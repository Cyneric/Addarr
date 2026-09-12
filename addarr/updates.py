"""
Filename: updates.py
Author: Christian Blank
Created Date: 2026-09-12
Description: Verified main-branch image discovery and the web app's updater client.
"""

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

PROTOCOL = 1
REPOSITORY = "Cyneric/Addarr"
IMAGE = "ghcr.io/cyneric/addarr"
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
RUNNING_PHASES = {"pulling", "stopping", "backing_up", "replacing", "creating", "starting", "checking",
                  "committed", "rolling_back"}


def update_view(status: dict[str, Any], job: dict[str, Any], *, gated: bool = False) -> dict[str, Any]:
    """Project technical update state into one user-facing status and optional action.

    Running jobs and recovery errors take precedence over cached release checks.
    A successful job is acknowledged briefly; old jobs never hide a newer update.
    """
    phase = job.get("phase", "manual_update")
    available = bool(status.get("available") and status.get("latest") != status.get("current"))
    ready = bool(available and SHA.fullmatch(status.get("current", "unknown")) and job.get("enabled")
                 and phase in {"idle", "succeeded", "rolled_back", "failed"})
    state, message, details = "current", "up_to_date", False
    if phase == "recovery_failed":
        state, message, details, ready = "error", "update_simple_recovery", True, False
    elif gated or phase in RUNNING_PHASES:
        state, message, ready = "updating", "update_simple_busy", False
    elif phase == "rolled_back":
        state, message, details = "error", "update_simple_restored", True
    elif phase == "failed":
        state, message, details = "error", "update_simple_failed", True
    elif available and job.get("revision") != status.get("latest"):
        state, message, details = ("available", "update_available", False) if ready else (
            "unavailable", "update_simple_setup" if phase == "manual_update" else "update_simple_unavailable", True)
    elif phase == "succeeded" and time.time() - job.get("updated", 0) < 120:
        state, message, ready = "updated", "update_simple_done", False
    elif status.get("status") == "local_build" or not SHA.fullmatch(status.get("current", "unknown")):
        state, message, ready = "development", "update_simple_development", False
    elif not job.get("enabled"):
        state, message, details = ("unavailable", "update_simple_setup" if phase == "manual_update"
                                   else "update_simple_unavailable", True)
    elif status.get("status") == "update_check_failed":
        state, message, details = "unavailable", "update_check_failed", True
    elif available:
        state, message, details = ("available", "update_available", False) if ready else (
            "unavailable", "update_simple_setup" if phase == "manual_update" else "update_simple_unavailable", True)
    elif status.get("status") == "build_pending":
        state, message, details = "preparing", "update_simple_preparing", True
    elif not status.get("checked"):
        state, message = "checking", "update_simple_checking"
    return {"state": state, "message_key": message, "can_install": ready,
            "revision": status.get("latest", "") if ready else "", "details": details,
            "visible": state in {"available", "updating", "updated", "error"} or available}


def installed_revision() -> str:
    """Only CI images carry a trusted revision; local builds default to unknown."""
    return os.getenv("ADDARR_REVISION", "unknown")


def maintenance() -> bool:
    """Fail closed until the companion commits this exact candidate's job."""
    job = os.getenv("ADDARR_UPDATE_JOB")
    if not job:
        return False
    try:
        state = json.loads((Path(os.getenv("ADDARR_UPDATE_STATE", "/updates")) / "job.json").read_text())
        return not (job in state.get("active_jobs", []) or
                    state.get("id") == job and state.get("phase") in {"committed", "succeeded"})
    except (OSError, ValueError):
        return True


async def published_image(http: httpx.AsyncClient, revision: str) -> str | None:
    """Resolve an immutable GHCR commit tag to a manifest digest, if published."""
    if not SHA.fullmatch(revision):
        raise ValueError("Invalid commit")
    token_response = await http.get("https://ghcr.io/token", params={
        "service": "ghcr.io", "scope": "repository:cyneric/addarr:pull"}, timeout=15)
    token_response.raise_for_status()
    token = token_response.json()["token"]
    response = await http.get(f"https://ghcr.io/v2/cyneric/addarr/manifests/sha-{revision}", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json",
    }, timeout=15)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    digest = response.headers.get("docker-content-digest", "")
    if not DIGEST.fullmatch(digest):
        raise ValueError("Registry did not return an image digest")
    return f"{IMAGE}@{digest}"


async def discover(http: httpx.AsyncClient, current: str) -> dict[str, Any]:
    """Offer only a published descendant of the running trusted CI revision."""
    result: dict[str, Any] = {"current": current, "checked": time.time(), "available": False,
                              "latest": "", "image": "", "status": "local_build", "commits": []}
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Addarr"}
    response = await http.get(f"https://api.github.com/repos/{REPOSITORY}/commits/main", headers=headers, timeout=15)
    response.raise_for_status()
    latest = response.json()["sha"]
    if not SHA.fullmatch(latest):
        raise ValueError("Invalid upstream commit")
    result["latest"] = latest
    if not SHA.fullmatch(current):
        return result
    if current == latest:
        result["status"] = "up_to_date"
        return result
    response = await http.get(f"https://api.github.com/repos/{REPOSITORY}/compare/{current}...{latest}", headers=headers, timeout=15)
    response.raise_for_status()
    comparison = response.json()
    if comparison.get("status") != "ahead":
        result["status"] = "local_build"
        return result
    result["commits"] = [{"sha": c["sha"], "message": c["commit"]["message"].splitlines()[0]}
                         for c in comparison.get("commits", [])[-30:]]
    result["image"] = await published_image(http, latest) or ""
    result["available"] = bool(result["image"])
    result["status"] = "update_available" if result["available"] else "build_pending"
    return result


class UpdateClient:
    """Cache hourly update checks and forward explicit admin installation requests."""

    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self.status: dict[str, Any] = {"current": installed_revision(), "latest": "", "available": False,
                                       "status": "not_checked", "commits": [], "checked": 0}
        self.lock = asyncio.Lock()
        self.install_lock = asyncio.Lock()
        self.job: dict[str, Any] = {"enabled": False, "phase": "manual_update"}

    async def check(self) -> None:
        """Preserve displayed commits on network failure but disable installation."""
        async with self.lock:
            try:
                self.status = await discover(self.http, installed_revision())
            except (httpx.HTTPError, ValueError, KeyError):
                self.status.update(status="update_check_failed", available=False, checked=time.time())

    async def companion(self, method: str = "GET", revision: str = "") -> dict[str, Any]:
        """Use a mounted secret; the browser never receives the companion token."""
        url = os.getenv("ADDARR_UPDATER_URL", "")
        token_file = os.getenv("ADDARR_UPDATER_TOKEN_FILE", "")
        if not url or not token_file:
            self.job = {"enabled": False, "phase": "manual_update"}
            return self.job
        try:
            token = (await asyncio.to_thread(Path(token_file).read_text)).strip()
            response = await self.http.request(method, url.rstrip("/") + "/job", headers={
                "Authorization": f"Bearer {token}"}, json={"revision": revision, "protocol": PROTOCOL} if method == "POST" else None,
                timeout=45)
            response.raise_for_status()
            result = response.json()
            if result.get("protocol") != PROTOCOL:
                self.job = {"enabled": False, "phase": "updater_incompatible"}
                return self.job
            self.job = {**result, "enabled": True}
            return self.job
        except (OSError, httpx.HTTPError, ValueError):
            self.job = {"enabled": False, "phase": "updater_unavailable"}
            return self.job

    async def run(self) -> None:
        """Check for commits hourly without ever starting installation."""
        while True:
            await self.check()
            await asyncio.sleep(3600)
