"""
Filename: test_engine.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Request workflow checks for permissions, approval, retries and availability.
"""

import asyncio

import httpx
import pytest

from addarr.domain import MediaRef, Options, ServiceError
from addarr.engine import Engine


def ref(kind="movie", external="123"):
    return MediaRef.model_validate(
        dict(
            service={"movie": "radarr", "series": "sonarr", "artist": "lidarr", "album": "lidarr"}[kind],
            external_id=external,
            title="Example",
            kind=kind,
            artist_id="artist-1" if kind == "album" else None,
        )
    )


async def test_approval_to_availability(engine, store, fake):
    request_id = await engine.create(1, ref(), Options())
    assert store.one("SELECT state FROM requests WHERE id=?", (request_id,))["state"] == "pending"
    await engine.tick()
    assert not fake.items["movie"]
    with pytest.raises(PermissionError):
        engine.action(request_id, "approve", "1", user_id=1)
    engine.action(request_id, "approve", "2", user_id=2)
    await engine.tick()
    assert len(fake.items["movie"]) == 1
    assert store.one("SELECT state FROM requests WHERE id=?", (request_id,))["state"] == "submitted"
    fake.items["movie"][0]["hasFile"] = True
    store.execute("UPDATE requests SET next_attempt=0")
    await engine.tick()
    assert store.one("SELECT state FROM requests WHERE id=?", (request_id,))["state"] == "available"
    states = [r["action"] for r in store.all("SELECT action FROM events")]
    assert states == ["pending", "queued", "submitted", "available"]
    assert len(store.all("SELECT * FROM outbox")) == 8


@pytest.mark.parametrize("kind", ["movie", "series", "artist", "album"])
async def test_global_auto_approval_for_all_media(engine, store, kind):
    store.set_setting("auto_approve_all", True)
    request_id = await engine.create(1, ref(kind), Options())
    assert store.one("SELECT state FROM requests WHERE id=?", (request_id,))["state"] == "queued"
    assert store.user(1)["auto_approve"] == 0


async def test_global_auto_approval_toggle_preserves_existing_requests_and_user_policy(engine, store):
    old_id = await engine.create(1, ref(external="old"), Options())
    store.set_setting("auto_approve_all", True)
    new_id = await engine.create(1, ref(external="new"), Options())
    assert store.one("SELECT state FROM requests WHERE id=?", (old_id,))["state"] == "pending"
    assert store.one("SELECT state FROM requests WHERE id=?", (new_id,))["state"] == "queued"
    store.set_setting("auto_approve_all", False)
    manual_id = await engine.create(1, ref(external="manual"), Options())
    assert store.one("SELECT state FROM requests WHERE id=?", (manual_id,))["state"] == "pending"
    store.execute("UPDATE users SET auto_approve=1 WHERE id=1")
    personal_id = await engine.create(1, ref(external="personal"), Options())
    assert store.one("SELECT state FROM requests WHERE id=?", (personal_id,))["state"] == "queued"


@pytest.mark.parametrize("status", ["pending", "revoked"])
async def test_global_auto_approval_does_not_grant_user_access(engine, store, status):
    store.set_setting("auto_approve_all", True)
    store.execute("UPDATE users SET status=? WHERE id=1", (status,))
    with pytest.raises(PermissionError):
        await engine.create(1, ref(), Options())
    assert not store.all("SELECT * FROM requests")


async def test_concurrent_duplicate_clicks(engine, store, fake):
    ids = await asyncio.gather(*(engine.create(2, ref(), Options()) for _ in range(10)))
    assert len(set(ids)) == 1
    await engine.tick()
    assert len(fake.items["movie"]) == len(fake.commands) == 1


@pytest.mark.parametrize("failure", ["timeout_add", "timeout_command"])
async def test_ambiguous_acceptance_and_restart(engine, store, fake, failure):
    setattr(fake, failure, True)
    request_id = await engine.create(2, ref(), Options())
    await engine.tick()
    assert store.one("SELECT state FROM requests WHERE id=?", (request_id,))["state"] == "queued"
    store.execute("UPDATE requests SET next_attempt=0")
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)) as http:
        replacement = Engine(store, http)
        await replacement.tick()
    assert len(fake.items["movie"]) == 1
    assert len(fake.commands) == 1
    assert store.one("SELECT state FROM requests WHERE id=?", (request_id,))["state"] == "submitted"


async def test_uncertain_search_is_not_blindly_replayed(engine, store, fake):
    request_id = await engine.create(2, ref(), Options())
    store.execute(
        "INSERT INTO operations VALUES(?,'uncertain',NULL)",
        (f"{engine.client('radarr').instance}:{request_id}:search",),
    )
    await engine.tick()
    row = store.one("SELECT * FROM requests WHERE id=?", (request_id,))
    assert row["state"] == "failed"
    assert "review" in row["error"]
    assert not fake.commands


async def test_overlapping_seasons_preserve_settings(engine, store, fake):
    first = await engine.create(2, ref("series"), Options(monitoring="selected", seasons=[1]))
    await engine.tick()
    fake.items["series"][0]["qualityProfileId"] = 2
    second = await engine.create(2, ref("series"), Options(monitoring="selected", seasons=[2]))
    await engine.tick()
    item = fake.items["series"][0]
    assert first != second
    assert len(fake.items["series"]) == 1
    assert all(s["monitored"] for s in item["seasons"])
    assert item["qualityProfileId"] == 2
    assert [c["body"]["seasonNumber"] for c in fake.commands] == [1, 2]


async def test_album_does_not_monitor_catalog(engine, store, fake):
    await engine.create(2, ref("album", "album-1"), Options())
    await engine.tick()
    assert fake.albums[0]["monitored"]
    assert not fake.albums[1]["monitored"]
    assert fake.items["artist"][0]["monitorNewItems"] == "none"
    assert fake.commands[0]["body"]["albumIds"] == [10]


async def test_artist_monitors_catalog(engine, store, fake):
    await engine.create(2, ref("artist", "artist-1"), Options())
    await engine.tick()
    assert all(a["monitored"] for a in fake.albums)
    assert fake.items["artist"][0]["monitorNewItems"] == "all"


async def test_future_episodes_include_known_future_releases(engine, fake):
    await engine.create(2, ref("series"), Options(monitoring="future"))
    await engine.tick()
    assert fake.episodes[0]["monitored"]
    assert not fake.episodes[1].get("monitored")
    assert not fake.commands


async def test_cancel_and_revoke_prevent_submission(engine, store, fake):
    request_id = await engine.create(2, ref(), Options())
    engine.action(request_id, "cancel", "2", user_id=2)
    await engine.tick()
    assert not fake.items["movie"]
    request_id = await engine.create(2, ref(), Options())
    store.execute("UPDATE users SET status='revoked' WHERE id=2")
    await engine.tick()
    assert not fake.items["movie"]
    assert store.one("SELECT state FROM requests WHERE id=?", (request_id,))["state"] == "failed"


async def test_service_outage_does_not_submit(engine, store, fake):
    request_id = await engine.create(2, ref(), Options())
    fake.fail_status = 503
    await engine.tick()
    row = store.one("SELECT * FROM requests WHERE id=?", (request_id,))
    assert row["state"] == "queued" and row["attempts"] == 1
    assert not fake.items["movie"]
    fake.fail_status = 0
    store.execute("UPDATE requests SET next_attempt=0")
    await engine.tick()
    assert len(fake.items["movie"]) == 1


@pytest.mark.parametrize(
    "status,category",
    [
        (401, "credentials"),
        (403, "credentials"),
        (429, "unavailable"),
        (500, "unavailable"),
        (400, "validation"),
    ],
)
async def test_error_categories(engine, fake, status, category):
    fake.fail_status = status
    with pytest.raises(ServiceError) as exc:
        await engine.search(1, "radarr", "Test")
    assert exc.value.category == category
    assert "SECRET" not in str(exc.value)


async def test_option_policy_and_exact_identity(engine, store):
    config = store.setting("service:radarr")
    config["allowed_profiles"] = [1]
    store.set_setting("service:radarr", config)
    with pytest.raises(ServiceError):
        await engine.create(2, ref(), Options(quality_profile=2))
    with pytest.raises(ServiceError):
        await engine.client("radarr").lookup("movie", "wrong", "tmdbId")
    with pytest.raises(ServiceError):
        await engine.create(2, ref(), Options(root_folder="/missing"))


async def test_state_changes_are_checked_at_action_time(engine):
    request_id = await engine.create(1, ref(), Options())
    engine.action(request_id, "reject", "2", user_id=2)
    with pytest.raises(ValueError):
        engine.action(request_id, "approve", "2", user_id=2)


async def test_search_query_is_encoded(engine, fake):
    results = await engine.search(1, "radarr", "A & B / 漢字")
    assert results[0].ref.external_id == "123"


async def test_none_preserves_existing_monitoring(engine, fake):
    await engine.create(2, ref("series"), Options(monitoring="selected", seasons=[1]))
    await engine.tick()
    await engine.create(2, ref("series"), Options(monitoring="none"))
    await engine.tick()
    assert fake.items["series"][0]["seasons"][0]["monitored"]
    assert len(fake.commands) == 1


async def test_two_requesters_share_submission_and_title_changes_deduplicate(engine, store, fake):
    first = await engine.create(2, ref(), Options())
    renamed = ref().model_copy(update={"title": "Translated title"})
    assert await engine.create(2, renamed, Options()) == first
    second = await engine.create(1, ref(), Options())
    engine.action(second, "approve", "2", user_id=2)
    await engine.tick()
    await engine.tick()
    assert len(fake.items["movie"]) == len(fake.commands) == 1
    assert len(store.all("SELECT * FROM requests WHERE state='submitted'")) == 2


async def test_overlapping_season_commands_are_not_duplicated(engine, fake):
    await engine.create(2, ref("series"), Options(monitoring="selected", seasons=[1]))
    await engine.tick()
    await engine.create(2, ref("series"), Options(monitoring="selected", seasons=[1, 2]))
    await engine.tick()
    assert [c["body"]["seasonNumber"] for c in fake.commands] == [1, 2]


async def test_notification_policy_does_not_remove_audit_trail(engine, store):
    store.set_setting("notify_requests", False)
    await engine.create(1, ref(), Options())
    assert not store.all("SELECT * FROM outbox")
    assert store.all("SELECT * FROM events")


async def test_changed_service_address_does_not_reuse_old_remote_ids(engine, store, fake):
    request_id = await engine.create(2, ref(), Options())
    config = store.setting("service:radarr")
    config["url"] = "http://replacement.test/"
    store.set_setting("service:radarr", config)
    await engine.tick()
    assert not fake.items["movie"]
    assert store.one("SELECT state FROM requests WHERE id=?", (request_id,))["state"] == "failed"
    assert await engine.create(2, ref(), Options()) != request_id
