# Addarr v2 architecture

The application is a single Python process. FastAPI owns its lifespan: open the database, construct a pooled HTTP client, start the request, Telegram, download and update-check workers, then cancel and await them on shutdown. Candidates wait in maintenance mode before starting these workers. An OS file lock prevents a second application using the same data directory. No application module reads configuration or starts I/O during import.

## Boundaries

| Module | Responsibility |
| --- | --- |
| `domain` | Validated service configuration, external media identity, search result and request options; categorized service failures |
| `store` | SQLite transactions, schema version, consistent backups and audit storage |
| `engine` | Authorization, approval transitions, submission recovery, availability and notification events |
| `downloads` | Read-only SABnzbd tracking through Arr media and download IDs |
| `updates` | Upstream commit checks and the web client for the companion |
| `updater` | Restricted Docker replacement, backup and rollback |
| `adapters` | Radarr v3, Sonarr v3 and Lidarr v1 HTTP contracts and reconciliation |
| `telegram_bot` | Private and allowed-group commands, expiring user/chat/topic-bound selections, polling lifecycle and outbox delivery |
| `web` | Administrator sessions, CSRF/origin checks, setup, settings, migration review and diagnostics |
| `migration` | Read-only legacy parsing and explicit, transactional import |
| `i18n` | Shared nine-language UI messages with matching placeholder contracts |

The web interface is server-rendered; HTMX refreshes diagnostics using authenticated HTML fragments. Service configuration and request mutations are form endpoints, not a supported third-party public REST API. `/health/live` and `/health/ready` expose process readiness, maintenance state and build identity. Service outages appear in authenticated diagnostics and do not make the container restart itself.

## Request lifecycle

Members create `pending` requests; administrators and trusted members create `queued` requests. Admin approval changes pending to queued. The worker durably marks a request `submitting` before network I/O. Successful submission becomes `submitted`; verified files become `available`. Open-ended artist/series monitoring remains submitted with progress. Rejection, cancellation and failure are explicit states.

New requests check the live library by catalog ID before they are stored. Existing movies and whole-series requests are rejected, while missing unmonitored seasons can still be requested. Search-result badges are advisory; confirmation repeats the check. Submission reconciliation stays separate so interrupted remote writes can recover.

The worker recovers submitting rows to queued after a restart. Service lookup reconciles existing external media identities before creating anything. Request scope uses stable IDs and normalized options, not translated titles. Identical requests from different users retain separate histories but share an existing submission. Existing profiles, paths and unrelated monitored seasons/albums are preserved. Service addresses form part of request and operation identity; changing an address stops old requests from being applied to a different library.

Search commands have their own durable operation ledger. Known-success commands are not sent again. An interrupted command is reconciled against the service's command history; if that history cannot establish acceptance, the request needs operator review. The application does not claim exactly-once execution across independent databases.

Notification events and outbox rows commit in the same transaction as request transitions. Successful sends are recorded; transient failures back off and exhausted deliveries remain visible. Telegram has no idempotency key for sends: a connection loss or crash after Telegram accepts a message but before local acknowledgement can cause a repeated notification. Media submissions use separate reconciliation and are not blindly repeated.

## Configuration and persistence

Web request actions wait for the current worker tick before cancelling or deleting a request. Cancellation stops local tracking without undoing remote work. Deletion sets the schema version 3 `deleted` flag, hides the record from request lists and discards unsent notifications. IDs and audit records stay in place to prevent old callback and command-ledger keys from referring to a new request. Existing databases are backed up before the schema upgrade.

`/config/addarr.db` is the single source of truth for settings, users, sessions, requests, operations, imports and notification delivery. YAML is an import format only. WAL mode, full synchronization, busy timeouts and short transactions protect local writes. Store the directory on a local filesystem (a local NAS disk is fine), not an SMB/NFS database share.

All schema changes must increment `PRAGMA user_version` through an explicit transaction. Newer database versions are rejected. Backups use SQLite's online backup API, not a copy of the live main database file. Downgrades require the corresponding old backup and image.

The first web administrator is created using `/config/bootstrap-token`; successful setup removes that token. Passwords use Argon2, sessions use random tokens stored as hashes, and mutations require CSRF and same-origin checks. Invites are single-use, expire after 24 hours and grant member access only. Imported users remain pending, including proposed Telegram administrators. Telegram numeric user IDs, not usernames or group membership alone, determine private authorization. Explicit group IDs grant request access only within that group; revoked users remain denied. Group grants never activate pending users or their proposed admin roles. Requests persist their originating group and topic, and the worker rechecks the current group allowlist before submission. Notification delivery rechecks it too. Schema version 2 adds request origins and outbox topics, with an automatic backup before upgrading an existing version 1 database.

## Retired interfaces

Shared-password `/auth`, custom command aliases, text-file access lists as runtime storage, import-time configuration prompts, download-client controls, library deletion, native installers and Helm are outside this release. `run.py` delegates to the v2 CLI. The old `src/`, `helm/`, installer scripts and translation files remain historical references and are excluded from the container. The `legacy/pre-v2` tag preserves the original runnable revision.

## Validation strategy

Tests use a stateful HTTP fixture whose remote writes survive an engine replacement, and actual python-telegram-bot dispatch with simulated Telegram transport. Browser checks launch the actual server. Disposable live-service checks run current media-service containers without indexers or download clients. Container checks verify setup, persisted sessions across restart/kill, non-root operation and graceful shutdown. A real Telegram bot and NAS soak remain release acceptance work, not something fixtures can certify.

## Code documentation

Keep a file header with its filename, author, original creation date and purpose in maintained source files. Use Python docstrings and JavaScript JSDoc for interfaces, especially return values, errors, side effects and ownership of resources. Explain retry and transaction rules where they apply. Short helpers only need a sentence when the signature leaves something unclear. Preserve third-party headers in vendored assets.

## Download tracking and updates

`downloads.py` is a read-only integration alongside the media request engine.
It reads each enabled Arr queue once per polling cycle, pages through history
for missed jobs, and matches remote media IDs to the configured download-client
name and SABnzbd `nzo_id`. Album requests use their album IDs; selected seasons
use episode or season IDs. Titles are display text, never identity keys.

Schema version 4 adds `downloads` and `request_downloads`. A job can belong to
several requests, such as a shared season pack. Job phase is separate from request
state. Only the existing Arr imported-file checks can mark a request available.
Status polling runs every 15 seconds; history is refreshed every minute. A
missing job is unknown, and observations older than 60 seconds display as stale.
Phase changes enter the existing durable outbox and obey notification and
user/group access settings. Deleted and cancelled requests stop participating.

`updates.py` checks GitHub ancestry and resolves immutable GHCR tags to digests.
`updater.py` runs only in the optional Docker companion. Its authenticated API
accepts a protocol version and commit, never shell commands, image URLs or target
container names. It verifies the candidate independently of the web app.

Update state is an atomic, fsynced JSON file outside SQLite. The candidate reads
it from a read-only mount as its maintenance gate. Container configuration lives
in a separate root-only file. Backup and replacement steps are journaled before
execution; recovery before commit restores the stopped app's data, while recovery
after commit finishes activation and cleanup. Data is never rolled back after
normal workers have been enabled.

API references: [SABnzbd](https://sabnzbd.org/wiki/configuration/5.1/api),
[Sonarr queue](https://github.com/Sonarr/Sonarr/blob/develop/src/Sonarr.Api.V3/Queue/QueueController.cs),
[Arr history client identities](https://github.com/Sonarr/Sonarr/blob/develop/src/NzbDrone.Core/History/HistoryService.cs).
