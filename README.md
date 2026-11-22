<img src="addarr/static/logos/addarr.svg" alt="Addarr logo" width="88" height="88">

# Addarr

Request movies, TV shows and music in Telegram. Addarr sends approved requests to Radarr, Sonarr or Lidarr. Admins review requests and manage access in the web interface.

Version 2 replaces Addarr Refresh. If you already run Refresh, see [how to import your installation](docs/MIGRATION.md).

![Addarr overview showing recent requests, download progress and connected services](docs/images/dashboard.png)

## Docker setup

Save [`docker-compose.yml`](https://raw.githubusercontent.com/Cyneric/Addarr/v2.0.0/docker-compose.yml) in a new directory. Create a `config` folder next to it. On Linux, run `sudo chown 1000:1000 config` so Addarr can write to it, or set `PUID` and `PGID` in `.env` to match the folder's owner and group.

For the [stable release](https://github.com/Cyneric/Addarr/releases/tag/v2.0.0), set `ADDARR_VERSION=2.0.0` in `.env`.

Run these commands from the directory with the Compose file:

```sh
docker compose pull
docker compose up -d
```

On the Docker host, open <http://127.0.0.1:8090>. To connect from another device on your LAN or VPN, set `ADDARR_BIND` in `.env` to the host's address on that network.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ADDARR_BIND` | `127.0.0.1` | Host address for the web interface |
| `ADDARR_PORT` | `8090` | Host port for the web interface |
| `ADDARR_CONFIG` | `./config` | Host directory mounted at `/config` |
| `PUID` / `PGID` | `1000` / `1000` | Container user and group |
| `ADDARR_VERSION` | `main` | Image tag. Use `2.0.0` for this release or `main` for preview builds. |

Addarr stores its SQLite database in the config directory. Keep it on local storage, off SMB and NFS shares.

### First run

1. Open the setup page and create an admin account with the token from `config/bootstrap-token`. Addarr deletes the token after setup.
2. In **Services**, enter the URL and API key for at least one media service. Use its LAN address or its name on a shared Docker network. `localhost` inside the container points to Addarr itself. Click **Test connection**, then choose your defaults and save. Lidarr also needs a metadata profile.
3. If an older Addarr instance uses the same Telegram bot token, stop that instance first. In **Settings**, enter the token, choose a language and enable the bot.
4. Send `/start` to the bot in a private chat. In **Users**, check your Telegram user ID and approve access. To grant someone else access, you can also send them a single-use invite.

## Using Addarr

In Telegram, send `/start` to open the menu or search with `/movie`, `/series` or `/music`. Requests wait for admin approval by default. Send `/requests` to check their status.

- [Telegram commands, approvals and group chats](docs/TELEGRAM.md)
- [Download progress with SABnzbd](docs/TELEGRAM.md#download-progress)
- [Import an older Addarr installation](docs/MIGRATION.md)
- [Update Addarr with Docker Compose or the web updater](docs/UPDATES.md)

## Backups and password recovery

Use **Download backup** in the web sidebar or run:

```sh
uv run addarr --data-dir ./config backup /safe/location/addarr.db
```

Store backups somewhere private. They contain service credentials and admin account data.

To reset a web account's password:

```sh
uv run addarr --data-dir ./config reset-password USERNAME
```

Enter the new password when prompted. The terminal hides what you type. The reset signs out all web sessions.

## Development

Install Python 3.13 and uv, then run:

```sh
uv sync --frozen --group dev
uv run addarr --data-dir ./config serve --host 127.0.0.1
```

After installing the dependencies, you can also start Addarr with `python run.py`. Put `--data-dir` before the subcommand. `--help` and `--version` work without a config file.

To build and run the Docker image from this checkout:

```sh
docker compose -f docker-compose.yml -f compose.build.yml up -d --build
```

To run the checks:

```sh
uv run pytest -q
uv run mypy addarr
uv run ruff check addarr tests
```

See the [architecture notes](docs/ARCHITECTURE.md) for request states and error handling, and the [release checklist](docs/RELEASE-CHECKLIST.md) for browser, container, migration and live-service tests.

## License

Addarr uses the [MIT license](LICENSE). See the bundled [HTMX license](addarr/static/htmx.LICENSE) and [logo sources](addarr/static/logos/SOURCES.md).
