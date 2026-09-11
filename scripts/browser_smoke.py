"""
Filename: browser_smoke.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Browser checks against a temporary Addarr server with no external services.
"""

import socket
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


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
                for path in ("services", "users", "requests", "settings", "migration", "diagnostics"):
                    response = page.goto(f"http://127.0.0.1:{port}/{path}")
                    assert response.status == 200, path
                    assert page.locator("h1").is_visible()
                    page.screenshot(path=artifacts / f"{path}-desktop.png", full_page=True)
                    if path == "settings":
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
