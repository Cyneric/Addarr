# Release acceptance

This is an alpha rebuild. Do not describe it as a production-validated release until the outstanding live checks are complete.

## Automated checks

```sh
uv sync --frozen --group dev
uv run ruff check addarr tests
uv run mypy addarr
uv run pytest -q
uv run playwright install chromium
uv run python scripts/browser_smoke.py
docker build -t addarr:rebuild .
uv run python scripts/container_smoke.py addarr:rebuild
docker buildx build --platform linux/arm64 --load -t addarr:rebuild-arm64 .
uv run python scripts/container_smoke.py addarr:rebuild-arm64
uv run python scripts/live_arr_smoke.py
```

Live-service tests create and remove only their own disposable containers and anonymous volumes. They perform real metadata lookups and additions, with no indexers/download clients. Search-command submission is exercised against those empty integrations. They do not touch configured personal services. Results, screenshots and browser logs go under ignored `artifacts/`.

## Verified in the implementation environment

- Unit, composed Telegram dispatch, web, migration, translation and recovery tests.
- Type checks and lint.
- Real Chromium: bootstrap setup, authenticated navigation, all nine locales, mobile layout, login/logout.
- Disposable Radarr 6.3.0.10514, Sonarr 4.0.19.2979 and Lidarr 3.1.0.4875: search, add, reconciliation and progress; Lidarr album add.
- Container architecture and restart results are recorded in `IMPLEMENTATION-STATUS.md` after verification.

## Required before public release

- [ ] Dedicated live Telegram bot: commands and menu flows for every media kind, photos and fallback, advanced selections, two users, approval/rejection, invites, stale callbacks and revocation.
- [ ] NAS deployment: correct volume ownership, LAN/VPN access, backup download and restore, container upgrade and rollback.
- [ ] 24-hour NAS soak: repeated service outages, Telegram outage, rate limiting, restart during submission and restart during notification delivery; no lost accepted requests or uncontrolled retry loops.
- [ ] Review all nine catalogs, including new approval and migration wording. Automated checks establish completeness and formatting; native-speaker review is recommended.
- [ ] Record service and image versions, timing, logs and any limitations in the release notes.
- [ ] Bump the Python version string and image tag together, update lock/export files, then push a `v2.*` tag only after acceptance.

The tag-triggered release workflow runs verification before publishing AMD64/ARM64 images to GHCR. Configure package visibility after first publication. No image or GitHub release is published by running local tests.

## Operator recovery

- Service credentials or invalid defaults: correct Services configuration, test it, then retry the failed request.
- Ambiguous search: inspect command history in Radarr/Sonarr/Lidarr. If the matching command exists, retry Addarr so it reconciles. If history expired, perform the intended search in that service, then retry while the matching command remains visible. Never clear the operation ledger to guess whether an action occurred.
- Blocked Telegram user or exhausted notification attempts: inspect Diagnostics. Request history remains authoritative; changing notification settings does not recreate old events.
- Backup restoration: stop Addarr, preserve the current data directory separately, restore the downloaded database into an empty writable data directory as `addarr.db`, then start the matching image. A new OS lock file is created. Restore neither a mismatched WAL file nor a newer database into an older image.
