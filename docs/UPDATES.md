# Updating Addarr

Addarr checks `main` for new commits once an hour. When an update is ready,
**Update available** appears at the top of the app. Click **Update now** to
install it. No extra confirmation is needed. The page stays open while Addarr
restarts and shows **Updated** when it is ready.

**Diagnostics → Updates** contains the Check now button, commit history, build
information and updater connection status. A commit becomes installable after
GitHub finishes the tests and publishes its image.

Local builds show their status but cannot install an update automatically. This
prevents a published image from replacing work that exists only on your machine.
The revision in an ordinary local Docker build is `unknown`.

## Enable updates in the web UI

The optional updater is a separate container. It needs access to Docker to
replace Addarr, and write access to the same configuration directory. Addarr
itself runs without the Docker socket. The companion does not publish a host
port and accepts only authenticated requests for its configured Addarr container.

Start with a published image, keeping the configuration directory you already
use. From the checkout, generate a token once:

```sh
python -c "import secrets,pathlib; pathlib.Path('config-updater-token').write_text(secrets.token_urlsafe(48))"
chmod 444 config-updater-token
docker compose -f docker-compose.yml -f compose.updates.yml pull
docker compose -f docker-compose.yml -f compose.updates.yml up -d --no-build
```

Keep the token file in a private directory. It is mounted as a secret in both
containers and is excluded from Git. On Windows, generate the token with Python
and skip `chmod`. Docker Desktop must be running Linux containers.

Use `.env` to set `ADDARR_CONFIG` to your existing data directory, and retain
your current `ADDARR_PORT`, `ADDARR_BIND`, `PUID` and `PGID` values. If needed,
set `ADDARR_CONTAINER_NAME` to a unique container name. The companion uses this
name as its only target. Both containers must use the same Docker daemon.

Diagnostics shows whether the companion is reachable. If its protocol
is incompatible, update the companion manually with Compose before continuing.

## During an update

The companion pulls the exact published image digest before stopping Addarr.
It then stops the application and backs up `/config`, including the database,
settings and sessions. Existing backup archives are excluded. A failed backup
leaves the old version in place.

The new version starts in maintenance mode. It can migrate and check its database,
but it cannot accept changes, submit requests, or start Telegram and download
workers. After startup passes, the companion enables normal operation. The
browser reconnects automatically.

If startup fails or does not pass within two minutes, the companion stops the
candidate, saves its failed state when possible, restores the data backup, and
restarts the original container. The previous image remains on disk. Updates
preserve mounts, published ports, environment settings, network aliases and
container security settings.

The updater keeps its job state and the latest three update backups in the
`update_state` Docker volume. These backups contain credentials. Do not remove
that volume during an update. Failed-state archives are retained for inspection
and can be removed manually once the failure is understood. Application backup
files under `/config/backups` remain untouched.

The companion resumes recovery after a restart. Once it has enabled application
workers, it will finish cleanup instead of rolling the database back: those
workers may already have submitted requests to another service.

If recovery stops, keep both volumes and the original container. Inspect the
updater job and container state before making further changes. The app is held
in maintenance mode until recovery is resolved. Do not run two Addarr instances
against the same directory.

Automatic updates require an ordinary directory or volume at `/config`.
Symlinks inside that directory, nested mounts and auto-remove containers are
rejected because they cannot be backed up and restored reliably by this updater.

## Manual updates

You can still update without the companion:

```sh
docker compose pull addarr
docker compose up -d --no-build addarr
```

Choose the image tag in `ADDARR_VERSION` and keep the existing config mount.
Download a database backup first. For a manual downgrade after a schema change,
restore a backup created by the version you are returning to.

After a web update, Compose still contains the image tag from your deployment
file. Set `ADDARR_VERSION` to the installed `sha-<commit>` tag before recreating
the service with Compose, or use `main` when intentionally moving to its current
published build. A broad `docker image prune -a` may delete the previous image.

## Development checks

```sh
uv run pytest tests/test_updates.py -q
docker build -t addarr:test .
uv run python scripts/updater_smoke.py addarr:test
```

The smoke test creates its own containers, network and volumes. It verifies an
upgrade and an injected startup failure through the production replacement and
rollback code, including an administrator session and allocated host port.
Its candidate image is built locally. Registry discovery, immutable digests,
authorization and concurrency are covered by the HTTP and unit tests.
