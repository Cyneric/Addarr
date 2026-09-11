"""
Filename: engine.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Request approval, queued submissions, retries and library progress checks.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

import httpx

from .adapters import ArrClient, configured_clients
from .domain import MediaRef, Options, SearchResult, ServiceError
from .store import Store

logger = logging.getLogger("addarr.engine")


class Engine:
    """Request workflow shared by Telegram, web administration and the worker.

    Database transitions are synchronous and finish before remote calls.
    An asyncio lock serializes worker ticks within this process; ProcessLock
    in the application lifespan prevents a second server using the same data.
    """
    def __init__(self, store: Store, http: httpx.AsyncClient):
        self.store, self.http = store, http
        self.last_tick = 0.0
        self.health: dict[str, Any] = {}
        self._health_at = 0.0
        self._lock = asyncio.Lock()

    def client(self, kind: str) -> ArrClient:
        """Return a currently enabled adapter or raise ServiceError if it is unavailable."""
        client = configured_clients(self.store, self.http).get(kind)
        if not client:
            raise ServiceError("disabled", "This media service is not configured or enabled")
        return client

    def authorize(self, user_id: int, admin: bool = False) -> dict[str, Any]:
        """Return an active user, raising PermissionError for missing access or a required admin role."""
        user = self.store.user(user_id)
        if not user or user["status"] != "active" or (admin and user["role"] != "admin"):
            raise PermissionError("Access has not been approved")
        return user

    async def search(self, user_id: int, kind: str, term: str, media_kind: str = "") -> list[SearchResult]:
        """Authorize a user, validate the search length and query the selected service."""
        self.authorize(user_id)
        if not 1 <= len(term.strip()) <= 200:
            raise ValueError("Search must contain 1–200 characters")
        return await self.client(kind).search(term.strip(), media_kind)

    async def create(self, user_id: int, ref: MediaRef, options: Options) -> int:
        """Validate a selection and persist a new request, or return its existing ID.

        An active request with the same user, media, service instance and options
        is reused. New requests are queued for admins or an auto-approval policy;
        others remain pending. Access is rechecked after remote option validation.
        No media is added remotely until the worker submits the queued request.
        """
        self.authorize(user_id)
        client = self.client(ref.service)
        options = await client.validate_options(options)
        if ref.kind == "series" and options.monitoring == "selected" and not options.seasons:
            raise ValueError("Select at least one season")
        options.seasons = sorted(set(options.seasons))
        identity = client.identity(ref)
        scope = hashlib.sha256(
            json.dumps(
                {
                    "service": ref.service,
                    "kind": ref.kind,
                    "external_id": ref.external_id,
                    "artist_id": ref.artist_id,
                    "options": options.model_dump(),
                    "identity": identity,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with self.store.transaction():
            user = self.authorize(user_id)
            duplicate = self.store.one(
                "SELECT id FROM requests WHERE user_id=? AND scope=? "
                "AND state NOT IN ('rejected','cancelled','failed')",
                (user_id, scope),
            )
            if duplicate:
                return int(duplicate["id"])
            auto_approve = (
                self.store.setting("auto_approve_all", False)
                or user["role"] == "admin"
                or user["auto_approve"]
            )
            state = "queued" if auto_approve else "pending"
            now = time.time()
            cursor = self.store.execute(
                "INSERT INTO requests(user_id,media,options,identity,scope,state,created,updated) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (user_id, ref.model_dump_json(), options.model_dump_json(), identity, scope, state, now, now),
            )
            assert cursor.lastrowid is not None
            request_id = cursor.lastrowid
            self.event(request_id, str(user_id), state)
        return request_id

    def event(self, request_id: int, actor: str, state: str) -> None:
        """Record a request event and queue notifications for its owner and active admins.

        Call within the transaction that changes request state so the audit event
        and outbox rows commit together. Notification preferences control delivery
        rows but do not suppress the audit event.
        """
        row = self.store.one("SELECT * FROM requests WHERE id=?", (request_id,))
        assert row is not None
        event_id = self.store.audit(actor, state, request_id)
        recipients = self.store.all(
            "SELECT * FROM users WHERE status='active' AND chat_id IS NOT NULL AND (id=? OR role='admin')",
            (row["user_id"],),
        )
        notification_group = (
            "notify_availability"
            if state in ("available", "progress")
            else "notify_failures"
            if state == "failed"
            else "notify_requests"
        )
        if not self.store.setting(notification_group, True):
            return
        for user in recipients:
            payload = {
                "id": request_id,
                "title": json.loads(row["media"])["title"],
                "state": state,
                "progress": row["progress"],
            }
            self.store.execute(
                "INSERT OR IGNORE INTO outbox(event_id,chat_id,locale,key,payload) VALUES(?,?,?,?,?)",
                (event_id, user["chat_id"], user["locale"], "notification", json.dumps(payload)),
            )

    def action(
        self, request_id: int, action: str, actor: str, *, user_id: int | None = None, web_admin: bool = False
    ) -> None:
        """Apply an allowed request transition and audit it in one transaction.

        Owners may cancel pending or queued requests. Admins may also approve,
        reject or retry requests in the corresponding state. web_admin is trusted
        only after the web layer authenticates the caller. Invalid ownership raises
        PermissionError; stale or unsupported transitions raise ValueError.
        """
        with self.store.transaction():
            user = self.authorize(user_id) if user_id is not None else None
            is_admin = web_admin or bool(user and user["role"] == "admin")
            row = self.store.one("SELECT * FROM requests WHERE id=?", (request_id,))
            if not row or not (is_admin or user and row["user_id"] == user["id"]):
                raise PermissionError("Request is not accessible")
            transitions = {
                "approve": ("pending", "queued"),
                "reject": ("pending", "rejected"),
                "retry": ("failed", "queued"),
            }
            if action == "cancel":
                if row["state"] not in ("pending", "queued"):
                    raise ValueError("Only requests waiting for submission can be cancelled")
                target = "cancelled"
            else:
                if not is_admin:
                    raise PermissionError("Administrator role required")
                if action not in transitions or row["state"] != transitions[action][0]:
                    raise ValueError("This action is no longer available")
                target = transitions[action][1]
            self.store.execute(
                "UPDATE requests SET state=?,error='',attempts=0,next_attempt=0,updated=? WHERE id=?",
                (target, time.time(), request_id),
            )
            self.event(request_id, actor, target)

    async def tick(self) -> None:
        """Process at most one due request, then poll progress and refresh due health checks.

        Submission is marked before network I/O. The saved instance identity must
        still match, and an equivalent submitted request can supply its remote ID.
        Service failures become retries or a failed request through fail().
        """
        async with self._lock:
            self.last_tick = time.time()
            row = self.store.one(
                "SELECT * FROM requests WHERE state='queued' AND next_attempt<=? ORDER BY id LIMIT 1",
                (time.time(),),
            )
            if row:
                with self.store.transaction():
                    owner = self.store.user(row["user_id"])
                    if not owner or owner["status"] != "active":
                        self.store.execute(
                            "UPDATE requests SET state='failed',error=? WHERE id=?",
                            ("Requester access was revoked", row["id"]),
                        )
                        self.event(row["id"], "worker", "failed")
                        return
                    self.store.execute(
                        "UPDATE requests SET state='submitting',updated=? WHERE id=?",
                        (time.time(), row["id"]),
                    )
                try:
                    ref, opts = (
                        MediaRef.model_validate_json(row["media"]),
                        Options.model_validate_json(row["options"]),
                    )
                    client = self.client(ref.service)
                    if row["identity"] != client.identity(ref):
                        raise ServiceError(
                            "configuration", "Service address changed; review and create a new request"
                        )
                    shared = self.store.one(
                        "SELECT remote_id FROM requests WHERE scope=? AND id<>? "
                        "AND state IN ('submitted','available') AND remote_id IS NOT NULL ORDER BY id LIMIT 1",
                        (row["scope"], row["id"]),
                    )
                    if shared:
                        endpoint = "artist" if ref.kind == "album" else ref.kind
                        try:
                            await client.call("GET", f"{endpoint}/{shared['remote_id']}")
                        except ServiceError as exc:
                            if exc.category != "validation":
                                raise
                            shared = None
                    remote_id = (
                        shared["remote_id"]
                        if shared
                        else await client.submit(row["id"], row["user_id"], ref, opts)
                    )
                    with self.store.transaction():
                        self.store.execute(
                            "UPDATE requests SET state='submitted',remote_id=?,error='',updated=? WHERE id=?",
                            (remote_id, time.time(), row["id"]),
                        )
                        self.event(row["id"], "worker", "submitted")
                except ServiceError as exc:
                    self.fail(row, exc)
                except Exception:
                    logger.error("request_failed request_id=%s category=internal", row["id"])
                    self.fail(
                        row, ServiceError("internal", "Internal failure; inspect diagnostics and retry")
                    )
            await self.poll_progress()
            if time.time() - self._health_at >= 60:
                await self.check_health()

    def fail(self, row: dict[str, Any], exc: ServiceError) -> None:
        """Record a failure, retrying transient errors with capped backoff for fewer than eight attempts."""
        attempts = row["attempts"] + 1
        state = "queued" if exc.retryable and attempts < 8 else "failed"
        with self.store.transaction():
            self.store.execute(
                "UPDATE requests SET state=?,error=?,attempts=?,next_attempt=?,updated=? WHERE id=?",
                (state, str(exc), attempts, time.time() + min(300, 2**attempts), time.time(), row["id"]),
            )
            if state == "failed":
                self.event(row["id"], "worker", state)
        logger.warning("request_id=%s state=%s category=%s", row["id"], state, exc.category)

    async def poll_progress(self) -> None:
        """Poll up to five due submissions, scheduling the next check and recording progress changes."""
        rows = self.store.all(
            "SELECT * FROM requests WHERE state='submitted' AND next_attempt<=? ORDER BY next_attempt LIMIT 5",
            (time.time(),),
        )
        for row in rows:
            self.store.execute("UPDATE requests SET next_attempt=? WHERE id=?", (time.time() + 60, row["id"]))
            try:
                ref = MediaRef.model_validate_json(row["media"])
                client = self.client(ref.service)
                if row["identity"] != client.identity(ref):
                    raise ServiceError(
                        "configuration", "Service address changed; previous library cannot be queried"
                    )
                done, progress = await client.progress(
                    ref, Options.model_validate_json(row["options"]), row["remote_id"]
                )
                with self.store.transaction():
                    self.store.execute(
                        "UPDATE requests SET progress=?,error='',state=?,updated=? WHERE id=?",
                        (progress, "available" if done else "submitted", time.time(), row["id"]),
                    )
                    if done or progress != row["progress"] and progress and row["progress"]:
                        self.event(row["id"], "worker", "available" if done else "progress")
            except ServiceError as exc:
                self.store.execute("UPDATE requests SET error=? WHERE id=?", (str(exc), row["id"]))

    async def check_health(self) -> None:
        """Refresh enabled service status concurrently and drop cached entries for disabled services."""
        self._health_at = time.time()
        active = configured_clients(self.store, self.http)
        self.health = {key: value for key, value in self.health.items() if key in active}

        async def check(kind: str, client: ArrClient) -> None:
            try:
                result = await client.call("GET", "system/status")
                self.health[kind] = {"ok": True, "version": result.get("version"), "checked": time.time()}
            except ServiceError as exc:
                self.health[kind] = {"ok": False, "error": str(exc), "checked": time.time()}

        await asyncio.gather(*(check(k, c) for k, c in active.items()))

    async def run(self) -> None:
        """Recover interrupted submissions and tick until the task is cancelled.

        Previously submitting rows return to the queue for adapter reconciliation.
        Unexpected tick failures are logged without exception details that could
        expose credentials, and the loop resumes after one second.
        """
        self.store.execute("UPDATE requests SET state='queued',next_attempt=0 WHERE state='submitting'")
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("worker_tick_failed category=internal")
            await asyncio.sleep(1)
