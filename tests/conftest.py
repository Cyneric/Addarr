"""
Filename: conftest.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Shared database fixtures and an in-memory Arr API for request tests.
"""

import copy
import json

import httpx
import pytest

from addarr.domain import ServiceConfig
from addarr.engine import Engine
from addarr.store import Store


class FakeArr:
    """Stateful remote fixture: writes survive a local engine restart."""

    def __init__(self):
        self.items = {"movie": [], "series": [], "artist": []}
        self.albums = []
        self.commands = []
        self.calls = []
        self.fail_status = 0
        self.timeout_command = False
        self.timeout_add = False
        self.episodes = [
            {"id": 11, "seasonNumber": 1, "hasFile": False, "airDateUtc": "2099-01-01T00:00:00Z"},
            {"id": 22, "seasonNumber": 2, "hasFile": False, "airDateUtc": "2020-01-01T00:00:00Z"},
        ]

    def handle(self, request):
        """Emulate Arr responses, including accepted writes whose responses time out."""
        path = request.url.path.split("/api/")[-1].split("/", 1)[-1]
        data = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, data))
        if self.fail_status:
            return httpx.Response(self.fail_status)
        if path == "system/status":
            return httpx.Response(200, json={"version": "fixture-1"})
        if path in ("qualityprofile", "metadataprofile"):
            return httpx.Response(200, json=[{"id": 1, "name": "Standard"}, {"id": 2, "name": "High"}])
        if path == "rootfolder":
            return httpx.Response(200, json=[{"id": 1, "path": "/media"}, {"id": 2, "path": "/archive"}])
        if path.endswith("/lookup"):
            endpoint = path.split("/")[0]
            row = {"title": "Example", "overview": "A test title", "images": []}
            if endpoint == "movie":
                row.update(tmdbId=123)
            elif endpoint == "series":
                row.update(
                    tvdbId=123,
                    seasons=[
                        {"seasonNumber": 1, "monitored": False},
                        {"seasonNumber": 2, "monitored": False},
                    ],
                )
            elif endpoint == "artist":
                row.update(foreignArtistId="artist-1", artistName="Artist")
            else:
                row.update(
                    foreignAlbumId="album-1", artist={"foreignArtistId": "artist-1", "artistName": "Artist"}
                )
            return httpx.Response(200, json=[row])
        if path == "tag":
            return httpx.Response(200, json=[] if request.method == "GET" else {"id": 1, **data})
        if path == "command":
            if request.method == "GET":
                return httpx.Response(200, json=self.commands)
            result = {"id": len(self.commands) + 1, "name": data["name"], "body": data}
            self.commands.append(result)
            if self.timeout_command:
                self.timeout_command = False
                raise httpx.ReadTimeout("After acceptance", request=request)
            return httpx.Response(201, json=result)
        if path == "episode":
            return httpx.Response(200, json=self.episodes)
        if path == "episode/monitor":
            for row in self.episodes:
                if row["id"] in data["episodeIds"]:
                    row["monitored"] = data["monitored"]
            return httpx.Response(202)
        if path == "album":
            return httpx.Response(200, json=self.albums)
        if path == "album/monitor":
            for row in self.albums:
                if row["id"] in data["albumIds"]:
                    row["monitored"] = data["monitored"]
            return httpx.Response(202)
        endpoint = path.split("/")[0]
        if endpoint in self.items:
            if request.method == "POST":
                result = {**data, "id": len(self.items[endpoint]) + 1}
                self.items[endpoint].append(copy.deepcopy(result))
                if endpoint == "artist":
                    self.albums = [
                        {
                            "id": 10,
                            "foreignAlbumId": "album-1",
                            "title": "First",
                            "monitored": False,
                            "statistics": {"trackFileCount": 0, "totalTrackCount": 10},
                        },
                        {"id": 20, "foreignAlbumId": "album-2", "title": "Second", "monitored": False},
                    ]
                if self.timeout_add:
                    self.timeout_add = False
                    raise httpx.ReadTimeout("After acceptance", request=request)
                return httpx.Response(201, json=result)
            if "/" in path:
                item_id = int(path.split("/")[1])
                item = next(r for r in self.items[endpoint] if r["id"] == item_id)
                if request.method == "PUT":
                    item.update(copy.deepcopy(data))
                return httpx.Response(200, json=item)
            return httpx.Response(200, json=self.items[endpoint])
        raise AssertionError(f"Unexpected request: {request.method} {path}")


@pytest.fixture
def fake():
    """Provide fresh remote state independent of any local engine instance."""
    return FakeArr()


@pytest.fixture
def store(tmp_path):
    """Provide a temporary database with three services and active member/admin accounts."""
    st = Store(tmp_path / "config")
    for kind in ("radarr", "sonarr", "lidarr"):
        config = ServiceConfig.model_validate(
            dict(
                kind=kind,
                url=f"http://{kind}.test",
                api_key="SECRET",
                quality_profile=1,
                root_folder="/media",
                metadata_profile=1,
            )
        )
        st.set_setting(f"service:{kind}", config.model_dump(mode="json"))
    st.execute("INSERT INTO users(id,name,status,chat_id) VALUES(1,'Member','active',1)")
    st.execute("INSERT INTO users(id,name,status,role,chat_id) VALUES(2,'Admin','active','admin',2)")
    yield st
    st.close()


@pytest.fixture
async def engine(store, fake):
    """Connect the request engine to the in-memory Arr transport for one test."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)) as client:
        yield Engine(store, client)
