# Implementation status — 2026-09-11

Implemented on `rebuild/v2`, based on `7dfed200795e2de90452c0511e50c2fc2c4042fc`. Local baseline tag: `legacy/pre-v2`. Version: `2.0.0a1`.

## Delivered

- Single-process Python application with explicit lifecycle, SQLite schema/versioning and OS process lock.
- Web bootstrap/login, service testing and defaults, roles/access review, invites, approval queue, migration preview/apply, notification settings, diagnostics and consistent backups.
- Telegram commands and menus using the same request/authorization engine; expiring user-bound screens, profiles/folders, season selection, artist and album workflows, request decisions and persistent notifications.
- Service-specific adapters with bounded HTTP requests, full 2xx handling, exact identity matching, shared-submission reconciliation and a durable search-command ledger.
- Preservation of existing media settings; scoped season/album monitoring and separate availability tracking.
- Read-only legacy import, explicit unsupported-setting report, pre-import backup and review-required access.
- All nine UI catalogs, desktop/mobile layouts, bundled HTMX, Docker/Compose, locked dependencies and CI/release workflows.

## Verified locally

| Check | Result |
| --- | --- |
| Pytest | 60 tests passing |
| Ruff | Passed |
| Mypy | Passed for all 11 runtime modules |
| Chromium | Setup, login/logout, navigation, nine locales and mobile overflow checks passed |
| Package | Source archive and wheel built; templates, stylesheet and HTMX assets included |
| AMD64 container | Setup, non-root/read-only operation, restart, forced-stop recovery and graceful shutdown passed |
| ARM64 container | Same checks passed under Docker Desktop emulation |
| Radarr 6.3.0.10514 | Live metadata search, add, search-command submission, duplicate reconciliation and progress passed |
| Sonarr 4.0.19.2979 | Live series/season add, search-command submission, reconciliation and progress passed |
| Lidarr 3.1.0.4875 | Live artist and album add, metadata-delay recovery, search-command submission, reconciliation and progress passed |

Test services were disposable containers with no user libraries, indexers or download clients. Files in `artifacts/` contain screenshots and live-service version/image results. Two third-party TestClient deprecation warnings remain; they do not fail the tests.

## Outstanding release acceptance

- Live Telegram transport with a dedicated bot and real user accounts. Current Telegram tests exercise actual dispatcher composition against a simulated transport.
- NAS deployment/permissions/restore and the planned 24-hour outage/restart soak.
- Review of translated wording beyond automated catalog/placeholder checks.
- Execution of the new GitHub workflows and publication of the first GHCR image. Nothing has been pushed or published during local implementation.

These are explicit release limits. The rebuild should be evaluated as an alpha until live acceptance is recorded. See `RELEASE-CHECKLIST.md` for commands and recovery procedures.
