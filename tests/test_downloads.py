"""
Filename: test_downloads.py
Author: Christian Blank
Created Date: 2026-09-12
Description: Download identity, status, outage and notification regression tests.
"""

import time

import httpx
import pytest

from addarr.domain import MediaRef, Options
from addarr.downloads import DownloadTracker, download_text, request_downloads, records, from_client
from addarr.engine import Engine


def submitted(engine, kind="movie", *, seasons=None, uid=2):
    """Seed a submitted request with the same remote IDs as the service fixture."""
    ref = MediaRef(service={"movie": "radarr", "series": "sonarr", "album": "lidarr"}[kind],
                   kind=kind, external_id="album-1" if kind == "album" else "123",
                   title="Example", artist_id="artist-1" if kind == "album" else None)
    opts = Options(monitoring="selected" if seasons else "all", seasons=seasons or [])
    rid = engine.store.execute(
        "INSERT INTO requests(user_id,media,options,identity,scope,state,created,updated,remote_id) "
        "VALUES(?,?,?,?,?,'submitted',?,?,1)",
        (uid, ref.model_dump_json(), opts.model_dump_json(), engine.client(ref.service).identity(ref),
         f"scope-{uid}-{kind}-{seasons}", time.time(), time.time()),
    ).lastrowid
    return rid


class Downloads:
    """A queue/history transport that records every request and never permits mutations."""

    def __init__(self, fake):
        self.fake = fake
        self.queue = []
        self.history = []
        self.clients = [{"id": 7, "name": "My SAB", "implementation": "Sabnzbd", "enable": True}]
        self.slots = [{"nzo_id": "SABnzbd_nzo_1", "status": "Downloading", "percentage": "25",
                       "mbleft": "750", "timeleft": "0:01:00"}]
        self.outage = False
        self.calls = []

    def handle(self, request):
        self.calls.append(request)
        assert request.method == "GET"
        path = request.url.path.rsplit("/", 1)[-1]
        if request.url.host == "sab.test":
            if self.outage:
                return httpx.Response(503)
            mode = request.url.params["mode"]
            return httpx.Response(200, json={mode: {"slots": self.slots if mode == "queue" else []}})
        if path == "downloadclient":
            return httpx.Response(200, json=self.clients)
        if path in {"queue", "history"}:
            rows = self.queue if path == "queue" else self.history
            return httpx.Response(200, json={"records": rows, "totalRecords": len(rows)})
        return self.fake.handle(request)


@pytest.fixture
async def tracking(store, fake):
    remote = Downloads(fake)
    store.set_setting("sabnzbd", {"url": "http://sab.test", "api_key": "SAB-SECRET", "enabled": True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(remote.handle)) as http:
        engine = Engine(store, http)
        yield engine, DownloadTracker(engine), remote


async def test_progress_notifications_and_import_are_separate(tracking):
    engine, tracker, remote = tracking
    rid = submitted(engine)
    remote.queue = [{"movieId": 1, "downloadId": "SABnzbd_nzo_1", "downloadClient": "My SAB"}]
    await tracker.tick()
    row = engine.store.one("SELECT * FROM requests WHERE id=?", (rid,))
    assert "25%" in download_text(engine.store, row)
    assert row["state"] == "submitted"
    assert engine.store.one("SELECT COUNT(*) n FROM events WHERE actor='downloads'")["n"] == 1
    remote.slots[0]["percentage"] = "60"
    await tracker.tick()
    assert engine.store.one("SELECT COUNT(*) n FROM events WHERE actor='downloads'")["n"] == 1
    for status, expected in [("Paused", "download_paused"), ("Repairing", "download_checking"),
                             ("Extracting", "download_extracting"), ("Failed", "download_failed"),
                             ("Downloading", "downloading"), ("Completed", "waiting_import")]:
        remote.slots[0]["status"] = status
        await tracker.tick()
        row = engine.store.one("SELECT * FROM requests WHERE id=?", (rid,))
        assert row["download_phase"] == expected
        assert row["state"] == "submitted"
    assert all(r.method == "GET" for r in remote.calls)


async def test_matching_never_uses_titles_or_unmapped_clients(tracking):
    engine, tracker, remote = tracking
    submitted(engine)
    remote.queue = [
        {"movieId": 99, "title": "Example", "downloadId": "wrong-media", "downloadClient": "My SAB"},
        {"movieId": 1, "title": "Example", "downloadId": "wrong-client", "downloadClient": "Other SAB"},
    ]
    await tracker.tick()
    assert not engine.store.all("SELECT * FROM downloads")
    remote.queue = [{"movieId": 1, "downloadId": "SABnzbd_nzo_1", "downloadClient": "My SAB"}]
    remote.clients.append({"id": 8, "name": "Other SAB", "implementation": "Sabnzbd"})
    await tracker.tick()
    assert not engine.store.all("SELECT * FROM downloads")
    config = engine.store.setting("sabnzbd")
    config["mappings"] = {"radarr": 7}
    engine.store.set_setting("sabnzbd", config)
    await tracker.tick()
    assert len(engine.store.all("SELECT * FROM downloads")) == 1


async def test_shared_season_pack_and_album_scope(tracking, fake):
    engine, tracker, remote = tracking
    first = submitted(engine, "series", seasons=[1])
    second = submitted(engine, "series", seasons=[1], uid=1)
    third = submitted(engine, "series", seasons=[2])
    album = submitted(engine, "album")
    fake.albums = [{"id": 10, "foreignAlbumId": "album-1"}, {"id": 20, "foreignAlbumId": "album-2"}]
    remote.queue = [
        {"seriesId": 1, "episodeId": 11, "downloadId": "SABnzbd_nzo_1", "downloadClient": "My SAB"},
        {"seriesId": 1, "episodeId": 11, "downloadId": "SABnzbd_nzo_1", "downloadClient": "My SAB"},
        {"artistId": 1, "albumId": 20, "downloadId": "wrong-album", "downloadClient": "My SAB"},
    ]
    await tracker.tick()
    assert len(engine.store.all("SELECT * FROM downloads")) == 1
    linked = {r["request_id"] for r in engine.store.all("SELECT * FROM request_downloads")}
    assert linked == {first, second}
    assert third not in linked and album not in linked
    assert sum(r.url.path.endswith("/queue") and r.url.host == "sonarr.test" for r in remote.calls) == 1


async def test_history_recovery_and_disappearing_job_become_unknown(tracking):
    engine, tracker, remote = tracking
    rid = submitted(engine)
    remote.history = [{"movieId": 1, "downloadId": "SABnzbd_nzo_1", "data": {
        "downloadClient": "Sabnzbd", "downloadClientName": "My SAB"}}]
    await tracker.tick()
    assert len(engine.store.all("SELECT * FROM downloads")) == 1
    remote.slots = []
    await tracker.tick()
    row = engine.store.one("SELECT * FROM requests WHERE id=?", (rid,))
    assert row["state"] == "submitted" and row["download_phase"] == "download_unknown"
    remote.outage = True
    engine.store.execute("UPDATE downloads SET seen=0,phase='downloading',percent=50")
    await tracker.tick()
    assert request_downloads(engine.store, row)[0]["percent"] is None
    assert "unavailable" in download_text(engine.store, row)


@pytest.mark.parametrize("action", ["cancel", "delete"])
async def test_admin_removal_stops_tracking_without_remote_changes(tracking, action):
    engine, tracker, remote = tracking
    rid = submitted(engine)
    remote.queue = [{"movieId": 1, "downloadId": "SABnzbd_nzo_1", "downloadClient": "My SAB"}]
    await tracker.tick()
    await engine.manage_request(rid, action, "owner")
    remote.calls.clear()
    await tracker.tick()
    assert not remote.calls
    assert not request_downloads(engine.store, engine.store.one("SELECT * FROM requests WHERE id=?", (rid,)))


async def test_changed_service_instance_and_revocation_stop_association(tracking):
    engine, tracker, remote = tracking
    rid = submitted(engine)
    remote.queue = [{"movieId": 1, "downloadId": "SABnzbd_nzo_1", "downloadClient": "My SAB"}]
    engine.store.execute("UPDATE requests SET identity='different-instance' WHERE id=?", (rid,))
    await tracker.tick()
    assert not engine.store.all("SELECT * FROM downloads")
    engine.store.execute("UPDATE users SET status='revoked' WHERE id=2")
    remote.calls.clear()
    await tracker.tick()
    assert not remote.calls


async def test_history_pagination(engine, monkeypatch):
    pages = []

    async def call(method, path, *, params):
        pages.append(params["page"])
        return {"records": [{"id": params["page"]}], "totalRecords": 201}

    client = engine.client("radarr")
    monkeypatch.setattr(client, "call", call)
    assert len(await records(client, "history")) == 3
    assert pages == [1, 2, 3]


def test_history_implementation_is_not_a_client_name():
    assert not from_client({"data": {"downloadClient": "Sabnzbd"}}, 7, "Sabnzbd")
    assert from_client({"data": {"DownloadClientName": "My SAB"}}, 7, "My SAB")
