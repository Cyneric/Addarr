# Addarr v2 architecture

The application is a single Python process. FastAPI owns its lifespan: open the database, construct a pooled HTTP client, start the request worker and Telegram supervisor, then cancel and await both on shutdown. An OS file lock prevents a second application using the same data directory. No application module reads configuration or starts I/O during import.

## Boundaries

| Module | Responsibility |
| --- | --- |
| `domain` | Validated service configuration, external media identity, search result and request options; categorized service failures |
| `store` | SQLite transactions, schema version, consistent backups and audit storage |
| `engine` | Authorization, approval transitions, submission recovery, availability and notification events |
| `adapters` | Radarr v3, Sonarr v3 and Lidarr v1 HTTP contracts and reconciliation |
| `telegram_bot` | Private-chat commands, expiring user-bound selections, polling lifecycle and outbox delivery |
| `web` | Administrator sessions, CSRF/origin checks, setup, settings, migration review and diagnostics |
| `migration` | Read-only legacy parsing and explicit, transactional import |
| `i18n` | Shared nine-language UI messages with matching placeholder contracts |

The web interface is server-rendered; HTMX refreshes diagnostics using authenticated HTML fragments. Service configuration and request mutations are form endpoints, not a supported third-party public REST API. `/health/live` and `/health/ready` expose only process health. Service outages appear in authenticated diagnostics and do not make the container restart itself.

## Request lifecycle

Members create `pending` requests; administrators and trusted members create `queued` requests. Admin approval changes pending to queued. The worker durably marks a request `submitting` before network I/O. Successful submission becomes `submitted`; verified files become `available`. Open-ended artist/series monitoring remains submitted with progress. Rejection, cancellation and failure are explicit states.

The worker recovers submitting rows to queued after a restart. Service lookup reconciles existing external media identities before creating anything. Request scope uses stable IDs and normalized options, not translated titles. Identical requests from different users retain separate histories but share an existing submission. Existing profiles, paths and unrelated monitored seasons/albums are preserved. Service addresses form part of request and operation identity; changing an address stops old requests from being applied to a different library.

Search commands have their own durable operation ledger. Known-success commands are not sent again. An interrupted command is reconciled against the service's command history; if that history cannot establish acceptance, the request needs operator review. The application does not claim exactly-once execution across independent databases.

Notification events and outbox rows commit in the same transaction as request transitions. Successful sends are recorded; transient failures back off and exhausted deliveries remain visible. Telegram has no idempotency key for sends: a connection loss or crash after Telegram accepts a message but before local acknowledgement can cause a repeated notification. Media submissions use separate reconciliation and are not blindly repeated.

## Configuration and persistence

`/config/addarr.db` is the single source of truth for settings, users, sessions, requests, operations, imports and notification delivery. YAML is an import format only. WAL mode, full synchronization, busy timeouts and short transactions protect local writes. Store the directory on a local filesystem (a local NAS disk is fine), not an SMB/NFS database share.

All schema changes must increment `PRAGMA user_version` through an explicit transaction. Newer database versions are rejected. Backups use SQLite's online backup API, not a copy of the live main database file. Downgrades require the corresponding old backup and image.

The first web administrator is created using `/config/bootstrap-token`; successful setup removes that token. Passwords use Argon2, sessions use random tokens stored as hashes, and mutations require CSRF and same-origin checks. Invites are single-use, expire after 24 hours and grant member access only. Imported users remain pending, including proposed Telegram administrators. Telegram numeric user IDs, not usernames or group membership, determine authorization.

## Retired interfaces

Shared-password `/auth`, custom command aliases, text-file access lists as runtime storage, import-time configuration prompts, download-client controls, library deletion, native installers and Helm are outside this release. `run.py` delegates to the v2 CLI. The old `src/`, `helm/`, installer scripts and translation files remain historical references and are excluded from the container. The `legacy/pre-v2` tag preserves the original runnable revision.

## Validation strategy

Tests use a stateful HTTP fixture whose remote writes survive an engine replacement, and actual python-telegram-bot dispatch with simulated Telegram transport. Browser checks launch the actual server. Disposable live-service checks run current media-service containers without indexers or download clients. Container checks verify setup, persisted sessions across restart/kill, non-root operation and graceful shutdown. A real Telegram bot and NAS soak remain release acceptance work, not something fixtures can certify.

## Code documentation

Keep a file header with its filename, author, original creation date and purpose in maintained source files. Use Python docstrings and JavaScript JSDoc for interfaces, especially return values, errors, side effects and ownership of resources. Explain retry and transaction rules where they apply. Short helpers only need a sentence when the signature leaves something unclear. Preserve third-party headers in vendored assets.
