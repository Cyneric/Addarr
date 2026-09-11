"""
Filename: test_telegram.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Telegram dispatcher checks for private access, media selection and notifications.
"""

import json
import asyncio
import hashlib
import time
from contextlib import asynccontextmanager

import pytest
from telegram import Update
from telegram.request import BaseRequest

from addarr.telegram_bot import TelegramUI


class TelegramTransport(BaseRequest):
    def __init__(self):
        self.sent = []

    @property
    def read_timeout(self):
        return 10

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, request_data=None, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        data = request_data.parameters if request_data else {}
        self.sent.append((endpoint, data))
        if endpoint == "getMe":
            result = {"id": 999, "is_bot": True, "first_name": "Addarr", "username": "addarr_test_bot"}
        elif endpoint in ("sendMessage", "editMessageText", "sendPhoto", "editMessageCaption"):
            result = {
                "message_id": len(self.sent),
                "date": 1,
                "chat": {"id": int(data.get("chat_id", 1)), "type": "private"},
                "text": data.get("text", data.get("caption", "")),
            }
        else:
            result = True
        return 200, json.dumps({"ok": True, "result": result}).encode()


@asynccontextmanager
async def bot(engine):
    transport = TelegramTransport()
    ui = TelegramUI(engine)
    app = ui.build_application("123:TEST", transport)
    failures = []

    async def error(update, context):
        failures.append(context.error)

    app.error_handlers.clear()
    app.add_error_handler(error)
    await app.initialize()
    try:
        yield app, ui, transport
        assert not failures, failures
    finally:
        await app.shutdown()


async def send(app, text="", data="", uid=2, chat_type="private"):
    user = {"id": uid, "is_bot": False, "first_name": "User"}
    message = {
        "message_id": 10,
        "date": 1,
        "chat": {"id": uid, "type": chat_type},
        "from": user,
        "text": text,
    }
    if text.startswith("/"):
        message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    raw = {"update_id": 100}
    if data:
        message["from"] = {"id": 999, "is_bot": True, "first_name": "Addarr"}
        raw["callback_query"] = {
            "id": "callback",
            "from": user,
            "chat_instance": "chat",
            "data": data,
            "message": message,
        }
    else:
        raw["message"] = message
    await app.process_update(Update.de_json(raw, app.bot))


@pytest.mark.parametrize(
    "kind,command", [("movie", "/movie"), ("series", "/series"), ("artist", "/music"), ("album", None)]
)
@pytest.mark.parametrize("entry", ["menu", "command"])
async def test_complete_conversation_through_dispatcher(engine, store, kind, command, entry):
    async with bot(engine) as (app, ui, transport):
        await send(app, "/start")
        if entry == "command" and command:
            await send(app, command)
        else:
            await send(app, data=f"new:{kind}")
        await send(app, "Example")
        nonce = ui.screens[2]["nonce"]
        await send(app, data=f"s:{nonce}:pick:0")
        await send(app, data=f"s:{nonce}:advanced")
        await send(app, data=f"s:{nonce}:profile:1")
        await send(app, data=f"s:{nonce}:folder:1")
        if kind == "series":
            await send(app, data=f"s:{nonce}:season:1")
        await send(app, data=f"s:{nonce}:confirm")
        rows = store.all("SELECT * FROM requests")
        assert len(rows) == 1
        assert json.loads(rows[0]["options"])["quality_profile"] == 2
        assert json.loads(rows[0]["options"])["root_folder"] == "/archive"
        if kind == "series":
            assert json.loads(rows[0]["options"])["seasons"] == [1]
        await send(app, data=f"s:{nonce}:confirm")
        assert len(store.all("SELECT * FROM requests")) == 1
        assert "expired" in transport.sent[-1][1]["text"]


async def test_cross_user_revocation_and_cancel(engine, store):
    async with bot(engine) as (app, ui, transport):
        await send(app, "/movie")
        await send(app, "Example")
        nonce = ui.screens[2]["nonce"]
        await send(app, data=f"s:{nonce}:pick:0", uid=1)
        assert "expired" in transport.sent[-1][1]["text"]
        await send(app, data=f"s:{nonce}:pick:0")
        store.execute("UPDATE users SET status='revoked' WHERE id=2")
        await send(app, data=f"s:{nonce}:confirm")
        assert not store.all("SELECT * FROM requests")
        store.execute("UPDATE users SET status='active' WHERE id=2")
        await send(app, "/cancel")
        assert 2 not in ui.screens


async def test_notifications_deliver_once_after_recorded_success(engine, store):
    async with bot(engine) as (app, ui, transport):
        await send(app, "/movie", uid=1)
        await send(app, "Example", uid=1)
        nonce = ui.screens[1]["nonce"]
        await send(app, data=f"s:{nonce}:pick:0", uid=1)
        await send(app, data=f"s:{nonce}:confirm", uid=1)
        await ui.deliver()
        before = len(transport.sent)
        await ui.deliver()
        assert len(transport.sent) == before
        assert all(r["state"] == "sent" for r in store.all("SELECT * FROM outbox"))


async def test_group_chat_ignored(engine, store):
    async with bot(engine) as (app, ui, transport):
        before = len(transport.sent)
        await send(app, "/movie", chat_type="group")
        assert len(transport.sent) == before
        assert not ui.screens


async def test_invalid_token_does_not_kill_supervisor(engine, store):
    ui = TelegramUI(engine)
    store.set_setting("telegram_token", "invalid")
    store.set_setting("polling_enabled", True)
    task = asyncio.create_task(ui.run())
    try:
        for _ in range(100):
            await asyncio.sleep(0.01)
            if ui.last_error:
                break
        assert not task.done()
        assert ui.last_error and not ui.online
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_invite_single_use_and_admin_preview_preserves_role(engine, store):
    token = "single-use-invite"
    digest = hashlib.sha256(token.encode()).hexdigest()
    store.execute("INSERT INTO invites(token,expires) VALUES(?,?)", (digest, time.time() + 60))
    async with bot(engine) as (app, ui, transport):
        await send(app, f"/start {token}", uid=2)
        assert store.user(2)["role"] == "admin"
        assert not store.one("SELECT used FROM invites WHERE token=?", (digest,))["used"]
        await send(app, f"/start {token}", uid=3)
        assert store.user(3)["status"] == "active"
        assert store.user(3)["role"] == "member"
        await send(app, f"/start {token}", uid=4)
        assert store.user(4)["status"] == "pending"
