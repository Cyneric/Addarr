"""
Filename: test_updates.py
Author: Christian Blank
Created Date: 2026-09-12
Description: Update discovery, authentication, maintenance and recovery regression tests.
"""

import copy
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from addarr.updates import discover, maintenance, PROTOCOL, update_view
from addarr.updater import UpdateManager, create_updater
from addarr.web import create_app

OLD = "1" * 40
NEW = "2" * 40
IMAGE = "ghcr.io/cyneric/addarr@sha256:" + "3" * 64


@pytest.mark.parametrize("phase,expected,can_install", [
    ("idle", "available", True), ("pulling", "updating", False),
    ("backing_up", "updating", False), ("checking", "updating", False),
    ("rolling_back", "updating", False), ("rolled_back", "error", True),
    ("recovery_failed", "error", False),
])
def test_update_view_hides_internal_steps(phase, expected, can_install):
    status = {"current": OLD, "latest": NEW, "available": True, "checked": 1, "status": "update_available"}
    view = update_view(status, {"phase": phase, "enabled": True})
    assert view["state"] == expected
    assert view["can_install"] == can_install
    if expected == "updating":
        assert view["message_key"] == "update_simple_busy"


def test_simple_update_fallbacks_and_success_acknowledgement():
    import time

    status = {"current": NEW, "latest": NEW, "available": False, "checked": 1, "status": "up_to_date"}
    assert not update_view(status, {"enabled": True, "phase": "idle"})["visible"]
    job = {"enabled": True, "phase": "succeeded", "revision": NEW, "updated": time.time()}
    assert update_view(status, job)["state"] == "updated"
    job["updated"] -= 121
    assert not update_view(status, job)["visible"]
    status.update(current=OLD, available=True)
    assert update_view(status, {"enabled": False, "phase": "manual_update"})["message_key"] == "update_simple_setup"
    assert update_view(status, {"enabled": False, "phase": "updater_unavailable"})["details"]
    status.update(current="unknown", available=False, status="local_build")
    view = update_view(status, job)
    assert view["state"] == "development" and not view["can_install"]
    assert update_view(status, job, gated=True)["state"] == "updating"
    assert update_view(status, {"phase": "recovery_failed"}, gated=True)["state"] == "error"


@pytest.mark.parametrize("current,comparison,published,status", [
    ("unknown", "ahead", True, "local_build"),
    (NEW, "identical", True, "up_to_date"),
    (OLD, "behind", True, "local_build"),
    (OLD, "diverged", True, "local_build"),
    (OLD, "ahead", False, "build_pending"),
    (OLD, "ahead", True, "update_available"),
])
async def test_discovery_never_downgrades_or_offers_unpublished_images(current, comparison, published, status):
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path.endswith("/commits/main"):
            return httpx.Response(200, json={"sha": NEW})
        if "/compare/" in request.url.path:
            return httpx.Response(200, json={"status": comparison, "commits": [{"sha": NEW, "commit": {"message": "feat: downloads\n\nDetails"}}]})
        if request.url.path == "/token":
            return httpx.Response(200, json={"token": "registry-secret"})
        return httpx.Response(200 if published else 404, headers={"docker-content-digest": IMAGE.split("@")[1]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await discover(http, current)
    assert result["status"] == status
    assert result["available"] == (status == "update_available")
    if result["available"]:
        assert result["image"] == IMAGE
        assert result["commits"][0]["message"] == "feat: downloads"
    if current == "unknown":
        assert len(calls) == 1


def test_maintenance_gate_survives_companion_restart_and_second_update(tmp_path, monkeypatch):
    monkeypatch.setenv("ADDARR_UPDATE_STATE", str(tmp_path))
    monkeypatch.setenv("ADDARR_UPDATE_JOB", "new-job")
    assert maintenance()
    path = tmp_path / "job.json"
    path.write_text(json.dumps({"id": "new-job", "phase": "checking"}))
    assert maintenance()
    path.write_text(json.dumps({"id": "new-job", "phase": "committed", "active_jobs": ["new-job"]}))
    assert not maintenance()
    path.write_text(json.dumps({"id": "next-job", "phase": "pulling", "active_jobs": ["new-job"]}))
    assert not maintenance()


def test_candidate_migrates_but_blocks_mutations_and_workers(tmp_path, monkeypatch):
    monkeypatch.setenv("ADDARR_UPDATE_STATE", str(tmp_path / "control"))
    monkeypatch.setenv("ADDARR_UPDATE_JOB", "candidate")
    app = create_app(tmp_path / "data", background=True, transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with TestClient(app) as client:
        ready = client.get("/health/ready").json()
        assert ready["ok"] and ready["maintenance"] and ready["updater_protocol"] == PROTOCOL
        assert app.state.engine.last_tick == 0
        assert client.post("/setup", data={"username": "wrong"}).status_code == 503
        assert client.post("/settings").status_code == 503
        assert not app.state.store.all("SELECT * FROM admins")


class FakeDocker:
    """Persist containers independently of manager restarts and inject startup failures."""

    def __init__(self, config: Path):
        self.config = config
        self.containers = {"old": {"Id": "old", "Name": "/addarr", "Image": "previous-image",
                                   "Config": {"Env": [f"ADDARR_REVISION={OLD}", "KEEP=yes"], "Labels": {
                                       "org.opencontainers.image.revision": OLD, "io.addarr.updates": "enabled"}},
                                   "HostConfig": {"ReadonlyRootfs": True, "Binds": ["config:/config"]},
                                   "State": {"Running": True},
                                   "NetworkSettings": {"Networks": {"test": {"Aliases": ["addarr"]}}}}}
        self.calls = []
        self.fail_create = False

    def inspect(self, name):
        for row in self.containers.values():
            if row["Id"] == name or row["Name"].lstrip("/") == name:
                return copy.deepcopy(row)
        raise httpx.HTTPStatusError("missing", request=httpx.Request("GET", "http://docker"), response=httpx.Response(404))

    def pull(self, image):
        self.calls.append(("pull", image))

    def action(self, container, action, **kwargs):
        self.calls.append((action, container))
        row = self.containers[container]
        if action == "stop":
            row["State"]["Running"] = False
        elif action == "start":
            row["State"]["Running"] = True
            if container == "candidate":
                (self.config / "keep.txt").write_text("candidate changed this")
                (self.config / "new-file.txt").write_text("candidate-only")
        elif action == "rename":
            row["Name"] = "/" + kwargs["params"]["name"]

    def call(self, method, path, **kwargs):
        self.calls.append((method, path))
        if path.endswith("/exec"):
            return {"Id": "health"}
        if path == "/exec/health/json":
            return {"Running": False, "ExitCode": 0}
        if path.startswith("/images/"):
            return {"Config": {"Labels": {"org.opencontainers.image.revision": NEW, "io.addarr.updater.protocol": "1"}}}
        if path == "/containers/create":
            if self.fail_create:
                raise ValueError("Cannot create container")
            self.containers["candidate"] = {"Id": "candidate", "Name": "/addarr", "State": {"Running": False},
                                             "Config": kwargs["json"], "NetworkSettings": {"Networks": {"test": {}}}}
            return {"Id": "candidate"}
        if method == "DELETE":
            self.containers.pop(path.split("/")[-1], None)
        if path.endswith("/disconnect"):
            self.containers[kwargs["json"]["Container"]]["NetworkSettings"]["Networks"] = {}
        if path.endswith("/connect"):
            self.containers[kwargs["json"]["Container"]]["NetworkSettings"]["Networks"]["test"] = kwargs["json"]["EndpointConfig"]


def manager_fixture(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "keep.txt").write_text("original data")
    (config / "backups").mkdir()
    (config / "backups" / "old.db").write_text("previous backup")
    docker = FakeDocker(config)
    manager = UpdateManager(tmp_path / "state", config, "addarr", docker)
    (manager.state / "original.json").write_text(json.dumps(docker.inspect("old")))
    manager.job = {"id": "job", "revision": NEW, "image": IMAGE, "old_id": "old", "old_name": "addarr",
                   "backup_name": "addarr-previous-job", "candidate": "", "active_jobs": ["older-job"]}
    manager.save("pulling")
    return manager, docker


def test_success_pulls_before_stopping_and_preserves_container_settings(tmp_path, monkeypatch):
    manager, docker = manager_fixture(tmp_path)
    monkeypatch.setattr(manager, "healthy", lambda *args: True)
    manager.install()
    assert manager.job["phase"] == "succeeded"
    assert manager.job["active_jobs"] == ["older-job", "job"]
    assert docker.calls.index(("pull", IMAGE)) < docker.calls.index(("stop", "old"))
    assert "old" not in docker.containers
    config = docker.containers["candidate"]["Config"]
    assert "KEEP=yes" in config["Env"] and "ADDARR_UPDATE_JOB=job" in config["Env"]
    assert config["HostConfig"]["ReadonlyRootfs"]
    assert config["NetworkingConfig"]["EndpointsConfig"]["test"]["Aliases"] == ["addarr"]


def test_startup_failure_restores_files_and_original_container(tmp_path, monkeypatch):
    manager, docker = manager_fixture(tmp_path)

    def unhealthy(*args):
        raise RuntimeError("bad migration")

    monkeypatch.setattr(manager, "healthy", unhealthy)
    manager.install()
    assert manager.job["phase"] == "rolled_back"
    assert manager.config.joinpath("keep.txt").read_text() == "original data"
    assert not manager.config.joinpath("new-file.txt").exists()
    assert manager.config.joinpath("backups", "old.db").read_text() == "previous backup"
    assert docker.inspect("addarr")["Id"] == "old"
    assert docker.inspect("old")["State"]["Running"]
    assert (manager.state / "failed-job.tar.gz").exists()
    # Restarting the companion does not restore a second time after workers resumed.
    manager.config.joinpath("keep.txt").write_text("work after rollback")
    restarted = UpdateManager(manager.state, manager.config, "addarr", docker)
    restarted.recover()
    assert manager.config.joinpath("keep.txt").read_text() == "work after rollback"


def test_companion_restart_recovers_interrupted_create(tmp_path):
    manager, docker = manager_fixture(tmp_path)
    docker.action("old", "stop")
    digest = manager.archive("backup-job.tar.gz")
    docker.action("old", "rename", params={"name": "addarr-previous-job"})
    docker.call("POST", "/containers/create", json={})
    docker.action("candidate", "start")
    manager.save("creating", backup_digest=digest)
    restarted = UpdateManager(manager.state, manager.config, "addarr", docker)
    restarted.recover()
    assert restarted.job["phase"] == "rolled_back"
    assert docker.inspect("addarr")["Id"] == "old"
    assert manager.config.joinpath("keep.txt").read_text() == "original data"


def test_recovery_after_commit_never_restores_the_old_database(tmp_path, monkeypatch):
    manager, docker = manager_fixture(tmp_path)
    monkeypatch.setattr(manager, "healthy", lambda *args: True)

    def fail_cleanup():
        raise OSError("daemon temporarily unavailable")

    monkeypatch.setattr(manager, "finish", fail_cleanup)
    manager.install()
    assert manager.job["phase"] == "committed"
    manager.config.joinpath("keep.txt").write_text("work after activation")
    restarted = UpdateManager(manager.state, manager.config, "addarr", docker)
    restarted.recover()
    assert restarted.job["phase"] == "succeeded"
    assert manager.config.joinpath("keep.txt").read_text() == "work after activation"


def test_backup_failure_does_not_replace_container(tmp_path, monkeypatch):
    manager, docker = manager_fixture(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(manager, "archive", fail)
    manager.install()
    assert manager.job["phase"] == "rolled_back"
    assert docker.inspect("old")["State"]["Running"]
    assert not any(path == "/containers/create" for _, path in docker.calls)


def test_tampered_backup_blocks_destructive_restore(tmp_path):
    manager, _ = manager_fixture(tmp_path)
    manager.save("checking", backup_digest=manager.archive("backup-job.tar.gz"))
    (manager.state / "backup-job.tar.gz").write_bytes(b"invalid")
    with pytest.raises(ValueError, match="checksum"):
        manager.restore()
    assert manager.config.joinpath("keep.txt").read_text() == "original data"


async def test_concurrent_jobs_rejected(tmp_path):
    manager, _ = manager_fixture(tmp_path)
    with pytest.raises(ValueError, match="already running"):
        await manager.start(NEW)


def test_companion_auth_and_fixed_protocol(tmp_path, monkeypatch):

    token = tmp_path / "token"
    token.write_text("x" * 48)
    monkeypatch.setenv("ADDARR_UPDATER_TOKEN_FILE", str(token))
    monkeypatch.setenv("ADDARR_UPDATE_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("ADDARR_UPDATE_TARGET", "fixed-target")
    with TestClient(create_updater()) as client:
        assert client.get("/job").status_code == 401
        headers = {"Authorization": "Bearer " + "x" * 48}
        assert client.get("/job", headers=headers).json()["protocol"] == PROTOCOL
        assert client.post("/job", headers=headers, json={"revision": NEW, "protocol": 99}).status_code == 409
        assert client.post("/job", headers=headers, json={"revision": NEW, "protocol": 1, "container": "other"}).status_code == 409
        assert client.post("/job", headers=headers, json={"revision": ";rm -rf /", "protocol": 1}).status_code == 409
        assert client.post("/job", headers=headers, content="x" * 2048).status_code == 413
