"""
Filename: browser_smoke.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Browser checks against a temporary Addarr server with no external services.
"""

import socket
import json
import sqlite3
import os
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect


def update_flow(page, base, artifacts, errors):
    """Exercise the real controls with simulated status, never invoking a container update."""
    state = {"offline": False, "posts": 0, "phase": "idle", "view": {
        "state": "available", "message": "Update available", "can_install": True,
        "revision": "2" * 40, "details": False, "visible": True,
    }}
    dialogs = []

    def unexpected_dialog(dialog):
        dialogs.append(dialog.message)
        dialog.dismiss()

    def status(route):
        if state["offline"]:
            route.abort("connectionclosed")
        else:
            route.fulfill(json={"job": {"enabled": True, "phase": state["phase"]}, "view": state["view"], "maintenance": False})

    def install(route):
        state["posts"] += 1
        assert "csrf" in route.request.post_data and "2" * 40 in route.request.post_data
        state["phase"] = "checking"
        state["view"] = {"state": "updating", "message": "Updating…", "can_install": False,
                         "revision": "", "details": False, "visible": True}
        route.fulfill(status=202, json={"accepted": True})

    page.on("dialog", unexpected_dialog)
    page.route("**/updates/status", status)
    page.route("**/updates/install", install)
    try:
        page.goto(base + "/")
        button = page.get_by_role("button", name="Update now", exact=True)
        expect(button).to_be_visible()
        assert page.locator('nav a[href="/updates"]').count() == 0
        page.screenshot(path=artifacts / "update-available-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=artifacts / "update-available-mobile.png", full_page=True)
        button.click()
        expect(page.locator(".update-message")).to_have_text("Updating…")
        page.locator('[data-update-install]').evaluate("form => form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}))")
        assert state["posts"] == 1 and not dialogs
        state["offline"] = True
        page.wait_for_timeout(3500)
        expect(page.locator(".update-message")).to_have_text("Updating…")
        state["offline"] = False
        state["phase"] = "succeeded"
        state["view"] = {"state": "updated", "message": "Updated", "can_install": False,
                         "revision": "", "details": False, "visible": True}
        expect(page.locator(".update-message")).to_have_text("Updated", timeout=12000)
        assert page.url == base + "/"
        for phase, message in (("rolled_back", "Update failed. The previous version is running again."),
                               ("recovery_failed", "Update failed. Recovery needs your attention. See diagnostics.")):
            state["phase"] = phase
            state["view"].update(state="error", message=message, details=True)
            page.goto(base + "/updates")
            expect(page.locator(".update-message")).to_have_text(message)
            expect(page.locator("[data-update-details]")).to_be_visible()
            expect(page.get_by_role("button", name="Update now", exact=True)).to_be_hidden()
        assert not dialogs
    finally:
        page.remove_listener("dialog", unexpected_dialog)
        page.unroute("**/updates/status", status)
        page.unroute("**/updates/install", install)
        errors[:] = [error for error in errors if "net::ERR_CONNECTION_CLOSED" not in error]
        page.set_viewport_size({"width": 1440, "height": 1000})


def main():
    """Start an isolated server, check desktop/mobile browser flows and clean up its process and data."""
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="addarr-browser-") as directory:
        log = (artifacts / "browser-server.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "addarr.cli",
                "--data-dir",
                directory,
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=root,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                try:
                    with urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=1):
                        break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError("Server failed; see artifacts/browser-server.log") from None
                    time.sleep(0.1)
            else:
                raise RuntimeError("Server startup timeout")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.goto(f"http://127.0.0.1:{port}")
                page.screenshot(path=artifacts / "setup-desktop.png", full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.screenshot(path=artifacts / "setup-mobile.png", full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.locator('[name="bootstrap"]').fill((Path(directory) / "bootstrap-token").read_text())
                page.locator('[name="username"]').fill("browser-owner")
                page.locator('[name="password"]').fill("browser-test-password")
                page.get_by_role("button", name="Show password", exact=True).click()
                assert page.locator('[name="password"]').get_attribute("type") == "text"
                page.get_by_role("button", name="Show password", exact=True).click()
                assert page.locator('[name="password"]').get_attribute("type") == "password"
                with page.expect_response(lambda response: response.request.method == "POST") as submission:
                    page.get_by_role("button", name="Create admin account", exact=True).click()
                if submission.value.status != 303:
                    page.screenshot(path=artifacts / "setup-failure.png", full_page=True)
                    raise AssertionError(
                        f"Setup HTTP {submission.value.status}: {page.locator('body').inner_text()}"
                    )
                page.wait_for_url(f"http://127.0.0.1:{port}/")
                page.screenshot(path=artifacts / "dashboard-desktop.png", full_page=True)
                for path in ("services", "downloads", "updates", "users", "requests", "settings", "migration", "diagnostics"):
                    response = page.goto(f"http://127.0.0.1:{port}/{path}")
                    assert response.status == 200, path
                    assert page.locator("h1").is_visible()
                    page.screenshot(path=artifacts / f"{path}-desktop.png", full_page=True)
                    if path == "requests":
                        # Seed only this temporary server's database to exercise real admin controls.
                        with closing(sqlite3.connect(Path(directory) / "addarr.db")) as database, database:
                            database.execute("INSERT INTO users(id,name,status) VALUES(1,'Test member','active')")
                            cursor = database.execute(
                                "INSERT INTO requests(user_id,media,options,identity,scope,state,created,updated,next_attempt) "
                                "VALUES(1,?,'{}','test','test','submitted',1,1,9999999999)",
                                (json.dumps({"service": "radarr", "kind": "movie", "external_id": "123",
                                             "title": "Request removal test"}),),
                            )
                            request_id = cursor.lastrowid
                        page.reload()
                        remove = page.locator(f'form[action="/requests/{request_id}/delete"] button')
                        cancel = page.locator(f'form[action="/requests/{request_id}/cancel"] button')
                        assert remove.is_visible() and cancel.is_visible()
                        page.screenshot(path=artifacts / "request-actions-desktop.png", full_page=True)
                        page.set_viewport_size({"width": 390, "height": 844})
                        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                        page.screenshot(path=artifacts / "request-actions-mobile.png", full_page=True)
                        page.set_viewport_size({"width": 1440, "height": 1000})
                        page.once("dialog", lambda dialog: dialog.dismiss())
                        remove.click()
                        assert page.get_by_role("heading", name="Request removal test").is_visible()
                        page.once("dialog", lambda dialog: dialog.accept())
                        cancel.click()
                        page.wait_for_load_state("load")
                        assert page.locator("article.request .pill").inner_text() == "Cancelled"
                        page.once("dialog", lambda dialog: dialog.accept())
                        remove.click()
                        page.wait_for_load_state("load")
                        assert page.get_by_role("heading", name="Request removal test").count() == 0
                    if path == "settings":
                        groups = page.locator('form[action="/settings/groups"]')
                        groups.locator('[name="allowed_group_ids"]').fill("-1001234567890\n-1009876543210")
                        groups.get_by_role("button", name="Save", exact=True).click()
                        page.wait_for_load_state("load")
                        page.reload()
                        assert groups.locator('[name="allowed_group_ids"]').input_value() == "-1001234567890\n-1009876543210"
                        groups.locator('[name="allowed_group_ids"]').fill("")
                        groups.get_by_role("button", name="Save", exact=True).click()
                        page.wait_for_load_state("load")
                        policy = page.locator('form[action="/settings/requests"]')
                        policy.locator('[name="auto_approve_all"]').check()
                        policy.get_by_role("button", name="Save", exact=True).click()
                        page.wait_for_load_state("load")
                        page.reload()
                        assert policy.locator('[name="auto_approve_all"]').is_checked()
                        policy.locator('[name="auto_approve_all"]').uncheck()
                        policy.get_by_role("button", name="Save", exact=True).click()
                        page.wait_for_load_state("load")
                    if path == "services":
                        for kind in ("sonarr", "lidarr", "radarr"):
                            page.locator(f'[data-service="{kind}"]').click()
                            page.wait_for_url(f"**/services#{kind}")
                            page.locator(f"#{kind}").wait_for(state="visible")
                            assert page.locator(f"#{kind}").is_visible()
                            assert page.locator(".service-config:visible").count() == 1
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), path
                    page.screenshot(path=artifacts / f"{path}-mobile.png", full_page=True)
                    page.set_viewport_size({"width": 1440, "height": 1000})
                update_flow(page, f"http://127.0.0.1:{port}", artifacts, errors)
                for language in (
                    "en-us",
                    "de-de",
                    "es-es",
                    "fr-fr",
                    "it-it",
                    "nl-be",
                    "pl-pl",
                    "pt-pt",
                    "ru-ru",
                ):
                    page.goto(f"http://127.0.0.1:{port}/?lang={language}")
                    assert page.locator("html").get_attribute("lang") == language[:2]
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), language
                    page.set_viewport_size({"width": 1440, "height": 1000})
                page.goto(f"http://127.0.0.1:{port}/?lang=en-us")
                assert page.locator("img.app-logo").count() == 4
                assert page.locator("img.app-logo").evaluate_all("images => images.every(img => img.complete && img.naturalWidth > 0)")
                page.set_viewport_size({"width": 390, "height": 844})
                page.screenshot(path=artifacts / "dashboard-mobile.png", full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.get_by_role("button", name="Navigation", exact=True).click()
                assert page.locator("#navigation").is_visible()
                assert page.get_by_role("button", name="Sign out", exact=True).is_visible()
                page.keyboard.press("Escape")
                assert page.get_by_role("button", name="Navigation", exact=True).get_attribute("aria-expanded") == "false"
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.get_by_role("button", name="Sign out", exact=True).click()
                page.wait_for_url(f"http://127.0.0.1:{port}/login")
                page.screenshot(path=artifacts / "login-desktop.png", full_page=True)
                page.locator('[name="username"]').fill("browser-owner")
                page.locator('[name="password"]').fill("browser-test-password")
                page.get_by_role("button", name="Sign in", exact=True).click()
                page.wait_for_url(f"http://127.0.0.1:{port}/")
                assert not errors, errors
                browser.close()
            print("Browser smoke passed: setup, navigation, nine locales, mobile layout, login/logout")
        finally:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False
                )
            else:
                process.terminate()
            process.wait(timeout=15)
            log.close()


if __name__ == "__main__":
    main()
