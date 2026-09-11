"""
Filename: web.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Web administration, first-run setup and application worker lifecycle.
"""

import asyncio
import hashlib
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData, UploadFile
from starlette.responses import Response

from . import __version__
from .adapters import ArrClient
from .domain import Options, ServiceConfig, ServiceError
from .engine import Engine
from .i18n import LANGUAGES, LOCALES, translate
from .migration import apply_import, parse_legacy, public_report
from .locking import ProcessLock
from .store import Store
from .telegram_bot import TelegramUI

logger = logging.getLogger("addarr.web")
hasher = PasswordHasher()
ROOT = Path(__file__).parent


def create_app(
    directory: Path | None = None,
    *,
    background: bool = True,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the web app without opening its database or starting workers.

    Args:
        directory: Data directory; defaults to ADDARR_DATA_DIR or /config.
        background: Start request and Telegram workers during lifespan startup.
            Tests may disable these to drive the engine directly.
        transport: Optional Arr HTTP transport for isolated integration tests.

    Returns:
        A FastAPI application. Its lifespan owns the process lock, database,
        HTTP client and worker tasks, and closes them on shutdown.
    """
    data_dir = directory or Path(os.getenv("ADDARR_DATA_DIR", "/config"))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Acquire application resources and cancel workers before closing HTTP and database connections."""
        with closing(ProcessLock(data_dir)), closing(Store(data_dir)) as store:
            app.state.store = store
            app.state.attempts = {}
            app.state.dummy_hash = await asyncio.to_thread(hasher.hash, secrets.token_urlsafe(32))
            if not store.one("SELECT id FROM admins LIMIT 1"):
                store.bootstrap_token()
                logger.info("setup_required bootstrap_file=%s", data_dir / "bootstrap-token")
            async with httpx.AsyncClient(transport=transport, follow_redirects=False) as http:
                engine = Engine(store, http)
                telegram = TelegramUI(engine)
                app.state.engine, app.state.telegram = engine, telegram
                tasks = (
                    [asyncio.create_task(engine.run()), asyncio.create_task(telegram.run())]
                    if background
                    else []
                )
                app.state.tasks = tasks
                try:
                    yield
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(
        title="Addarr",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=ROOT / "templates")

    def store(request: Request) -> Store:
        """Return the database connection owned by this application lifespan."""
        return request.app.state.store

    def locale(request: Request) -> str:
        """Resolve language from query, cookie or settings, with English as the fallback."""
        value = (
            request.query_params.get("lang")
            or request.cookies.get("language")
            or store(request).setting("language", "en-us")
        )
        return value if value in LOCALES else "en-us"

    def admin(request: Request) -> dict[str, Any]:
        """Resolve an unexpired session digest or raise HTTP 401; raw session tokens are not stored."""
        digest = hashlib.sha256(request.cookies.get("session", "").encode()).hexdigest()
        row = store(request).one(
            "SELECT admins.* FROM sessions JOIN admins ON admins.id=sessions.admin_id "
            "WHERE token=? AND expires>?",
            (digest, time.time()),
        )
        if not row:
            raise HTTPException(401, "Authentication required")
        return row

    async def form(request: Request, authenticated: bool = True) -> FormData:
        """Read a bounded form and validate its CSRF token and supplied Origin header.

        Authentication is required except for setup and login. Those routes still
        require the form token and origin checks.
        """
        if authenticated:
            admin(request)
        if int(request.headers.get("content-length", "0")) > 1_100_000:
            raise HTTPException(413, "Request too large")
        data = await request.form(max_files=4, max_fields=60, max_part_size=1_000_000)
        expected = request.cookies.get("csrf", "")
        if not expected or not secrets.compare_digest(str(data.get("csrf", "")), expected):
            raise HTTPException(403, "Invalid form token")
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Unexpected form origin")
        return data

    def page(request: Request, section: str, **extra: Any) -> Response:
        """Render a localized page with a CSRF cookie and disable response caching."""
        language = locale(request)
        csrf = request.cookies.get("csrf") or secrets.token_urlsafe(32)
        context = {
            "section": section,
            "csrf": csrf,
            "version": __version__,
            "locale": language,
            "languages": list(zip(LOCALES, LANGUAGES, strict=True)),
            "t": lambda key: translate(language, key),
            **extra,
        }
        response = templates.TemplateResponse(request=request, name="app.html", context=context)
        response.set_cookie(
            "csrf", csrf, httponly=True, samesite="strict", secure=request.url.scheme == "https"
        )
        response.set_cookie("language", language, samesite="strict")
        response.headers["Cache-Control"] = "no-store"
        return response

    def session(request: Request, admin_id: int) -> Response:
        """Persist a twelve-hour session digest, rotate CSRF and redirect with the session cookie."""
        token = secrets.token_urlsafe(48)
        st = store(request)
        st.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
        st.execute(
            "INSERT INTO sessions VALUES(?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), admin_id, time.time() + 12 * 3600),
        )
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            "session",
            token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=12 * 3600,
        )
        response.set_cookie(
            "csrf",
            secrets.token_urlsafe(32),
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
        )
        return response

    def throttle(request: Request) -> None:
        """Limit setup and login attempts per client address to ten within fifteen minutes."""
        key = request.client.host if request.client else "local"
        now = time.time()
        attempts = request.app.state.attempts
        for host in list(attempts):
            attempts[host] = [v for v in attempts[host] if now - v < 900]
            if not attempts[host]:
                del attempts[host]
        times = attempts.setdefault(key, [])
        if len(times) >= 10:
            raise HTTPException(429, "Too many authentication attempts; wait 15 minutes")
        times.append(now)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        """Apply same-origin content restrictions and block framing of app responses."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        """Redirect expired sessions to login and render other HTTP errors with their status."""
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        response = page(request, "error", error=translate(locale(request), "error"), detail=str(exc.detail))
        response.status_code = exc.status_code
        return response

    @app.exception_handler(ValueError)
    @app.exception_handler(ServiceError)
    async def action_error(request: Request, exc: Exception) -> Response:
        # Do not render Pydantic inputs: validation errors may contain API keys.
        """Show safe service errors while omitting validation inputs that may contain credentials."""
        response = page(
            request,
            "error",
            error=translate(locale(request), "error"),
            detail=str(exc)
            if isinstance(exc, ServiceError)
            else "Invalid or conflicting input; check your selections",
        )
        response.status_code = 400
        return response

    @app.exception_handler(PermissionError)
    async def permission_error(request: Request, exc: PermissionError) -> Response:
        """Render a generic access-denied page without revealing authorization details."""
        response = page(request, "error", error=translate(locale(request), "error"), detail="Access denied")
        response.status_code = 403
        return response

    @app.get("/health/live")
    async def live() -> dict[str, bool]:
        """Report that the HTTP process can answer requests; no dependency checks are performed."""
        return {"ok": True}

    @app.get("/health/ready")
    async def ready(request: Request) -> Response:
        """Report whether every configured background task is still running."""
        tasks = request.app.state.tasks
        ok = not any(task.done() for task in tasks)
        return JSONResponse({"ok": ok}, status_code=200 if ok else 503)

    @app.get("/login")
    async def login_page(request: Request) -> Response:
        """Render the login form and issue its CSRF token."""
        return page(request, "login")

    @app.post("/login")
    async def login(request: Request) -> Response:
        """Verify credentials off the event loop, apply rate limits and issue an admin session."""
        data = await form(request, False)
        throttle(request)
        row = store(request).one("SELECT * FROM admins WHERE username=?", (str(data.get("username", "")),))
        try:
            # A fixed dummy hash keeps nonexistent users on the password-verification path.
            password_hash = row["password"] if row else request.app.state.dummy_hash
            await asyncio.to_thread(hasher.verify, password_hash, str(data.get("password", "")))
        except VerificationError:
            raise HTTPException(403, "Invalid credentials") from None
        if not row:
            raise HTTPException(403, "Invalid credentials")
        return session(request, row["id"])

    @app.post("/logout")
    async def logout(request: Request) -> Response:
        """Delete the current session from SQLite and clear its browser cookie."""
        await form(request)
        store(request).execute(
            "DELETE FROM sessions WHERE token=?",
            (hashlib.sha256(request.cookies.get("session", "").encode()).hexdigest(),),
        )
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("session")
        return response

    @app.get("/setup")
    async def setup_page(request: Request) -> Response:
        """Show first-run setup only while no administrator exists."""
        if store(request).one("SELECT id FROM admins LIMIT 1"):
            return RedirectResponse("/login", status_code=303)
        return page(request, "setup")

    @app.post("/setup")
    async def setup(request: Request) -> Response:
        """Validate the bootstrap token, create the first administrator and remove the token file."""
        data = await form(request, False)
        throttle(request)
        st = store(request)
        if st.one("SELECT id FROM admins LIMIT 1"):
            raise HTTPException(409, "Setup already completed")
        if not secrets.compare_digest(str(data.get("bootstrap", "")), st.bootstrap_token()):
            raise HTTPException(403, "Invalid bootstrap token")
        username, password = str(data.get("username", "")).strip(), str(data.get("password", ""))
        if not username or len(username) > 100 or len(password) < 12 or len(password) > 1024:
            raise ValueError("Invalid credentials")
        password_hash = await asyncio.to_thread(hasher.hash, password)
        with st.transaction():
            if st.one("SELECT id FROM admins LIMIT 1"):
                raise HTTPException(409, "Setup already completed")
            cursor = st.execute(
                "INSERT INTO admins(username,password) VALUES(?,?)", (username, password_hash)
            )
            st.audit(username, "setup_complete")
        (st.directory / "bootstrap-token").unlink(missing_ok=True)
        assert cursor.lastrowid is not None
        return session(request, cursor.lastrowid)

    @app.get("/")
    async def overview(request: Request) -> Response:
        """Render request counts, recent requests and cached service status for an administrator."""
        if not store(request).one("SELECT id FROM admins LIMIT 1"):
            return RedirectResponse("/setup", status_code=303)
        admin(request)
        st = store(request)
        recent_requests = st.all(
            "SELECT requests.*,users.name FROM requests JOIN users ON users.id=requests.user_id "
            "ORDER BY requests.id DESC LIMIT 5"
        )
        for row in recent_requests:
            row["media"] = json.loads(row["media"])
        return page(
            request,
            "dashboard",
            counts={
                r["state"]: r["n"] for r in st.all("SELECT state,COUNT(*) n FROM requests GROUP BY state")
            },
            health=request.app.state.engine.health,
            polling=st.setting("polling_enabled", False),
            online=request.app.state.telegram.online,
            pending_users=st.all("SELECT COUNT(*) n FROM users WHERE status='pending'")[0]["n"],
            recent_requests=recent_requests,
        )

    @app.get("/requests")
    async def requests_page(request: Request) -> Response:
        """Show requests in pages of fifty, newest first."""
        admin(request)
        offset = max(0, int(request.query_params.get("offset", "0")))
        rows = store(request).all(
            "SELECT requests.*,users.name FROM requests JOIN users ON users.id=requests.user_id "
            "ORDER BY requests.id DESC LIMIT 50 OFFSET ?",
            (offset,),
        )
        for row in rows:
            row["media"] = json.loads(row["media"])
        return page(request, "requests", requests=rows, offset=offset)

    @app.post("/requests/{request_id}/{action}")
    async def request_action(request: Request, request_id: int, action: str) -> Response:
        """Authenticate a form action and let the engine validate the requested state transition."""
        await form(request)
        request.app.state.engine.action(request_id, action, admin(request)["username"], web_admin=True)
        return RedirectResponse("/requests", status_code=303)

    @app.get("/users")
    async def users_page(request: Request) -> Response:
        """List Telegram users and their current access policies."""
        admin(request)
        return page(request, "users", users=store(request).all("SELECT * FROM users ORDER BY status,id"))

    @app.post("/users/{user_id}")
    async def user_update(request: Request, user_id: int) -> Response:
        """Validate and save a Telegram user policy together with its audit event."""
        data = await form(request)
        status, role, language = str(data.get("status")), str(data.get("role")), str(data.get("locale"))
        if (
            status not in ("pending", "active", "revoked")
            or role not in ("member", "admin")
            or language not in LOCALES
        ):
            raise ValueError("Invalid user policy")
        st = store(request)
        with st.transaction():
            st.execute(
                "UPDATE users SET status=?,role=?,auto_approve=?,locale=? WHERE id=?",
                (status, role, int(data.get("auto_approve") == "on"), language, user_id),
            )
            st.audit(
                admin(request)["username"],
                "user_policy",
                detail=f"user_id={user_id} status={status} role={role}",
            )
        return RedirectResponse("/users", status_code=303)

    @app.post("/invite")
    async def invite(request: Request) -> Response:
        """Create a single-use, one-day Telegram invite, storing only its token digest."""
        await form(request)
        st = store(request)
        username = st.setting("bot_username")
        if not username:
            raise ValueError("Enable Telegram before creating an invite")
        token = secrets.token_urlsafe(24)
        st.execute(
            "INSERT INTO invites(token,expires) VALUES(?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), time.time() + 86400),
        )
        st.audit(admin(request)["username"], "invite_created")
        return page(
            request,
            "users",
            users=st.all("SELECT * FROM users ORDER BY status,id"),
            invite=f"https://t.me/{username}?start={token}",
        )

    async def service_page(
        request: Request, draft: ServiceConfig | None = None, caps: Any = None
    ) -> Response:
        """Render saved or draft configuration with live profile and folder choices.

        Each service has a six-second fetch limit. An unavailable service keeps
        its stored selections so opening the page cannot erase configuration.
        """
        configs = {
            kind: store(request).setting(f"service:{kind}", {}) for kind in ("radarr", "sonarr", "lidarr")
        }
        if draft:
            configs[draft.kind] = draft.model_dump(mode="json")
        capabilities: dict[str, Any] = {draft.kind: caps} if draft and caps else {}
        unavailable: set[str] = set()

        async def load_choices(kind: str, config: dict[str, Any]) -> None:
            if not config or kind in capabilities:
                return
            try:
                async with asyncio.timeout(6):
                    client = ArrClient(
                        ServiceConfig.model_validate(config), store(request), request.app.state.engine.http
                    )
                    capabilities[kind] = await client.capabilities()
            except (ServiceError, ValueError, TimeoutError, httpx.RequestError):
                unavailable.add(kind)

        await asyncio.gather(*(load_choices(kind, config) for kind, config in configs.items()))
        return page(
            request,
            "services",
            configs=configs,
            capabilities=capabilities,
            unavailable=unavailable,
            active_service=draft.kind if draft else "radarr",
        )

    @app.get("/services")
    async def services_page(request: Request) -> Response:
        """Authenticate the administrator and load service configuration with live choices."""
        admin(request)
        return await service_page(request)

    @app.post("/services/{kind}")
    async def service_update(request: Request, kind: str) -> Response:
        """Test a draft or save service settings, retaining secrets when fields are blank.

        A successful test stores an admin-bound draft in SQLite for fifteen-minute
        reuse by the save form. Saving an enabled service validates its defaults
        against the remote API before replacing the active configuration.
        """
        data = await form(request)
        if kind not in ("radarr", "sonarr", "lidarr"):
            raise ValueError("Unknown service")
        old = store(request).setting(f"service:{kind}", {})
        draft_key = request.cookies.get(f"draft_{kind}", "")
        draft = store(request).setting(f"draft:{draft_key}")
        if draft and draft["admin"] == admin(request)["id"] and draft["expires"] > time.time():
            old = draft["config"]
        config = ServiceConfig.model_validate(
            dict(
                kind=kind,
                url=str(data.get("url", "")),
                api_key=str(data.get("api_key") or old.get("api_key", "")),
                username=str(data.get("username", "")),
                password=str(data.get("password") or old.get("password", "")),
                enabled=data.get("enabled") == "on",
                quality_profile=int(str(data["quality_profile"])) if data.get("quality_profile") else None,
                root_folder=str(data.get("root_folder", "")),
                metadata_profile=int(str(data["metadata_profile"])) if data.get("metadata_profile") else None,
                allowed_profiles=[int(str(v)) for v in data.getlist("allowed_profiles")],
                allowed_folders=[str(v) for v in data.getlist("allowed_folders")],
                search=data.get("search") == "on",
                tags=[t.strip() for t in str(data.get("tags", "")).split(",") if t.strip()],
                requester_tag=data.get("requester_tag") == "on",
                season_folder=data.get("season_folder") == "on",
                minimum_availability=str(data.get("minimum_availability", "released")),
            )
        )
        client = ArrClient(config, store(request), request.app.state.engine.http)
        if data.get("action") == "test":
            caps = await client.capabilities()
            # Keep tested credentials in a server-side draft so the save form need not echo them.
            draft_id = secrets.token_urlsafe(16)
            store(request).set_setting(
                f"draft:{draft_id}",
                {
                    "admin": admin(request)["id"],
                    "expires": time.time() + 900,
                    "config": config.model_dump(mode="json"),
                },
            )
            response = await service_page(request, config, caps)
            response.set_cookie(f"draft_{kind}", draft_id, httponly=True, samesite="strict", max_age=900)
            return response
        if config.enabled:
            await client.validate_options(Options())
        store(request).set_setting(f"service:{kind}", config.model_dump(mode="json"))
        if draft:
            store(request).execute("DELETE FROM settings WHERE key=?", (f"draft:{draft_key}",))
        store(request).audit(admin(request)["username"], "service_updated", detail=kind)
        await request.app.state.engine.check_health()
        return RedirectResponse(f"/services#{kind}", status_code=303)

    @app.get("/settings")
    async def settings_page(request: Request) -> Response:
        """Render request approval, polling and notification settings."""
        admin(request)
        return page(
            request,
            "settings",
            auto_approve_all=store(request).setting("auto_approve_all", False),
            polling=store(request).setting("polling_enabled", False),
            notifications={
                key: store(request).setting(key, True)
                for key in ("notify_requests", "notify_availability", "notify_failures")
            },
        )

    @app.post("/settings/requests")
    async def request_settings_update(request: Request) -> Response:
        """Save and audit automatic approval for new requests; existing requests keep their state."""
        data = await form(request)
        st = store(request)
        enabled = data.get("auto_approve_all") == "on"
        with st.transaction():
            st.set_setting("auto_approve_all", enabled)
            st.audit(
                admin(request)["username"], "request_policy_updated", detail=f"auto_approve_all={enabled}"
            )
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings")
    async def settings_update(request: Request) -> Response:
        """Save Telegram and notification settings, checking service defaults before enabling polling."""
        data = await form(request)
        st = store(request)
        token = str(data.get("token") or st.setting("telegram_token", ""))
        language = str(data.get("language", "en-us"))
        if language not in LOCALES:
            raise ValueError("Invalid language")
        enabled = data.get("polling") == "on"
        if enabled:
            if not token:
                raise ValueError("Bot token required")
            count = 0
            for kind in ("radarr", "sonarr", "lidarr"):
                config = st.setting(f"service:{kind}", {})
                if config.get("enabled"):
                    await request.app.state.engine.client(kind).validate_options(Options())
                    count += 1
            if not count:
                raise ValueError("Configure at least one service first")
        with st.transaction():
            st.set_setting("telegram_token", token)
            st.set_setting("polling_enabled", enabled)
            st.set_setting("language", language)
            for key in ("notify_requests", "notify_availability", "notify_failures"):
                st.set_setting(key, data.get(key) == "on")
            st.audit(admin(request)["username"], "settings_updated")
        return RedirectResponse("/settings", status_code=303)

    @app.get("/migration")
    async def migration_page(request: Request) -> Response:
        """Render the legacy import form for an authenticated administrator."""
        admin(request)
        return page(request, "migration")

    @app.post("/migration/preview")
    async def migration_preview(request: Request) -> Response:
        """Parse uploaded legacy files, retain the private report and render a credential-free preview."""
        data = await form(request)
        content = data.get("config")
        if not isinstance(content, UploadFile):
            raise ValueError("Select a YAML file")
        raw = (await content.read(1_000_001)).decode("utf-8-sig")
        lists = {}
        for name in ("admin.txt", "allowlist.txt", "chatid.txt"):
            upload = data.get(name)
            if isinstance(upload, UploadFile) and upload.filename:
                lists[name] = (await upload.read(100_001)).decode("utf-8-sig")
        report = parse_legacy(raw, lists)
        store(request).set_setting(f"import:{admin(request)['id']}", report)
        return page(request, "migration", report=public_report(report))

    @app.post("/migration/apply")
    async def migration_apply(request: Request) -> Response:
        """Apply the administrator preview only if its submitted digest still matches."""
        data = await form(request)
        key = f"import:{admin(request)['id']}"
        report = store(request).setting(key)
        if not report or str(data.get("digest")) != report["digest"]:
            raise ValueError("Import preview expired")
        apply_import(store(request), report)
        store(request).execute("DELETE FROM settings WHERE key=?", (key,))
        return RedirectResponse("/users", status_code=303)

    @app.get("/diagnostics")
    async def diagnostics(request: Request) -> Response:
        """Show cached health, worker status, uncertain operations and recent audit events."""
        admin(request)
        st, engine = store(request), request.app.state.engine
        return page(
            request,
            "diagnostics",
            health=engine.health,
            worker={
                "last_tick": engine.last_tick,
                "telegram": request.app.state.telegram.online,
                "telegram_error": request.app.state.telegram.last_error,
            },
            operations=st.all("SELECT * FROM operations WHERE state='uncertain'"),
            outbox=st.all("SELECT state,COUNT(*) n FROM outbox GROUP BY state"),
            events=st.all("SELECT * FROM events ORDER BY id DESC LIMIT 100"),
        )

    @app.get("/diagnostics/health")
    async def health_fragment(request: Request) -> Response:
        """Render the authenticated status fragment used by periodic browser refreshes."""
        admin(request)
        engine = request.app.state.engine
        return templates.TemplateResponse(
            request=request,
            name="health.html",
            context={
                "t": lambda key: translate(locale(request), key),
                "health": engine.health,
                "worker": {
                    "last_tick": engine.last_tick,
                    "telegram": request.app.state.telegram.online,
                    "telegram_error": request.app.state.telegram.last_error,
                },
            },
        )

    @app.post("/backup")
    async def backup(request: Request) -> Response:
        """Create a consistent SQLite backup and return it as an authenticated file download."""
        await form(request)
        directory = store(request).directory / "backups"
        directory.mkdir(exist_ok=True)
        destination = directory / f"addarr-{time.time_ns()}.db"
        store(request).backup(destination)
        return FileResponse(
            destination,
            filename=destination.name,
            media_type="application/octet-stream",
            headers={"Cache-Control": "no-store"},
        )

    return app
