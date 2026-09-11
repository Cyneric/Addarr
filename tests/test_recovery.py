"""
Filename: test_recovery.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Persistence and process lock checks for restart and crash recovery.
"""

import asyncio

import pytest

from addarr.domain import Options
from addarr.locking import ProcessLock
from addarr.store import Store
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
