"""
Filename: updater.py
Author: Christian Blank
Created Date: 2026-09-12
Description: Restricted Docker companion with persistent upgrade and rollback jobs.
"""

import asyncio
import copy
import hashlib
import json
import logging
import os
import secrets
import shutil
import sqlite3
import tarfile
import time
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Request

from .locking import ProcessLock
from .updates import PROTOCOL, discover, SHA

TERMINAL = {"idle", "succeeded", "rolled_back", "failed", "recovery_failed"}
logger = logging.getLogger("addarr.updater")


class Docker:
    """Small Docker Engine API client used only by the companion process."""

    def __init__(self) -> None:
        self.http = httpx.Client(transport=httpx.HTTPTransport(uds="/var/run/docker.sock"),
                                 base_url="http://docker/v1.45", timeout=180)

    def call(self, method: str, path: str, **kwargs: Any) -> Any:
        """Require a successful daemon response, keeping daemon details out of the UI."""
        response = self.http.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    def pull(self, image: str) -> None:
        """Consume the full pull stream and reject errors inside successful HTTP responses."""
        with self.http.stream("POST", "/images/create", params={"fromImage": image}, timeout=900) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line and json.loads(line).get("error"):
                    raise RuntimeError("Image pull failed")

    def inspect(self, container: str) -> dict[str, Any]:
        """Inspect a configured container ID or name using an escaped path segment."""
        return self.call("GET", f"/containers/{quote(container, safe='')}/json")

    def action(self, container: str, action: str, **kwargs: Any) -> Any:
        """Apply a fixed lifecycle operation; callers never accept action names from HTTP."""
        return self.call("POST", f"/containers/{quote(container, safe='')}/{action}", **kwargs)


class UpdateManager:
    """Own one configured target, one persistent job, and its data backups.

    The original container is retained until the new image passes startup checks.
    Before commit, any restart of this companion resumes rollback. After commit,
    recovery finishes activation instead, because workers may have made requests.
    """

    def __init__(self, state: Path, config: Path, target: str, docker: Docker):
        self.state, self.config, self.target, self.docker = state, config, target, docker
        self.state.mkdir(parents=True, exist_ok=True)
        self.path = state / "job.json"
        self.job = json.loads(self.path.read_text()) if self.path.exists() else {"phase": "idle"}
        self.lock = asyncio.Lock()
        self.task: asyncio.Task[None] | None = None

    def save(self, phase: str, **values: Any) -> None:
        """Atomically persist and fsync state before each irreversible lifecycle step."""
        self.job = {**self.job, **values, "phase": phase, "updated": time.time()}
        temporary = self.state / "job.tmp"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(self.job, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)
        # This status file is also the read-only activation gate for uid 1000.
        if os.name != "nt":
            self.path.chmod(0o644)
            fd = os.open(self.state, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def public(self) -> dict[str, Any]:
        """Return job progress without container configuration, paths or environment secrets."""
        return {"protocol": PROTOCOL, **{k: self.job[k] for k in
                ("id", "phase", "revision", "updated", "error") if k in self.job}}

    def validate(self, original: dict[str, Any]) -> None:
        """Require explicit opt-in and identical data/control mounts in both containers."""
        if original["Config"].get("Labels", {}).get("io.addarr.updates") != "enabled":
            raise ValueError("Target container has not enabled updates")
        if not original["State"]["Running"]:
            raise ValueError("Target must be running")
        own = self.docker.inspect(os.getenv("HOSTNAME", "addarr-updater"))
        for target_path, own_path in (("/config", "/config"), ("/updates", "/state")):
            target = next((m for m in original["Mounts"] if m["Destination"] == target_path), None)
            local = next((m for m in own["Mounts"] if m["Destination"] == own_path), None)
            if not target or not local or target["Source"] != local["Source"] or target["Type"] != local["Type"]:
                raise ValueError("Companion mounts do not match the target")
            if target_path == "/updates" and target.get("RW"):
                raise ValueError("The app must mount update state read-only")
        if any(m["Destination"].startswith("/config/") for m in original["Mounts"]):
            raise ValueError("Nested config mounts cannot be backed up safely")
        if original["HostConfig"].get("AutoRemove"):
            raise ValueError("Auto-remove containers cannot be updated")

    async def start(self, revision: str) -> dict[str, Any]:
        """Recheck ancestry and published image server-side; accept no image or container input."""
        async with self.lock:
            if self.job["phase"] not in TERMINAL or self.job["phase"] == "recovery_failed":
                raise ValueError("An update is already running or needs recovery")
            original = await asyncio.to_thread(self.docker.inspect, self.target)
            await asyncio.to_thread(self.validate, original)
            labels = original["Config"].get("Labels") or {}
            current = labels.get("org.opencontainers.image.revision", "unknown")
            env_revision = next((e.split("=", 1)[1] for e in original["Config"]["Env"]
                                 if e.startswith("ADDARR_REVISION=")), "unknown")
            if current != env_revision or not SHA.fullmatch(current):
                raise ValueError("Local or unknown builds need a manual update")
            async with httpx.AsyncClient(follow_redirects=False) as http:
                available = await discover(http, current)
            if not available["available"] or revision != available["latest"]:
                raise ValueError("This commit is not ready to install")
            job_id = secrets.token_hex(12)
            # Secrets from inspect live in a separate root-only file, never the app's gate.
            fd = os.open(self.state / "original.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(original, stream)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                (self.state / "original.json").chmod(0o600)
            active_jobs = self.job.get("active_jobs", [])
            self.job = {"id": job_id, "revision": revision, "image": available["image"], "active_jobs": active_jobs,
                        "old_id": original["Id"], "old_name": original["Name"].lstrip("/"),
                        "backup_name": f"{self.target}-previous-{job_id}", "candidate": "", "error": ""}
            self.save("pulling")
            self.task = asyncio.create_task(asyncio.to_thread(self.install))
            return self.public()

    def archive(self, name: str, *, check_database: bool = True) -> str:
        """Archive stopped application data, preserving ownership and checking SQLite integrity."""
        destination = self.state / name
        for path in self.config.rglob("*"):
            if path.relative_to(self.config).parts[0] == "backups":
                continue
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ValueError("Config must contain ordinary files and directories")
        database = self.config / "addarr.db"
        if database.exists() and check_database:
            with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as connection:
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Database integrity check failed")
        temporary = destination.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)
        with tarfile.open(temporary, "w:gz", dereference=True) as archive:
            for path in self.config.iterdir():
                if path.name != "backups":
                    archive.add(path, arcname=path.name, recursive=True)
        if os.name != "nt":
            temporary.chmod(0o600)
        with temporary.open("r+b") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            os.fsync(stream.fileno())
        temporary.replace(destination)
        return digest

    def restore(self) -> None:
        """Restore only a verified archive into the already-validated shared config mount."""
        source = self.state / f"backup-{self.job['id']}.tar.gz"
        with source.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != self.job["backup_digest"]:
                raise ValueError("Backup checksum mismatch")
        with tarfile.open(source) as archive:
            members = archive.getmembers()
            for member in members:
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                    raise ValueError("Unsupported backup entry")
            # /config is a fixed verified mount, and every deletion is its direct child.
            for child in self.config.iterdir():
                if child.name == "backups":
                    continue
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            archive.extractall(self.config, members=members, numeric_owner=True, filter="fully_trusted")

    def networks(self, original: dict[str, Any]) -> dict[str, Any]:
        """Preserve aliases and explicit IPAM configuration, omitting daemon-assigned addresses."""
        return {name: {k: copy.deepcopy(v) for k, v in endpoint.items()
                       if k in {"Aliases", "IPAMConfig", "DriverOpts", "Links"} and v is not None}
                for name, endpoint in original["NetworkSettings"]["Networks"].items()}

    def detach(self, container: str) -> None:
        """Release network aliases before creating a replacement with the same name."""
        for name in self.docker.inspect(container)["NetworkSettings"]["Networks"]:
            if name in {"host", "none"}:
                continue
            self.docker.call("POST", f"/networks/{quote(name, safe='')}/disconnect",
                             json={"Container": container, "Force": True})

    def healthy(self, container: str, revision: str) -> bool:
        """Check startup in the container itself, including the closed maintenance gate."""
        script = ("import json,urllib.request; d=json.load(urllib.request.urlopen("
                  "'http://127.0.0.1:8090/health/ready',timeout=3)); "
                  f"assert d['ok'] and d['maintenance'] and d['revision']=={revision!r} and d['updater_protocol']=={PROTOCOL}")
        return self.probe(container, script)

    def probe(self, container: str, script: str) -> bool:
        """Run a fixed readiness assertion inside the target without exposing output or credentials."""
        exec_id = self.docker.call("POST", f"/containers/{container}/exec", json={
            "Cmd": ["python", "-c", script], "AttachStdout": False, "AttachStderr": False})["Id"]
        self.docker.call("POST", f"/exec/{exec_id}/start", json={"Detach": True})
        for _ in range(10):
            result = self.docker.call("GET", f"/exec/{exec_id}/json")
            if not result["Running"]:
                return result["ExitCode"] == 0
            time.sleep(0.5)
        return False

    def install(self) -> None:
        """Pull, stop, back up, start gated candidate, then commit or roll back."""
        try:
            original = json.loads((self.state / "original.json").read_text())
            self.docker.pull(self.job["image"])
            image = self.docker.call("GET", f"/images/{quote(self.job['image'], safe='')}/json")
            labels = image["Config"].get("Labels") or {}
            if labels.get("org.opencontainers.image.revision") != self.job["revision"] or labels.get("io.addarr.updater.protocol") != str(PROTOCOL):
                raise ValueError("Published image does not support this updater protocol")
            self.save("stopping")
            self.docker.action(self.job["old_id"], "stop", params={"t": 45})
            if self.docker.inspect(self.job["old_id"])["State"]["Running"]:
                raise ValueError("Target did not stop")
            self.save("backing_up")
            digest = self.archive(f"backup-{self.job['id']}.tar.gz")
            self.save("replacing", backup_digest=digest)
            self.detach(self.job["old_id"])
            self.docker.action(self.job["old_id"], "rename", params={"name": self.job["backup_name"]})
            config = copy.deepcopy(original["Config"])
            config["Image"] = self.job["image"]
            config["Labels"] = {**(config.get("Labels") or {}), **labels}
            config["Env"] = [e for e in config.get("Env", []) if not e.startswith(("ADDARR_REVISION=", "ADDARR_UPDATE_JOB="))]
            config["Env"] += [f"ADDARR_REVISION={self.job['revision']}", f"ADDARR_UPDATE_JOB={self.job['id']}"]
            config["HostConfig"] = copy.deepcopy(original["HostConfig"])
            # HostConfig can contain an empty HostPort for automatically allocated ports.
            # Preserve the actual bindings, so existing browser URLs keep working.
            if original["NetworkSettings"].get("Ports"):
                config["HostConfig"]["PortBindings"] = {
                    port: bindings for port, bindings in original["NetworkSettings"]["Ports"].items() if bindings
                }
            config["NetworkingConfig"] = {"EndpointsConfig": self.networks(original)}
            self.save("creating")
            candidate = self.docker.call("POST", "/containers/create", params={"name": self.job["old_name"]}, json=config)["Id"]
            self.save("starting", candidate=candidate)
            self.docker.action(candidate, "start")
            self.save("checking")
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if self.healthy(candidate, self.job["revision"]):
                    # This is the activation boundary. Never restore data after workers may run.
                    self.save("committed", active_jobs=[*self.job.get("active_jobs", [])[-2:], self.job["id"]])
                    self.finish()
                    return
                time.sleep(2)
            raise RuntimeError("Candidate startup timed out")
        except Exception as exc:
            logger.warning("update_failed phase=%s category=%s", self.job["phase"], type(exc).__name__)
            if self.job["phase"] == "committed":
                return  # Recovery will finish cleanup; rollback is no longer safe.
            self.rollback()

    def finish(self) -> None:
        """Retain the previous image and three backups; remove the stopped old container."""
        try:
            self.docker.call("DELETE", f"/containers/{self.job['old_id']}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        backups = sorted(self.state.glob("backup-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in backups[3:]:
            path.unlink()
        self.save("succeeded")

    def rollback(self) -> None:
        """Recover the original container, using a pre-migration backup when replacement began."""
        prior = self.job["phase"]
        try:
            self.save("rolling_back", error="The update failed. Restoring the previous version.")
            original = json.loads((self.state / "original.json").read_text())
            candidate = self.job.get("candidate")
            if not candidate and prior in {"creating", "rolling_back"}:
                try:
                    found = self.docker.inspect(self.job["old_name"])
                    if found["Id"] != self.job["old_id"]:
                        candidate = found["Id"]
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise
            if candidate:
                try:
                    self.docker.action(candidate, "stop", params={"t": 45})
                    self.docker.call("DELETE", f"/containers/{candidate}")
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise
            if self.job.get("backup_digest") and not self.job.get("restore_done"):
                if self.docker.inspect(self.job["old_id"])["State"]["Running"]:
                    self.docker.action(self.job["old_id"], "stop", params={"t": 45})
                try:
                    if not (self.state / f"failed-{self.job['id']}.tar.gz").exists():
                        self.archive(f"failed-{self.job['id']}.tar.gz", check_database=False)
                except Exception:
                    pass  # A corrupt candidate database must not prevent restoring the good backup.
                self.restore()
                self.save("rolling_back", restore_done=True)
            old = self.docker.inspect(self.job["old_id"])
            if old["Name"].lstrip("/") != self.job["old_name"]:
                self.docker.action(self.job["old_id"], "rename", params={"name": self.job["old_name"]})
            for name, endpoint in self.networks(original).items():
                if name not in old["NetworkSettings"]["Networks"]:
                    self.docker.call("POST", f"/networks/{quote(name, safe='')}/connect",
                                     json={"Container": self.job["old_id"], "EndpointConfig": endpoint})
            if not old["State"]["Running"]:
                self.docker.action(self.job["old_id"], "start")
            script = ("import json,urllib.request; d=json.load(urllib.request.urlopen("
                      "'http://127.0.0.1:8090/health/ready',timeout=3)); "
                      "assert d['ok'] and not d.get('maintenance',False)")
            deadline = time.monotonic() + 120
            while not self.probe(self.job["old_id"], script):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Restored version did not become ready")
                time.sleep(2)
            self.save("rolled_back", error="The update failed. The previous version has been restored.")
        except Exception as exc:
            logger.warning("update_recovery_failed category=%s", type(exc).__name__)
            self.save("recovery_failed", error="Automatic recovery stopped. Keep the backups and inspect the updater logs.")

    def recover(self) -> None:
        """Resume a persisted job before accepting another installation request."""
        if self.job["phase"] == "committed":
            self.finish()
        elif self.job["phase"] not in TERMINAL:
            self.rollback()


def create_updater() -> FastAPI:
    """Serve a token-authenticated, single-target protocol on the internal Docker network."""
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        token = (await asyncio.to_thread(Path(os.environ["ADDARR_UPDATER_TOKEN_FILE"]).read_text)).strip()
        if len(token) < 32:
            raise RuntimeError("Updater token must have at least 32 characters")
        state = Path(os.getenv("ADDARR_UPDATE_STATE", "/state"))
        with closing(ProcessLock(state)):
            docker = Docker()
            manager = UpdateManager(state, Path("/config"), os.environ["ADDARR_UPDATE_TARGET"], docker)
            app.state.manager, app.state.token = manager, token
            await asyncio.to_thread(manager.recover)

            async def cleanup() -> None:
                """Retry post-commit cleanup without ever rolling back an activated version."""
                while True:
                    await asyncio.sleep(30)
                    if manager.job["phase"] == "committed" and (manager.task is None or manager.task.done()):
                        try:
                            await asyncio.to_thread(manager.finish)
                        except Exception as exc:
                            logger.warning("update_cleanup_pending category=%s", type(exc).__name__)

            cleanup_task = asyncio.create_task(cleanup())
            try:
                yield
            finally:
                cleanup_task.cancel()
                await asyncio.gather(cleanup_task, return_exceptions=True)
                if manager.task:
                    await manager.task
                docker.http.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route("/job", methods=["GET", "POST"])
    async def job(request: Request) -> dict[str, Any]:
        """Accept only a revision and protocol version from the authenticated web server."""
        if not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {app.state.token}"):
            raise HTTPException(401, "Authentication required")
        manager: UpdateManager = app.state.manager
        if request.method == "GET":
            return manager.public()
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > 1024:
                raise HTTPException(413, "Request too large")
        try:
            data = json.loads(body)
            if set(data) != {"revision", "protocol"} or data["protocol"] != PROTOCOL or not SHA.fullmatch(data["revision"]):
                raise ValueError("Unsupported update request")
            return await manager.start(data["revision"])
        except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
            raise HTTPException(409, "Update unavailable; check the container setup and published build") from exc

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_updater(), host="0.0.0.0", port=8091, log_level="info")
