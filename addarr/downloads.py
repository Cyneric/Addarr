"""
Filename: downloads.py
Author: Christian Blank
Created Date: 2026-09-12
Description: Read-only SABnzbd progress, linked to requests through Arr download IDs.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, HttpUrl, field_validator

from .adapters import ArrClient, configured_clients
from .domain import MediaRef, Options, ServiceError
from .engine import Engine
from .i18n import translate
from .store import Store

logger = logging.getLogger("addarr.downloads")


class SabnzbdConfig(BaseModel):
    """One optional SABnzbd instance; mapping values are Arr download-client IDs."""

    url: HttpUrl
    api_key: str
    enabled: bool = False
    mappings: dict[str, int] = {}

    @field_validator("url")
    @classmethod
    def plain_url(cls, value: HttpUrl) -> HttpUrl:
        """Keep credentials and API parameters out of the saved address."""
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("Use a URL without credentials, query or fragment")
        return value


class SabnzbdClient:
    """Read queue and history only. The caller owns the HTTP client."""

    def __init__(self, config: SabnzbdConfig, http: httpx.AsyncClient):
        self.config, self.http = config, http
        self.base = str(config.url).rstrip("/")
        self.instance = hashlib.sha256(self.base.encode()).hexdigest()[:16]

    async def read(self, mode: str, **params: Any) -> dict[str, Any]:
        """Fetch a bounded status response without exposing API keys in errors."""
        if mode not in {"queue", "history", "version"}:
            raise ValueError("Only status queries are supported")
        try:
            response = await self.http.get(
                self.base + "/api", params={"mode": mode, "output": "json",
                                             "apikey": self.config.api_key, **params},
                timeout=httpx.Timeout(15, connect=5), follow_redirects=False,
            )
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict) or value.get("error"):
                raise ValueError("Invalid status response")
            if mode != "version" and (not isinstance(value.get(mode), dict) or
                                      not isinstance(value[mode].get("slots"), list)):
                raise ValueError("Invalid job list")
            return value
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceError("sabnzbd", "SABnzbd is unavailable; check its address and API key", True) from exc

    async def jobs(self, ids: set[str]) -> dict[str, dict[str, Any]]:
        """Read only the jobs identified by Arr, in bounded batches, including history."""
        jobs: dict[str, dict[str, Any]] = {}
        ordered = sorted(ids)
        for start in range(0, len(ordered), 50):
            batch = ",".join(ordered[start:start + 50])
            for mode in ("history", "queue"):
                response = await self.read(mode, nzo_ids=batch, limit=50)
                block = response.get(mode)
                if not isinstance(block, dict) or not isinstance(block.get("slots"), list):
                    raise ServiceError("sabnzbd", "SABnzbd returned an invalid job list", True)
                for slot in block["slots"]:
                    if slot.get("nzo_id") in ids:
                        if mode == "queue" and block.get("paused") and str(slot.get("priority")).lower() not in {"force", "2"}:
                            slot = {**slot, "status": "Paused", "timeleft": ""}
                        jobs[slot["nzo_id"]] = slot
        return jobs


async def download_clients(client: ArrClient) -> list[dict[str, Any]]:
    """Expose IDs and names, never the credentials returned by Arr's client API."""
    rows = await client.call("GET", "downloadclient")
    return [{"id": int(row["id"]), "name": str(row["name"])} for row in rows
            if row.get("implementation", "").lower() == "sabnzbd" and row.get("enable", True)]


def from_client(entry: dict[str, Any], client_id: int, name: str) -> bool:
    """History names differ from implementation names; accept only an exact client identity."""
    data = {str(k).lower(): v for k, v in entry.get("data", {}).items()}
    return entry.get("downloadClientId") == client_id or (
        entry.get("downloadClient") == name if "downloadClient" in entry
        else data.get("downloadclientname") == name
    )


async def records(client: ArrClient, path: str, since: float = 0) -> list[dict[str, Any]]:
    """Page through Arr status records; refuse incomplete oversized responses."""
    from datetime import datetime

    result: list[dict[str, Any]] = []
    for page in range(1, 101):
        params: dict[str, Any] = {"page": page, "pageSize": 100, "includeEpisode": "true"}
        if path == "history":
            params.update(sortKey="date", sortDirection="descending")
        body = await client.call("GET", path, params=params)
        if not isinstance(body, dict) or not isinstance(body.get("records"), list):
            raise ServiceError("downloads", "Arr returned an invalid status list", True)
        rows = body["records"]
        if path == "history" and since:
            for row in rows:
                try:
                    if row.get("date") and datetime.fromisoformat(row["date"].replace("Z", "+00:00")).timestamp() < since:
                        continue
                except ValueError:
                    continue
                result.append(row)
        else:
            result.extend(rows)
        if not rows or page * 100 >= body.get("totalRecords", 0):
            return result
        if path == "history" and rows[-1].get("date"):
            try:
                if datetime.fromisoformat(rows[-1]["date"].replace("Z", "+00:00")).timestamp() < since:
                    return result
            except ValueError:
                pass
    raise ServiceError("downloads", "Arr status list is too large to read completely", True)


def phase(slot: dict[str, Any]) -> str:
    """Normalize SAB states without treating a completed download as imported media."""
    state = str(slot.get("status", "")).lower()
    return {"downloading": "downloading", "queued": "download_queued", "paused": "download_paused",
            "checking": "download_checking", "verifying": "download_checking", "repairing": "download_checking",
            "extracting": "download_extracting", "moving": "download_extracting",
            "running": "download_extracting", "completed": "waiting_import", "failed": "download_failed",
            "fetching": "download_queued", "propagating": "download_queued", "grabbing": "download_queued"}.get(state, "download_unknown")


def number(value: Any) -> float | None:
    """Parse optional nonnegative finite metrics supplied as SAB strings."""
    import math

    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) and parsed >= 0 else None
    except (ValueError, TypeError):
        return None


def request_downloads(store: Store, row: dict[str, Any]) -> list[dict[str, Any]]:
    """Return distinct jobs only for active requests and the configured SAB instance."""
    config = store.setting("sabnzbd")
    if row["deleted"] or row["state"] != "submitted" or not config or not config.get("enabled"):
        return []
    instance = hashlib.sha256(str(SabnzbdConfig.model_validate(config).url).rstrip("/").encode()).hexdigest()[:16]
    jobs = store.all(
        "SELECT d.* FROM downloads d JOIN request_downloads r ON r.download_id=d.id "
        "WHERE r.request_id=? AND d.instance=?", (row["id"], instance),
    )
    for job in jobs:
        if job["seen"] < time.time() - 60:
            job.update(phase="download_unknown", percent=None, remaining=None, eta="")
    return jobs


def download_text(store: Store, row: dict[str, Any], locale: str = "en-us") -> str:
    """Format compact progress for Telegram; never show global speed as a job speed."""
    parts = []
    for job in request_downloads(store, row):
        text = translate(locale, job["phase"])
        if job["percent"] is not None:
            text += f" · {job['percent']:.0f}%"
        if job["remaining"] is not None:
            text += f" · {job['remaining']:.0f} MB"
        if job["eta"]:
            text += f" · {job['eta']}"
        parts.append(text)
    return "\n".join(parts[:10])


class DownloadTracker:
    """Poll status every fifteen seconds; all remote operations are reads.

    A durable many-to-many link allows a season pack to serve several requests.
    IDs from another Arr instance or unmapped client are never linked by title.
    """

    def __init__(self, engine: Engine):
        self.engine, self.store, self.http = engine, engine.store, engine.http
        self.history_at: dict[str, float] = {}

    async def matches(self, client: ArrClient, row: dict[str, Any], entries: list[dict[str, Any]]) -> set[str]:
        """Match remote movie, episode/season or album IDs, preserving request scope."""
        ref = MediaRef.model_validate_json(row["media"])
        if row["identity"] != client.identity(ref):
            return set()
        options = Options.model_validate_json(row["options"])
        media_key = {"movie": "movieId", "series": "seriesId", "album": "artistId", "artist": "artistId"}[ref.kind]
        candidates = [e for e in entries if e.get(media_key) == row["remote_id"]]
        if ref.kind == "album":
            albums = await client.call("GET", "album", params={"artistId": row["remote_id"]})
            ids = {a["id"] for a in albums if a.get("foreignAlbumId") == ref.external_id}
            candidates = [e for e in candidates if e.get("albumId") in ids]
        if ref.kind == "series" and options.monitoring in {"selected", "future"}:
            episodes = await client.call("GET", "episode", params={"seriesId": row["remote_id"]})
            if options.monitoring == "selected":
                ids = {e["id"] for e in episodes if e.get("seasonNumber") in options.seasons}
            else:
                from datetime import datetime

                ids = set()
                for episode in episodes:
                    try:
                        if datetime.fromisoformat(episode["airDateUtc"].replace("Z", "+00:00")).timestamp() >= row["created"]:
                            ids.add(episode["id"])
                    except (KeyError, ValueError):
                        continue
            candidates = [e for e in candidates if e.get("episodeId") in ids or (
                options.monitoring == "selected" and e.get("seasonNumber") in options.seasons)]
        return {str(e["downloadId"]) for e in candidates if e.get("downloadId")}

    async def tick(self) -> None:
        """Refresh associations, then one SAB snapshot for all associated jobs."""
        raw = self.store.setting("sabnzbd")
        if not raw or not raw.get("enabled"):
            return
        config = SabnzbdConfig.model_validate(raw)
        sab = SabnzbdClient(config, self.http)
        rows = self.store.all("SELECT * FROM requests WHERE state='submitted' AND deleted=0 AND remote_id IS NOT NULL")
        active: list[dict[str, Any]] = []
        for row in rows:
            try:
                self.engine.authorize(row["user_id"], chat_id=row["chat_id"])
                active.append(row)
            except PermissionError:
                continue
        ids: set[str] = set()
        for kind, client in configured_clients(self.store, self.http).items():
            selected = [r for r in active if json.loads(r["media"])["service"] == kind
                        and r["identity"] == client.identity(MediaRef.model_validate_json(r["media"]))]
            if not selected:
                continue
            try:
                choices = await download_clients(client)
                mapping = config.mappings.get(kind)
                if mapping is None and len(choices) == 1:
                    mapping = choices[0]["id"]
                choice = next((c for c in choices if c["id"] == mapping), None)
                if not choice or sum(c["name"] == choice["name"] for c in choices) != 1:
                    continue
                entries = await records(client, "queue")
                history_key = f"download_history:{kind}:{client.instance}:{sab.instance}:{mapping}"
                history_checked = 0.0
                if time.time() - self.history_at.get(kind, 0) >= 60:
                    since = self.store.setting(history_key, min(r["created"] for r in selected))
                    history_checked = time.time()
                    entries += await records(client, "history", since - 300)
                entries = [e for e in entries if from_client(e, choice["id"], choice["name"])]
                for row in selected:
                    matched = await self.matches(client, row, entries)
                    # Remote awaits may overlap cancellation, deletion or a policy change.
                    current = self.store.one("SELECT * FROM requests WHERE id=? AND state='submitted' AND deleted=0", (row["id"],))
                    if not current:
                        continue
                    self.engine.authorize(current["user_id"], chat_id=current["chat_id"])
                    for nzo_id in matched:
                        self.store.execute("INSERT OR IGNORE INTO downloads(instance,nzo_id) VALUES(?,?)", (sab.instance, nzo_id))
                        self.store.execute(
                            "INSERT OR IGNORE INTO request_downloads SELECT ?,id FROM downloads WHERE instance=? AND nzo_id=?",
                            (row["id"], sab.instance, nzo_id),
                        )
                    ids.update(d["nzo_id"] for d in request_downloads(self.store, current))
                if history_checked:
                    self.store.set_setting(history_key, history_checked)
                    self.history_at[kind] = history_checked
            except (ServiceError, PermissionError):
                logger.info("download_status_unavailable service=%s", kind)
        if not ids:
            return
        try:
            slots = await sab.jobs(ids)
        except ServiceError:
            return  # Last-seen times expire; outages never imply completion.
        with self.store.transaction():
            for nzo_id in ids:
                slot = slots.get(nzo_id, {})
                state = phase(slot)
                pct = number(slot.get("percentage"))
                if pct is not None:
                    pct = min(100, pct)
                self.store.execute(
                    "UPDATE downloads SET phase=?,percent=?,remaining=?,eta=?,seen=? WHERE instance=? AND nzo_id=?",
                    (state, pct, number(slot.get("mbleft")), str(slot.get("timeleft", ""))[:40],
                     time.time(), sab.instance, nzo_id),
                )
            for row in active:
                current = self.store.one("SELECT * FROM requests WHERE id=? AND state='submitted' AND deleted=0", (row["id"],))
                if not current:
                    continue
                try:
                    self.engine.authorize(current["user_id"], chat_id=current["chat_id"])
                except PermissionError:
                    continue
                states = {d["phase"] for d in request_downloads(self.store, current)}
                priority = ["download_failed", "download_unknown", "download_paused", "downloading",
                            "download_checking", "download_extracting", "download_queued", "waiting_import"]
                state = next((s for s in priority if s in states), "")
                if state and state != current["download_phase"]:
                    self.store.execute("UPDATE requests SET download_phase=? WHERE id=?", (state, row["id"]))
                    if state != "download_unknown":
                        self.engine.event(row["id"], "downloads", state)

    async def run(self) -> None:
        """Keep transient status failures from stopping request processing."""
        while True:
            try:
                await self.tick()
            except Exception:
                logger.warning("download_tracking_failed")
            await asyncio.sleep(15)
