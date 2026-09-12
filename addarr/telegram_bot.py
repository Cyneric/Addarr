"""
Filename: telegram_bot.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Private and allowed-group commands, media selection and queued Telegram notifications.
"""

import asyncio
import hashlib
import html
import json
import logging
import secrets
import time
from typing import Any

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup as Keyboard
from telegram import ForceReply, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.request import BaseRequest

from .domain import Options, SearchResult, ServiceError
from .engine import Engine
from .i18n import LANGUAGES, LOCALES, translate

logger = logging.getLogger("addarr.telegram")


class TelegramUI:
    """Telegram conversations and notification delivery backed by the shared engine.

    Selection screens are temporary user/chat/topic state with expiring nonces.
    Submitted requests and notifications live in SQLite and survive restarts.
    """
    def __init__(self, engine: Engine):
        self.engine, self.store = engine, engine.store
        self.screens: dict[tuple[int, int, int | None], dict[str, Any]] = {}
        self.application: Any = None
        self.online = False
        self.last_error = ""

    def locale(self, user_id: int) -> str:
        """Use the saved user language, or the installation language for a new user."""
        user = self.store.user(user_id)
        return user["locale"] if user else self.store.setting("language", "en-us")

    def t(self, user_id: int, key: str, **values: object) -> str:
        """Translate and format a message using the recipient language."""
        return translate(self.locale(user_id), key, **values)

    def group_id(self, update: Update) -> int | None:
        """Return a group origin, leaving private conversations without a group grant."""
        chat = update.effective_chat
        return chat.id if chat and chat.type in ("group", "supergroup") else None

    def screen_key(self, update: Update, uid: int) -> tuple[int, int, int | None]:
        """Keep each user's selections separate across chats and forum topics."""
        assert update.effective_chat and update.effective_message
        return update.effective_chat.id, uid, update.effective_message.message_thread_id

    def keyboard(self, update: Update, rows: list[list[Button]]) -> Keyboard:
        """Bind every group button, including navigation, to the initiating user."""
        if self.group_id(update) is None:
            return Keyboard(rows)
        assert update.effective_user
        return Keyboard([
            [Button(button.text, callback_data=f"g:{update.effective_user.id}:{button.callback_data}")
             for button in row] for row in rows
        ])

    async def render(self, update: Update, text: str, rows: list[list[Button]] | None = None) -> None:
        """Edit the current callback message when possible, otherwise send a reply with its keyboard."""
        if not update.effective_message:
            return
        keyboard = self.keyboard(update, rows or [])
        if update.callback_query:
            try:
                if update.effective_message.photo:
                    await update.effective_message.edit_caption(caption=text[:1000], reply_markup=keyboard)
                else:
                    await update.effective_message.edit_text(text[:4000], reply_markup=keyboard)
                return
            except TelegramError:
                pass
        await update.effective_message.reply_text(text[:4000], reply_markup=keyboard)

    async def receive(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check chat access and callback ownership before touching conversation state.

        Group searches accept replies only to the user's current search prompt,
        so normal conversation cannot become a search when privacy is disabled.
        Anonymous senders and channel posts have no usable requester identity.
        """
        if not update.effective_user or not update.effective_chat or not update.effective_message:
            return
        if update.effective_user.is_bot or update.effective_message.sender_chat:
            return
        group = self.group_id(update)
        if group and (update.effective_message.text or "").split("@", 1)[0] == "/chatid":
            await update.effective_message.reply_text(str(group))
            return
        if update.effective_chat.type != "private" and not self.store.group_allowed(group):
            if update.callback_query:
                await update.callback_query.answer()
            return
        uid = update.effective_user.id
        data = update.callback_query.data or "" if update.callback_query else ""
        if group and update.callback_query:
            prefix = f"g:{uid}:"
            if not data.startswith(prefix):
                await update.callback_query.answer(self.t(uid, "own_buttons"))
                return
            data = data[len(prefix):]
        if group and not update.callback_query and not (update.effective_message.text or "").startswith("/"):
            screen = self.screens.get(self.screen_key(update, uid))
            reply = update.effective_message.reply_to_message
            if (not screen or screen["expires"] <= time.time() or not reply
                    or reply.message_id != screen.get("prompt_id")):
                return
        if update.callback_query:
            await update.callback_query.answer()
        try:
            await self.dispatch(update, uid, data)
        except PermissionError:
            await self.render(update, self.t(uid, "access_pending"))
        except (ServiceError, ValueError, KeyError, IndexError) as exc:
            await self.render(
                update, self.t(uid, "already_in_library" if isinstance(exc, ServiceError)
                               and exc.category == "already_exists" else "error"),
                [[Button(self.t(uid, "back"), callback_data="home")]],
            )
        except TelegramError:
            logger.warning("telegram_reply_failed user_id=%s", uid)

    async def dispatch(self, update: Update, uid: int, data: str | None = None) -> None:
        """Route an accepted update after registering its sender and handling a private invite.

        Invites activate a member without automatic request approval. All later
        commands require active access, and expired selection screens are removed.
        The receive() handler checks the chat allowlist and callback owner first.
        """
        assert update.effective_message and update.effective_user
        screen: dict[str, Any] | None
        text = update.effective_message.text or "" if update.effective_message else ""
        data = data if data is not None else (update.callback_query.data or "" if update.callback_query else "")
        command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
        self.store.execute(
            "INSERT OR IGNORE INTO users(id,name,locale) VALUES(?,?,?)",
            (
                uid,
                update.effective_user.full_name if update.effective_user else str(uid),
                self.store.setting("language", "en-us"),
            ),
        )
        if self.group_id(update) is None:
            self.store.execute("UPDATE users SET chat_id=? WHERE id=?", (uid, uid))
        if command == "/start" and len(text.split()) == 2 and self.group_id(update) is None:
            digest = hashlib.sha256(text.split()[1].encode()).hexdigest()
            with self.store.transaction():
                invite = self.store.one(
                    "SELECT * FROM invites WHERE token=? AND used=0 AND expires>?", (digest, time.time())
                )
                current_user = self.store.user(uid)
                if invite and current_user and current_user["status"] != "active":
                    self.store.execute("UPDATE invites SET used=1 WHERE token=?", (digest,))
                    self.store.execute(
                        "UPDATE users SET status='active',role='member',auto_approve=0 WHERE id=?", (uid,)
                    )
                    self.store.audit(str(uid), "invite_redeemed")
        self.engine.authorize(uid, chat_id=self.group_id(update))
        self.screens = {key: val for key, val in self.screens.items() if val["expires"] > time.time()}
        if command in ("/start", "/auth") or data == "home":
            self.screens.pop(self.screen_key(update, uid), None)
            rows = []
            for kind, service in (
                ("movie", "radarr"),
                ("series", "sonarr"),
                ("artist", "lidarr"),
                ("album", "lidarr"),
            ):
                if self.store.setting(f"service:{service}", {}).get("enabled"):
                    rows.append([Button(self.t(uid, kind), callback_data=f"new:{kind}")])
            rows.extend(
                [
                    [Button(self.t(uid, "requests"), callback_data="requests")],
                    [Button(self.t(uid, "language"), callback_data="language")],
                ]
            )
            await self.render(update, self.t(uid, "welcome"), rows)
        elif data == "language":
            await self.render(
                update,
                self.t(uid, "language"),
                [
                    [Button(label, callback_data=f"lang:{locale}")]
                    for locale, label in zip(LOCALES, LANGUAGES, strict=True)
                ],
            )
        elif data.startswith("lang:"):
            locale = data.split(":")[1]
            if locale not in LOCALES:
                raise ValueError("Invalid locale")
            self.store.execute("UPDATE users SET locale=? WHERE id=?", (locale, uid))
            await self.render(
                update, self.t(uid, "language"), [[Button(self.t(uid, "back"), callback_data="home")]]
            )
        elif command == "/cancel" or data == "cancel":
            self.screens.pop(self.screen_key(update, uid), None)
            await self.render(
                update, self.t(uid, "cancelled"), [[Button(self.t(uid, "back"), callback_data="home")]]
            )
        elif command == "/help":
            await self.render(update, self.t(uid, "help"))
        elif command == "/status":
            await self.render(
                update,
                "\n".join(f"{k}: {'✓' if v['ok'] else '✕'}" for k, v in self.engine.health.items())
                or self.t(uid, "empty"),
            )
        elif command == "/requests" or data == "requests":
            await self.requests(update, uid)
        elif data.startswith("r:"):
            _, action, request_id = data.split(":")
            self.engine.action(
                int(request_id), action, str(uid), user_id=uid,
                chat_id=self.group_id(update), thread_id=update.effective_message.message_thread_id,
            )
            await self.requests(update, uid)
        elif command in ("/movie", "/series", "/music") or data.startswith("new:"):
            kind = (
                data.split(":")[1]
                if data
                else {"/movie": "movie", "/series": "series", "/music": "artist"}[command]
            )
            self.screens[self.screen_key(update, uid)] = {
                "kind": kind,
                "nonce": secrets.token_hex(4),
                "expires": time.time() + 900,
                "results": [],
                "selected": None,
                "options": Options(),
            }
            screen = self.screens[self.screen_key(update, uid)]
            term = text.split(maxsplit=1)[1] if command and len(text.split(maxsplit=1)) == 2 else ""
            if term:
                service = {"movie": "radarr", "series": "sonarr", "artist": "lidarr", "album": "lidarr"}[kind]
                screen["results"] = await self.engine.search(uid, service, term, kind, chat_id=self.group_id(update))
                await self.results(update, uid, screen)
            elif self.group_id(update):
                assert update.effective_message
                prompt = await update.effective_message.reply_text(
                    f'<a href="tg://user?id={uid}">{html.escape(update.effective_user.first_name)}</a>\n'
                    + html.escape(self.t(uid, "group_search")),
                    parse_mode="HTML", reply_markup=ForceReply(selective=True), do_quote=True,
                )
                screen["prompt_id"] = prompt.message_id
            else:
                await self.render(
                    update, self.t(uid, "search"), [[Button(self.t(uid, "cancel"), callback_data="cancel")]]
                )
        elif data.startswith("s:"):
            await self.selection(update, uid, data)
        elif not command and not data:
            screen = self.screens.get(self.screen_key(update, uid))
            if not screen:
                await self.render(update, self.t(uid, "expired"))
                return
            kind = screen["kind"]
            service = {"movie": "radarr", "series": "sonarr", "artist": "lidarr", "album": "lidarr"}[kind]
            screen["results"] = await self.engine.search(uid, service, text, kind, chat_id=self.group_id(update))
            await self.results(update, uid, screen)
        else:
            await self.render(update, self.t(uid, "expired"))

    def button(self, uid: int, screen: dict[str, Any], label: str, action: str) -> Button:
        """Build a translated selection button bound to the current screen nonce."""
        return Button(self.t(uid, label), callback_data=f"s:{screen['nonce']}:{action}")

    async def results(self, update: Update, uid: int, screen: dict[str, Any]) -> None:
        """Render search results as nonce-bound selection buttons with a cancel action."""
        rows = [
            [Button(result.ref.title[:55] + (" · " + self.t(uid, "in_library") if result.in_library else ""),
                    callback_data=f"s:{screen['nonce']}:pick:{i}")]
            for i, result in enumerate(screen["results"])
        ]
        rows.append([Button(self.t(uid, "cancel"), callback_data="cancel")])
        await self.render(
            update, self.t(uid, screen["kind"]) if screen["results"] else self.t(uid, "empty"), rows
        )

    async def selection(self, update: Update, uid: int, data: str) -> None:
        """Handle a media selection callback for the current user, chat and topic.

        Reject an old nonce, then update selection or options, render a preview,
        or create the confirmed request through the engine. dispatch() removes
        expired screens before reaching this handler.
        """
        assert update.effective_message
        parts = data.split(":")
        screen = self.screens.get(self.screen_key(update, uid))
        if not screen or parts[1] != screen["nonce"]:
            await self.render(update, self.t(uid, "expired"))
            return
        action = parts[2]
        if action == "results":
            await self.results(update, uid, screen)
            return
        if action == "pick":
            screen["selected"] = screen["results"][int(parts[3])]
            screen["options"] = Options()
        selected: SearchResult = screen["selected"]
        if not selected:
            raise ValueError("No selection")
        opts: Options = screen["options"]
        if action == "confirm":
            request_id = await self.engine.create(
                uid, selected.ref, opts, chat_id=self.group_id(update),
                thread_id=update.effective_message.message_thread_id if self.group_id(update) else None,
            )
            self.screens.pop(self.screen_key(update, uid), None)
            row = self.store.one("SELECT state FROM requests WHERE id=?", (request_id,))
            assert row is not None
            await self.render(
                update,
                f"#{request_id} · {selected.ref.title}\n{self.t(uid, row['state'])}",
                [[Button(self.t(uid, "requests"), callback_data="requests")]],
            )
            return
        client = self.engine.client(selected.ref.service)
        in_library = await client.already_in_library(selected.ref, opts)
        if in_library and selected.ref.kind in ("movie", "album"):
            await self.render(update, selected.ref.title + "\n" + self.t(uid, "already_in_library"), [
                [self.button(uid, screen, "back", "results")],
            ])
            return
        if action in ("advanced", "profile", "folder", "mode", "season"):
            client = self.engine.client(selected.ref.service)
            caps = await client.capabilities()
            profiles = [
                p
                for p in caps["profiles"]
                if not client.config.allowed_profiles or p["id"] in client.config.allowed_profiles
            ]
            folders = [
                p
                for p in caps["folders"]
                if not client.config.allowed_folders or p["path"] in client.config.allowed_folders
            ]
            if action == "profile":
                opts.quality_profile = profiles[int(parts[3])]["id"]
            elif action == "folder":
                opts.root_folder = folders[int(parts[3])]["path"]
            elif action == "mode":
                opts.monitoring = Options.model_validate({"monitoring": parts[3]}).monitoring
            elif action == "season":
                season = int(parts[3])
                if season not in selected.seasons:
                    raise ValueError("Invalid season")
                opts.seasons = sorted(set(opts.seasons) ^ {season})
                opts.monitoring = "selected"
            rows = [
                [
                    Button(
                        ("✓ " if opts.quality_profile == p["id"] else "")
                        + self.t(uid, "profile")
                        + ": "
                        + p["name"],
                        callback_data=f"s:{screen['nonce']}:profile:{i}",
                    )
                ]
                for i, p in enumerate(profiles)
            ]
            rows += [
                [
                    Button(
                        ("✓ " if opts.root_folder == p["path"] else "")
                        + self.t(uid, "folder")
                        + ": "
                        + p["path"],
                        callback_data=f"s:{screen['nonce']}:folder:{i}",
                    )
                ]
                for i, p in enumerate(folders)
            ]
            if selected.ref.kind in ("series", "artist"):
                rows += [
                    [self.button(uid, screen, mode, f"mode:{mode}")] for mode in ("all", "future", "none")
                ]
            if selected.ref.kind == "series":
                rows += [
                    [
                        Button(
                            ("✓ " if s in opts.seasons else "") + f"S{s}",
                            callback_data=f"s:{screen['nonce']}:season:{s}",
                        )
                    ]
                    for s in selected.seasons
                ]
            actions = [self.button(uid, screen, "back", "preview")]
            if not await client.already_in_library(selected.ref, opts):
                actions.insert(0, self.button(uid, screen, "confirm", "confirm"))
            rows.append(actions)
            await self.render(update, selected.ref.title + "\n" + self.t(uid, opts.monitoring), rows)
            return
        rows = [
            [self.button(uid, screen, "advanced", "advanced")],
            [
                self.button(uid, screen, "back", "results"),
                Button(self.t(uid, "cancel"), callback_data="cancel"),
            ],
        ]
        if not in_library:
            rows.insert(0, [self.button(uid, screen, "confirm", "confirm")])
        preview = selected.ref.title + "\n\n" + selected.overview[:700]
        if in_library:
            preview += "\n\n" + self.t(uid, "already_in_library")
            if selected.ref.kind == "series":
                preview += "\n" + self.t(uid, "missing_seasons")
        if action == "pick" and selected.image.startswith("https://") and update.effective_message:
            try:
                await update.effective_message.reply_photo(
                    selected.image, caption=preview[:1000], reply_markup=self.keyboard(update, rows)
                )
                return
            except TelegramError:
                pass
        await self.render(update, preview, rows)

    async def requests(self, update: Update, uid: int) -> None:
        """Show the latest ten visible requests and the actions allowed for their current states."""
        user = self.engine.authorize(uid, chat_id=self.group_id(update))
        group = self.group_id(update)
        if group:
            assert update.effective_message
            rows = self.store.all(
                "SELECT * FROM requests WHERE deleted=0 AND user_id=? AND chat_id=? AND thread_id IS ? ORDER BY id DESC LIMIT 10",
                (uid, group, update.effective_message.message_thread_id),
            )
        else:
            rows = self.store.all(
                "SELECT * FROM requests WHERE deleted=0 "
                + ("" if user["role"] == "admin" else "AND user_id=? ")
                + "ORDER BY id DESC LIMIT 10",
                () if user["role"] == "admin" else (uid,),
            )
        text, buttons = [], []
        for row in rows:
            from .downloads import download_text

            downloads = download_text(self.store, row, user["locale"])
            text.append(
                f"#{row['id']} · {json.loads(row['media'])['title']}\n{self.t(uid, row['state'])}\n{row['progress']}"
                + (f"\n{downloads}" if downloads else "")
            )
            actions = []
            if row["state"] == "pending" and user["role"] == "admin":
                actions += ["approve", "reject"]
            if row["state"] == "failed" and user["role"] == "admin":
                actions += ["retry"]
            if row["state"] in ("pending", "queued"):
                actions += ["cancel"]
            if actions:
                buttons.append(
                    [
                        Button(f"#{row['id']} {self.t(uid, a)}", callback_data=f"r:{a}:{row['id']}")
                        for a in actions
                    ]
                )
        buttons.append([Button(self.t(uid, "back"), callback_data="home")])
        await self.render(update, "\n\n".join(text) or self.t(uid, "no_requests"), buttons)

    async def deliver(self) -> None:
        """Attempt up to ten due outbox messages for active recipients.

        Honor Telegram retry delays; stop after twelve failed attempts or a
        forbidden recipient. A crash after send but before recording success can
        deliver a message again, so this is not exactly-once delivery.
        """
        for row in self.store.all(
            "SELECT * FROM outbox WHERE state='pending' AND next_attempt<=? ORDER BY id LIMIT 10",
            (time.time(),),
        ):
            # Another send may have yielded while an admin deleted this request.
            if not self.store.one("SELECT id FROM outbox WHERE id=? AND state='pending'", (row["id"],)):
                continue
            if row["chat_id"] < 0:
                user = self.store.one(
                    "SELECT users.status FROM users JOIN requests ON requests.user_id=users.id "
                    "JOIN events ON events.request_id=requests.id WHERE events.id=? AND requests.chat_id=?",
                    (row["event_id"], row["chat_id"]),
                )
                allowed = self.store.group_allowed(row["chat_id"]) and bool(user and user["status"] != "revoked")
            else:
                user = self.store.one("SELECT status FROM users WHERE chat_id=?", (row["chat_id"],))
                allowed = bool(user and user["status"] == "active")
            if not allowed:
                self.store.execute("UPDATE outbox SET state='discarded' WHERE id=?", (row["id"],))
                continue
            payload = json.loads(row["payload"])
            payload["state"] = translate(row["locale"], payload["state"])
            try:
                await self.application.bot.send_message(
                    row["chat_id"], translate(row["locale"], row["key"], **payload)[:4000],
                    message_thread_id=row["thread_id"],
                )
                self.store.execute("UPDATE outbox SET state='sent' WHERE id=?", (row["id"],))
            except Forbidden:
                self.store.execute("UPDATE outbox SET state='failed' WHERE id=?", (row["id"],))
            except TelegramError as exc:
                attempts = row["attempts"] + 1
                delay = min(3600, 2**attempts)
                if isinstance(exc, RetryAfter):
                    retry_after = exc.retry_after
                    delay = (
                        int(retry_after.total_seconds())
                        if hasattr(retry_after, "total_seconds")
                        else int(retry_after)
                    )
                self.store.execute(
                    "UPDATE outbox SET attempts=?,next_attempt=?,state=? WHERE id=?",
                    (attempts, time.time() + delay, "failed" if attempts >= 12 else "pending", row["id"]),
                )

    def build_application(self, token: str, request: BaseRequest | None = None) -> Any:
        """Build the sequential update dispatcher without starting polling.

        An optional BaseRequest substitutes the Telegram transport in tests.
        The supervisor owns initialization, startup and shutdown.
        """
        builder = Application.builder().token(token).concurrent_updates(False)
        if request is not None:
            builder = builder.request(request)
        application = builder.build()
        self.application = application
        application.add_handler(
            CommandHandler(
                ["start", "auth", "movie", "series", "music", "status", "help", "cancel", "requests", "chatid"],
                self.receive,
            )
        )
        application.add_handler(CallbackQueryHandler(self.receive))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive))

        async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
            logger.error("telegram_update_failed category=internal")

        application.add_error_handler(on_error)
        return application

    async def run(self) -> None:
        """Supervise polling and notification delivery until cancelled.

        Restart when the saved token or polling setting changes. Connection
        failures update diagnostics and retry after cleanup without logging tokens.
        """
        while True:
            token = self.store.setting("telegram_token", "")
            if not token or not self.store.setting("polling_enabled", False):
                await asyncio.sleep(2)
                continue
            application = None
            try:
                application = self.build_application(token)
                await application.initialize()
                self.store.set_setting("bot_username", application.bot.username)
                await application.start()
                assert application.updater is not None
                await application.updater.start_polling(allowed_updates=["message", "callback_query"])
                self.online, self.last_error = True, ""
                while token == self.store.setting("telegram_token") and self.store.setting("polling_enabled"):
                    await self.deliver()
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.last_error = "Telegram unavailable; check token and network"
                logger.warning("telegram_connection_failed")
            finally:
                self.online = False
                if application and application.updater and application.updater.running:
                    await application.updater.stop()
                if application and application.running:
                    await application.stop()
                if application:
                    await application.shutdown()
            await asyncio.sleep(5)
