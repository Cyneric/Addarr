"""
Filename: test_recovery.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Persistence and process lock checks for restart and crash recovery.
"""

import asyncio
import sqlite3

import pytest

from addarr.domain import Options
from addarr.locking import ProcessLock
from addarr.store import SCHEMA, Store
from test_engine import ref


def test_one_process_per_data_directory(tmp_path):
    first = ProcessLock(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="Another Addarr"):
            ProcessLock(tmp_path)
    finally:
        first.close()
    second = ProcessLock(tmp_path)
    second.close()


async def test_recover_submitting_checkpoint(engine, store, fake):
    request_id = await engine.create(2, ref(), Options())
    store.execute("UPDATE requests SET state='submitting' WHERE id=?", (request_id,))
    task = asyncio.create_task(engine.run())
    try:
        for _ in range(100):
            await asyncio.sleep(0.01)
            if store.one("SELECT state FROM requests WHERE id=?", (request_id,))["state"] == "submitted":
                break
        assert store.one("SELECT state FROM requests WHERE id=?", (request_id,))["state"] == "submitted"
        assert len(fake.items["movie"]) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_transaction_rollback_and_reopen(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.set_setting("unfinished", True)
            raise RuntimeError("Interrupted operation")
    store.set_setting("committed", True)
    store.close()
    reopened = Store(tmp_path)
    try:
        assert reopened.setting("unfinished") is None
        assert reopened.setting("committed") is True
        assert reopened.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_v1_database_upgrade_preserves_requests_and_takes_backup(tmp_path):
    """Upgrade an existing installation rather than only testing a fresh schema."""
    connection = sqlite3.connect(tmp_path / "addarr.db")
    connection.executescript(SCHEMA + "PRAGMA user_version=1;")
    connection.execute("INSERT INTO settings VALUES('language', '\"de-de\"')")
    connection.execute("INSERT INTO users(id,name,status) VALUES(1,'Member','active')")
    connection.execute(
        "INSERT INTO requests(user_id,media,options,identity,scope,state,created,updated) "
        "VALUES(1,'{}','{}','movie:1','scope','pending',1,1)"
    )
    connection.commit()
    connection.close()
    store = Store(tmp_path)
    try:
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == 4
        assert store.setting("language") == "de-de"
        row = store.one("SELECT * FROM requests")
        assert row["state"] == "pending" and row["chat_id"] is None and row["thread_id"] is None
        assert row["deleted"] == 0
        assert len(list((tmp_path / "backups").glob("before-schema-v2-*.db"))) == 1
    finally:
        store.close()
    reopened = Store(tmp_path)
    reopened.close()
    assert len(list((tmp_path / "backups").glob("before-schema-v2-*.db"))) == 1


def test_v2_upgrade_preserves_group_origin_and_backs_up(tmp_path):
    connection = sqlite3.connect(tmp_path / "addarr.db")
    connection.executescript(
        SCHEMA + "ALTER TABLE requests ADD COLUMN chat_id INTEGER;"
        "ALTER TABLE requests ADD COLUMN thread_id INTEGER;"
        "ALTER TABLE outbox ADD COLUMN thread_id INTEGER; PRAGMA user_version=2;"
    )
    connection.execute(
        "INSERT INTO requests(user_id,media,options,identity,scope,state,created,updated,chat_id,thread_id) "
        "VALUES(1,'{}','{}','movie:1','scope','submitted',1,1,-100123,12)"
    )
    connection.commit()
    connection.close()
    store = Store(tmp_path)
    try:
        row = store.one("SELECT * FROM requests")
        assert row["deleted"] == 0 and row["chat_id"] == -100123 and row["thread_id"] == 12
        assert list((tmp_path / "backups").glob("before-schema-v3-*.db"))
    finally:
        store.close()
