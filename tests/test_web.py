"""
Filename: test_web.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Web checks for authentication, service settings, request policies and administration.
"""

import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from addarr.adapters import ArrClient
from addarr.domain import ServiceError
from addarr.web import create_app


@pytest.fixture
def web(tmp_path, fake):
    app = create_app(tmp_path / "web", background=False, transport=httpx.MockTransport(fake.handle))
    with TestClient(app) as client:
        yield client, app


def post(client, path, **data):
    return client.post(path, data={"csrf": client.cookies.get("csrf"), **data})


def setup(client, app):
    assert client.get("/").url.path == "/setup"
    response = post(
        client,
        "/setup",
        username="owner",
        password="correct horse battery",
        bootstrap=app.state.store.bootstrap_token(),
    )
    assert response.status_code == 200
    assert response.url.path == "/"


def test_bootstrap_login_logout_and_csrf(web):
    client, app = web
    setup(client, app)
    assert not (app.state.store.directory / "bootstrap-token").exists()
    assert client.post("/settings", data={"polling": "on"}).status_code == 403
    post(client, "/logout")
    assert client.get("/users").url.path == "/login"
    assert post(client, "/login", username="owner", password="wrong").status_code == 403
    assert post(client, "/login", username="missing", password="wrong").status_code == 403
    assert post(client, "/login", username="owner", password="correct horse battery").url.path == "/"
    assert post(client, "/setup", username="x", password="a long password", bootstrap="x").status_code == 409


def test_global_approval_setting_is_persistent_and_independent_of_bot_settings(web):
    client, app = web
    setup(client, app)
    assert app.state.store.setting("auto_approve_all", False) is False
    assert client.post("/settings/requests", data={"auto_approve_all": "on"}).status_code == 403
    app.state.store.set_setting("polling_enabled", True)
    app.state.store.set_setting("telegram_token", "KEEP-TOKEN")
    response = post(client, "/settings/requests", auto_approve_all="on")
    assert response.status_code == 200
    assert 'name="auto_approve_all" type="checkbox" checked' in client.get("/settings").text
    assert app.state.store.setting("auto_approve_all") is True
    assert app.state.store.setting("polling_enabled") is True
    assert app.state.store.setting("telegram_token") == "KEEP-TOKEN"
    response = post(client, "/settings/requests")
    assert response.status_code == 200
    assert app.state.store.setting("auto_approve_all") is False
    assert len(app.state.store.all("SELECT * FROM events WHERE action='request_policy_updated'")) == 2


def test_all_admin_pages_and_locales(web):
    client, app = web
    setup(client, app)
    for path in ("/", "/users", "/services", "/settings", "/requests", "/migration", "/diagnostics"):
        for language in ("en-us", "de-de", "es-es", "fr-fr", "it-it", "nl-be", "pl-pl", "pt-pt", "ru-ru"):
            response = client.get(path + "?lang=" + language)
            assert response.status_code == 200
            assert f'lang="{language[:2]}"' in response.text
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_overview_shows_latest_five_requests_and_escapes_titles(web):
    client, app = web
    setup(client, app)
    st = app.state.store
    st.execute("INSERT INTO users(id,name) VALUES(1,'Viewer')")
    for number in range(6):
        st.execute(
            "INSERT INTO requests(user_id,media,options,identity,scope,state,created,updated) "
            "VALUES(1,?,'{}',?,?,'pending',0,0)",
            (
                json.dumps({"service": "radarr", "title": f"<film-{number}>"}),
                str(number),
                str(number),
            ),
        )
    response = client.get("/")
    assert response.status_code == 200
    assert "film-0" not in response.text
    assert "<film-5>" not in response.text
    assert response.text.index("&lt;film-5&gt;") < response.text.index("&lt;film-1&gt;")
    assert response.text.count('class="recent-row"') == 5


def test_connection_test_save_and_no_secret_reflection(web):
    client, app = web
    setup(client, app)
    response = post(
        client,
        "/services/radarr",
        url="http://radarr.test",
        api_key="SECRET",
        action="test",
        enabled="on",
        search="on",
    )
    assert response.status_code == 200 and "Standard" in response.text
    assert "SECRET" not in response.text
    response = post(
        client,
        "/services/radarr",
        url="http://radarr.test",
        action="save",
        enabled="on",
        quality_profile="1",
        root_folder="/media",
        search="on",
    )
    assert response.status_code == 200
    assert app.state.store.setting("service:radarr")["api_key"] == "SECRET"
    assert '<select name="quality_profile">' in client.get("/services").text
    response = post(client, "/services/radarr", url="invalid", api_key="DO-NOT-LEAK", action="save")
    assert response.status_code == 400 and "DO-NOT-LEAK" not in response.text


@pytest.mark.parametrize("kind", ["radarr", "sonarr", "lidarr"])
def test_saved_service_loads_choices_on_each_visit(web, kind):
    client, app = web
    setup(client, app)
    config = dict(
        kind=kind,
        url=f"http://{kind}.test",
        api_key="PRIVATE-KEY",
        quality_profile=2,
        root_folder="/archive",
        metadata_profile=2,
        allowed_profiles=[2],
        allowed_folders=["/archive"],
    )
    app.state.store.set_setting(f"service:{kind}", config)
    for _ in range(2):
        response = client.get("/services")
        assert response.status_code == 200
        assert '<select name="quality_profile">' in response.text
        assert '<option value="2" selected>High</option>' in response.text
        assert '<option value="/archive" selected>/archive</option>' in response.text
        if kind == "lidarr":
            assert '<select name="metadata_profile">' in response.text
        assert "PRIVATE-KEY" not in response.text
    assert app.state.store.setting(f"service:{kind}") == config


def test_offline_service_keeps_saved_selections_and_page_available(web, fake):
    client, app = web
    setup(client, app)
    config = dict(
        kind="radarr",
        url="http://radarr.test",
        api_key="PRIVATE-KEY",
        quality_profile=2,
        root_folder="/archive",
        allowed_profiles=[2],
        allowed_folders=["/archive"],
    )
    app.state.store.set_setting("service:radarr", config)
    fake.fail_status = 503
    response = client.get("/services")
    assert response.status_code == 200
    assert "Could not load profiles and folders" in response.text
    assert 'type="hidden" name="quality_profile" value="2"' in response.text
    assert 'type="hidden" name="root_folder" value="/archive"' in response.text
    assert 'type="hidden" name="allowed_profiles" value="2"' in response.text
    assert "PRIVATE-KEY" not in response.text
    assert app.state.store.setting("service:radarr") == config


def test_removed_service_choice_does_not_silently_select_a_replacement(web):
    client, app = web
    setup(client, app)
    app.state.store.set_setting(
        "service:radarr",
        dict(
            kind="radarr",
            url="http://radarr.test",
            api_key="SECRET",
            quality_profile=99,
            root_folder="/removed",
        ),
    )
    response = client.get("/services")
    assert '<option value="99" selected>99 · No longer available</option>' in response.text
    assert '<option value="/removed" selected>/removed · No longer available</option>' in response.text


def test_one_offline_service_does_not_hide_other_service_choices(web, monkeypatch):
    client, app = web
    setup(client, app)
    for kind in ("radarr", "sonarr"):
        app.state.store.set_setting(
            f"service:{kind}",
            dict(
                kind=kind,
                url=f"http://{kind}.test",
                api_key="SECRET",
                quality_profile=2,
                root_folder="/archive",
            ),
        )
    original = ArrClient.capabilities

    async def capabilities(arr):
        if arr.config.kind == "radarr":
            raise ServiceError("unavailable", "Cannot connect")
        return await original(arr)

    monkeypatch.setattr(ArrClient, "capabilities", capabilities)
    response = client.get("/services")
    assert response.status_code == 200
    assert "Could not load profiles and folders" in response.text
    assert '<option value="2" selected>High</option>' in response.text


def test_migration_preview_is_readonly_and_access_pending(web):
    client, app = web
    setup(client, app)
    yaml = "telegram:\n  token: secret-token\nadmins: [123]\nauthenticated_users: [456]\nlanguage: de-de\n"
    response = client.post(
        "/migration/preview",
        data={"csrf": client.cookies.get("csrf")},
        files={"config": ("config.yaml", yaml, "application/yaml")},
    )
    assert response.status_code == 200 and "secret-token" not in response.text
    assert not app.state.store.user(123)
    report = app.state.store.setting("import:1")
    response = post(client, "/migration/apply", digest=report["digest"])
    assert response.status_code == 200
    assert app.state.store.user(123)["status"] == "pending"
    assert not app.state.store.setting("polling_enabled")
    response = post(client, "/users/123", status="active", role="admin", locale="de-de")
    assert response.status_code == 200
    assert app.state.store.user(123)["status"] == "active"


def test_backup_restores_database(web, tmp_path):
    client, app = web
    setup(client, app)
    response = post(client, "/backup")
    assert response.status_code == 200
    path = tmp_path / "restore.db"
    path.write_bytes(response.content)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT username FROM admins").fetchone()[0] == "owner"


def test_login_throttling_and_origin(web):
    client, app = web
    setup(client, app)
    response = client.post(
        "/settings", data={"csrf": client.cookies.get("csrf")}, headers={"Origin": "http://evil.test"}
    )
    assert response.status_code == 403
    post(client, "/logout")
    for _ in range(10):
        response = post(client, "/login", username="owner", password="wrong")
    assert response.status_code == 429


def test_health_and_missing_configuration(web):
    client, app = web
    assert client.get("/health/live").json() == {"ok": True}
    assert client.get("/health/ready").status_code == 200
    setup(client, app)
    assert post(client, "/settings", token="123:abc", language="en-us", polling="on").status_code == 400
