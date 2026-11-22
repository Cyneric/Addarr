# Release acceptance

Record live test results and known limits before publishing a stable release.

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

## v2.0.0 acceptance

The maintainer confirmed these live checks on [v2.0.0a1](https://github.com/Cyneric/Addarr/releases/tag/v2.0.0a1). The stable release changes the version and documentation. The application behavior is unchanged.

- [x] Live Telegram bot with real users.
- [x] NAS deployment, backup restoration and container rollback.
- [x] 24-hour NAS run.
- Native-speaker review of all nine language catalogs is still pending. Automated tests check completeness and placeholders. Browser smoke tests check navigation in each locale.

## Publishing a release

For changes to Telegram, check commands and menus for each media kind, photos and fallback, advanced selections, access approval, invites, stale callbacks and revocation. For deployment changes, check volume ownership, LAN or VPN access, backup and restore, upgrade and rollback. Use a 24-hour run to check recovery from outages, rate limits and restarts during submission or delivery.

1. Record the service versions, test results and known limits in the release notes.
2. Update the version in `pyproject.toml` and `addarr/__init__.py`. Regenerate `uv.lock` and `requirements.txt`.
3. Push a matching `v2.*` tag after acceptance. Publish the GitHub release once the tagged image is available for both platforms.

The tag-triggered release workflow runs verification before publishing AMD64/ARM64 images to GHCR. Configure package visibility after first publication. No image or GitHub release is published by running local tests.

## Operator recovery

- Service credentials or invalid defaults: correct Services configuration, test it, then retry the failed request.
- Ambiguous search: inspect command history in Radarr/Sonarr/Lidarr. If the matching command exists, retry Addarr so it reconciles. If history expired, perform the intended search in that service, then retry while the matching command remains visible. Never clear the operation ledger to guess whether an action occurred.
- Blocked Telegram user or exhausted notification attempts: inspect Diagnostics. Request history remains authoritative; changing notification settings does not recreate old events.
- Backup restoration: stop Addarr, preserve the current data directory separately, restore the downloaded database into an empty writable data directory as `addarr.db`, then start the matching image. A new OS lock file is created. Restore neither a mismatched WAL file nor a newer database into an older image.
