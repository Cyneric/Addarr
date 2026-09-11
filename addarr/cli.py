"""
Filename: cli.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Commands for serving Addarr, importing configuration, backups and password resets.
"""

import argparse
import getpass
import json
import logging
import os
from pathlib import Path

import uvicorn
from argon2 import PasswordHasher

from . import __version__
from .migration import apply_import, public_report, read_legacy
from .store import Store
from .web import create_app


def main() -> None:
    """Parse CLI arguments and serve the application or run one maintenance command.

    Serving is the default. Migration only previews unless --apply is supplied.
    Password resets read the password interactively and invalidate all sessions.
    Maintenance commands close their Store before returning.
    """
    parser = argparse.ArgumentParser(description="Addarr media requests")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("ADDARR_DATA_DIR", "/config")))
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8090)
    migrate = commands.add_parser("migrate")
    migrate.add_argument("source", type=Path)
    migrate.add_argument("--apply", action="store_true")
    backup = commands.add_parser("backup")
    backup.add_argument("destination", type=Path)
    reset = commands.add_parser("reset-password")
    reset.add_argument("username")
    args = parser.parse_args()
    if args.command in (None, "serve"):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        # HTTP client logs can contain the Telegram token in request URLs.
        logging.getLogger("httpx").setLevel(logging.CRITICAL)
        logging.getLogger("httpcore").setLevel(logging.CRITICAL)
        logging.getLogger("telegram").setLevel(logging.CRITICAL)
        uvicorn.run(
            create_app(args.data_dir),
            host=getattr(args, "host", "0.0.0.0"),
            port=getattr(args, "port", 8090),
            access_log=False,
            forwarded_allow_ips="",
        )
        return
    if args.command == "migrate":
        report = read_legacy(args.source)
        print(json.dumps(public_report(report), indent=2, ensure_ascii=False))
        if not args.apply:
            return
    store = Store(args.data_dir)
    try:
        if args.command == "migrate":
            apply_import(store, report)
        elif args.command == "backup":
            if args.destination.exists():
                parser.error("Backup destination already exists")
            store.backup(args.destination)
        elif args.command == "reset-password":
            password = getpass.getpass("New password (12+ characters): ")
            if len(password) < 12 or password != getpass.getpass("Confirm password: "):
                parser.error("Password too short or confirmation did not match")
            with store.transaction():
                result = store.execute(
                    "UPDATE admins SET password=? WHERE username=?",
                    (PasswordHasher().hash(password), args.username),
                )
                if not result.rowcount:
                    parser.error("Unknown administrator")
                store.execute("DELETE FROM sessions")
                store.audit("cli", "password_reset")
    finally:
        store.close()


if __name__ == "__main__":
    main()
