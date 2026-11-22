# Import an older Addarr installation

Open **Import legacy data** in the web interface and upload your old `config.yaml`. You can also include `admin.txt`, `allowlist.txt` and `chatid.txt`.

Review the preview before importing. Addarr backs up its database, leaves the original files alone and keeps the bot disabled. It keeps any service configuration you already saved in v2.

After importing, check profiles, folders, exclusions and monitoring settings in **Services**. Approve imported users in **Users**. Addarr does not use the old shared password or import group chat IDs. Add group chat IDs again in [Settings](TELEGRAM.md#group-chats).

To preview and apply an import from the command line:

```sh
uv run addarr --data-dir ./config migrate /path/to/old/install
uv run addarr --data-dir ./config migrate /path/to/old/install --apply
```

## What v2 does not support

V2 does not control download clients, delete media from your library, support Telegram broadcast channels or connect to multiple instances of the same service. Native installers and Helm are also unsupported. Use the [Docker setup](../README.md#docker-setup) for v2. The old scripts in the repository are for the [pre-v2 code](https://github.com/Cyneric/Addarr/tree/7dfed200795e2de90452c0511e50c2fc2c4042fc).
