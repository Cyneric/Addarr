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
                "chat": {"id": int(data.get("chat_id", 1)),
                         "type": "supergroup" if int(data.get("chat_id", 1)) < 0 else "private"},
                "from": {"id": 999, "is_bot": True, "first_name": "Addarr"},
                "message_thread_id": data.get("message_thread_id"),
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


async def send(app, text="", data="", uid=2, chat_type="private", chat_id=None, thread_id=None,
               reply_id=None, anonymous=False):
    user = {"id": uid, "is_bot": False, "first_name": "User"}
    message = {
        "message_id": 10,
        "date": 1,
        "chat": {"id": chat_id if chat_id is not None else uid, "type": chat_type},
        "from": user,
        "text": text,
    }
    if thread_id is not None:
        message.update(message_thread_id=thread_id, is_topic_message=True)
    if reply_id is not None:
        message["reply_to_message"] = {
            "message_id": reply_id, "date": 1, "chat": message["chat"],
            "from": {"id": 999, "is_bot": True, "first_name": "Addarr"}, "text": "Search",
        }
    if anonymous:
        message["sender_chat"] = message["chat"]
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
        nonce = ui.screens[(2, 2, None)]["nonce"]
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
        nonce = ui.screens[(2, 2, None)]["nonce"]
        await send(app, data=f"s:{nonce}:pick:0", uid=1)
        assert "expired" in transport.sent[-1][1]["text"]
        await send(app, data=f"s:{nonce}:pick:0")
        store.execute("UPDATE users SET status='revoked' WHERE id=2")
        await send(app, data=f"s:{nonce}:confirm")
        assert not store.all("SELECT * FROM requests")
        store.execute("UPDATE users SET status='active' WHERE id=2")
        await send(app, "/cancel")
        assert (2, 2, None) not in ui.screens


async def test_notifications_deliver_once_after_recorded_success(engine, store):
    async with bot(engine) as (app, ui, transport):
        await send(app, "/movie", uid=1)
        await send(app, "Example", uid=1)
        nonce = ui.screens[(1, 1, None)]["nonce"]
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


@pytest.mark.parametrize("chat_type", ["group", "supergroup"])
async def test_allowed_group_request_and_notifications(engine, store, fake, chat_type):
    """Group membership permits a request without granting private access."""
    group, uid = -100123456, 41
    store.set_setting("allowed_group_ids", [group])
    store.set_setting("auto_approve_all", True)
    async with bot(engine) as (app, ui, transport):
        async def group_send(text="", data="", **kwargs):
            await send(app, text, data, uid=uid, chat_type=chat_type, chat_id=group, **kwargs)

        await group_send("/movie@addarr_test_bot")
        key = group, uid, None
        prompt_id = ui.screens[key]["prompt_id"]
        assert store.user(uid)["status"] == "pending"
        assert store.user(uid)["chat_id"] is None
        await group_send("Example", reply_id=prompt_id)
        nonce = ui.screens[key]["nonce"]
        markup = transport.sent[-1][1]["reply_markup"]
        assert all(button["callback_data"].startswith(f"g:{uid}:")
                   for row in markup["inline_keyboard"] for button in row)
        await group_send(data=f"g:{uid}:s:{nonce}:pick:0")
        await group_send(data=f"g:{uid}:s:{nonce}:confirm")
        row = store.one("SELECT * FROM requests")
        assert row["user_id"] == uid and row["chat_id"] == group and row["state"] == "queued"
        await engine.tick()
        assert len(fake.items["movie"]) == 1
        before = len(transport.sent)
        await ui.deliver()
        targets = [int(data["chat_id"]) for endpoint, data in transport.sent[before:] if endpoint == "sendMessage"]
        assert group in targets and uid not in targets
        await send(app, "/movie", uid=uid)
        assert (uid, uid, None) not in ui.screens
        assert "approve your access" in transport.sent[-1][1]["text"]


async def test_group_buttons_reject_other_users_and_unbound_callbacks(engine, store):
    group = -100123456
    store.set_setting("allowed_group_ids", [group])
    async with bot(engine) as (app, ui, transport):
        await send(app, "/movie Example", uid=1, chat_type="supergroup", chat_id=group)
        key = group, 1, None
        nonce = ui.screens[key]["nonce"]
        for data in (f"g:1:s:{nonce}:pick:0", "g:1:cancel", "g:1:home", "g:1:new:movie", "new:movie"):
            before = len(transport.sent)
            await send(app, data=data, uid=2, chat_type="supergroup", chat_id=group)
            assert all(endpoint == "answerCallbackQuery" for endpoint, _ in transport.sent[before:])
            assert ui.screens[key]["selected"] is None
        assert not store.all("SELECT * FROM requests")


async def test_group_text_search_only_accepts_own_prompt_reply(engine, store, fake):
    group = -100123456
    store.set_setting("allowed_group_ids", [group])
    async with bot(engine) as (app, ui, transport):
        await send(app, "/movie", uid=1, chat_type="supergroup", chat_id=group)
        prompt_id = ui.screens[(group, 1, None)]["prompt_id"]
        before = len(transport.sent)
        for uid, reply in ((1, None), (1, 9876), (2, prompt_id)):
            await send(app, "Normal group chat", uid=uid, chat_type="supergroup", chat_id=group, reply_id=reply)
        assert len(transport.sent) == before
        assert not fake.calls
        await send(app, "Example", uid=1, chat_type="supergroup", chat_id=group, reply_id=prompt_id)
        assert ui.screens[(group, 1, None)]["results"]


async def test_group_private_and_topic_selections_are_isolated(engine, store):
    group = -100123456
    store.set_setting("allowed_group_ids", [group])
    async with bot(engine) as (app, ui, transport):
        await send(app, "/movie Private")
        await send(app, "/series Group", chat_type="supergroup", chat_id=group, thread_id=12)
        await send(app, "/movie Other topic", chat_type="supergroup", chat_id=group, thread_id=13)
        keys = {(2, 2, None), (group, 2, 12), (group, 2, 13)}
        assert set(ui.screens) == keys
        nonce = ui.screens[(group, 2, 12)]["nonce"]
        await send(app, data=f"g:2:s:{nonce}:pick:0", chat_type="supergroup", chat_id=group, thread_id=13)
        assert ui.screens[(group, 2, 13)]["selected"] is None
        await send(app, "/cancel", chat_type="supergroup", chat_id=group, thread_id=13)
        assert set(ui.screens) == keys - {(group, 2, 13)}
        for action in ("pick:0", "confirm"):
            await send(app, data=f"g:2:s:{nonce}:{action}", chat_type="supergroup", chat_id=group, thread_id=12)
        assert store.one("SELECT * FROM requests")["thread_id"] == 12
        before = len(transport.sent)
        await ui.deliver()
        sent = [data for endpoint, data in transport.sent[before:]
                if endpoint == "sendMessage" and int(data["chat_id"]) == group]
        assert sent and all(data["message_thread_id"] == 12 for data in sent)


async def test_revoked_anonymous_and_channel_senders_cannot_request(engine, store):
    group = -100123456
    store.set_setting("allowed_group_ids", [group])
    store.execute("UPDATE users SET status='revoked' WHERE id=1")
    async with bot(engine) as (app, ui, transport):
        await send(app, "/movie Example", uid=1, chat_type="supergroup", chat_id=group)
        await send(app, "/movie Example", uid=2, chat_type="supergroup", chat_id=group, anonymous=True)
        await send(app, "/movie Example", uid=2, chat_type="channel", chat_id=group)
        assert not ui.screens and not store.all("SELECT * FROM requests")


async def test_chatid_works_before_group_is_allowed_without_granting_access(engine, store):
    async with bot(engine) as (app, ui, transport):
        await send(app, "/chatid@addarr_test_bot", uid=41, chat_type="supergroup", chat_id=-100123456)
        assert transport.sent[-1][1]["text"] == "-100123456"
        assert store.user(41) is None


async def test_removing_group_discards_its_pending_notifications(engine, store):
    from test_engine import ref
    from addarr.domain import Options

    group = -100123456
    store.set_setting("allowed_group_ids", [group])
    await engine.create(1, ref(), Options(), chat_id=group)
    store.set_setting("allowed_group_ids", [])
    async with bot(engine) as (app, ui, transport):
        before = len(transport.sent)
        await ui.deliver()
        assert not any(int(data.get("chat_id", 0)) == group for _, data in transport.sent[before:])
        assert store.one("SELECT state FROM outbox WHERE chat_id=?", (group,))["state"] == "discarded"


async def test_existing_movie_preview_and_stale_confirmation(engine, store, fake):
    async with bot(engine) as (app, ui, transport):
        await send(app, "/movie Example")
        nonce = ui.screens[(2, 2, None)]["nonce"]
        await send(app, data=f"s:{nonce}:pick:0")
        fake.items["movie"].append({"id": 77, "tmdbId": 123})
        await send(app, data=f"s:{nonce}:confirm")
        assert "Already in your library" in transport.sent[-1][1]["text"]
        assert not store.all("SELECT * FROM requests")
        await send(app, "/movie Example")
        assert "In library" in json.dumps(transport.sent[-1][1]["reply_markup"])
        nonce = ui.screens[(2, 2, None)]["nonce"]
        await send(app, data=f"s:{nonce}:pick:0")
        assert ":confirm" not in json.dumps(transport.sent[-1][1]["reply_markup"])


async def test_deleted_requests_are_hidden_and_not_notified(engine, store):
    from test_engine import ref
    from addarr.domain import Options

    request_id = await engine.create(2, ref().model_copy(update={"title": "Deleted request title"}), Options())
    await engine.manage_request(request_id, "delete", "web-owner")
    async with bot(engine) as (app, ui, transport):
        await send(app, "/requests")
        assert "Deleted request title" not in transport.sent[-1][1]["text"]
        before = len(transport.sent)
        await ui.deliver()
        assert len(transport.sent) == before


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
