"""
Filename: migration.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Preview and import legacy configuration without granting users access automatically.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import yaml

from .domain import ServiceConfig
from .i18n import LOCALES
from .store import Store


def parse_legacy(content: str, lists: dict[str, str] | None = None) -> dict[str, Any]:
    """Validate legacy YAML and build an import report without writing to the database.

    Args:
        content: YAML configuration text, limited to 1 MB when encoded.
        lists: Optional text files keyed by legacy filename, such as admin.txt.

    Returns:
        Services, users, warnings, settings and a digest of the supplied input.
        This report contains credentials; use public_report() for display.

    Raises:
        ValueError: Invalid YAML, unsupported structure or invalid service data.
    """
    if len(content.encode()) > 1_000_000:
        raise ValueError("Legacy configuration exceeds 1 MB")
    try:
        raw = yaml.safe_load(content)
    except (yaml.YAMLError, RecursionError) as exc:
        raise ValueError("Invalid YAML configuration") from exc
    if not isinstance(raw, dict):
        raise ValueError("Configuration must be a YAML mapping")
    for section in ("radarr", "sonarr", "lidarr", "telegram"):
        if section in raw and raw[section] is not None and not isinstance(raw[section], dict):
            raise ValueError(f"{section} must be a mapping")
    for section in ("radarr", "sonarr", "lidarr"):
        old = raw.get(section) or {}
        for field in ("server", "auth", "features", "paths", "quality", "tags"):
            if field in old and not isinstance(old[field], dict):
                raise ValueError(f"{section}.{field} must be a mapping")
    for field in ("admins", "allow_list", "authenticated_users", "chat_id"):
        if raw.get(field) is not None and not isinstance(raw[field], list):
            raise ValueError(f"{field} must be a list")
    report: dict[str, Any] = {
        "services": {},
        "users": [],
        "warnings": [],
        "settings": {},
        "digest": hashlib.sha256((content + json.dumps(lists or {}, sort_keys=True)).encode()).hexdigest(),
    }
    known = {
        "radarr",
        "sonarr",
        "lidarr",
        "telegram",
        "language",
        "admins",
        "allow_list",
        "authenticated_users",
        "chat_id",
        "transmission",
        "sabnzbd",
        "security",
        "entrypoints",
        "logging",
        "monitoring",
    }
    for key in raw.keys() - known:
        report["warnings"].append(f"Unmapped setting: {key}")
    for kind in ("radarr", "sonarr", "lidarr"):
        old = raw.get(kind) or {}
        if not old:
            continue
        server, auth = old.get("server", {}), old.get("auth", {})
        enabled = bool(old.get("enable", False))
        if not enabled:
            report["warnings"].append(f"{kind}: disabled configuration retained only in original source")
            continue
        address = str(server.get("addr", "localhost"))
        if "://" not in address:
            protocol = "https" if server.get("ssl") else "http"
            address = f"{protocol}://{address}"
            if server.get("port"):
                address += f":{server['port']}"
        address = address.rstrip("/") + "/" + str(server.get("path", "")).strip("/")
        features = old.get("features", {})
        availability = features.get("minimumAvailability", "released")
        if availability == "preDB":
            availability = "released"
            report["warnings"].append(f"{kind}: legacy preDB availability becomes released")
        config = ServiceConfig.model_validate(
            dict(
                kind=kind,
                url=address,
                api_key=auth.get("apikey") or "",
                username=auth.get("username") or "",
                password=auth.get("password") or "",
                quality_profile=old.get("qualityProfileId"),
                root_folder=old.get("rootFolderPath", ""),
                metadata_profile=old.get("metadataProfileId"),
                search=features.get("search", True),
                minimum_availability=availability,
                season_folder=features.get("seasonFolder", True),
                tags=old.get("tags", {}).get("default", []),
                requester_tag=old.get("tags", {}).get("addRequesterIdTag", False),
            )
        )
        report["services"][kind] = config.model_dump(mode="json")
        report["warnings"].append(
            f"{kind}: review profile, folder, exclusions and monitoring defaults before enabling polling"
        )
        for key in old.keys() - {
            "enable",
            "server",
            "auth",
            "features",
            "paths",
            "quality",
            "tags",
            "adminRestrictions",
            "metadataProfileId",
            "qualityProfileId",
            "rootFolderPath",
        }:
            report["warnings"].append(f"Unmapped setting: {kind}.{key}")
        for section, supported in {
            "features": {"search", "minimumAvailability", "seasonFolder"},
            "paths": set(),
            "quality": set(),
            "tags": {"default", "addRequesterIdTag"},
        }.items():
            for key in (old.get(section) or {}).keys() - supported:
                report["warnings"].append(f"Review unmapped setting: {kind}.{section}.{key}")
        if old.get("adminRestrictions"):
            report["warnings"].append(
                f"{kind}: admin-only restrictions require review; imported users remain pending"
            )
    identities: dict[int, str] = {}
    for key in ("authenticated_users", "allow_list", "admins", "chat_id"):
        for value in raw.get(key, []) or []:
            try:
                user_id = int(value)
            except (ValueError, TypeError):
                report["warnings"].append(f"Invalid identity in {key}; not imported")
                continue
            if user_id <= 0:
                report["warnings"].append("Group chat identity not imported; private chats only")
            else:
                identities[user_id] = (
                    "admin" if key == "admins" or identities.get(user_id) == "admin" else "member"
                )
    for name, text in (lists or {}).items():
        for value in text.replace(",", "\n").splitlines():
            try:
                user_id = int(value.strip())
            except ValueError:
                if value.strip():
                    report["warnings"].append(f"Unrecognized entry in {name}")
                continue
            if user_id > 0:
                identities[user_id] = (
                    "admin" if name == "admin.txt" or identities.get(user_id) == "admin" else "member"
                )
            else:
                report["warnings"].append(f"Group entry in {name} not imported")
    report["users"] = [{"id": key, "role": role} for key, role in identities.items()]
    language = raw.get("language", "en-us")
    report["settings"]["language"] = language if language in LOCALES else "en-us"
    token = (raw.get("telegram") or {}).get("token")
    if token:
        report["settings"]["telegram_token"] = str(token)
    report["warnings"].extend(
        [
            "Shared passwords are retired. Imported identities require explicit administrator approval.",
            "Polling remains disabled. Stop the old bot before enabling this installation.",
            "Download controls, custom command aliases, group access and legacy logging/monitoring settings are not imported.",
        ]
    )
    return report


def public_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return preview fields with service credentials and the Telegram token omitted."""
    return {
        "services": list(report["services"]),
        "users": report["users"],
        "warnings": report["warnings"],
        "language": report["settings"].get("language"),
        "digest": report["digest"],
    }


def apply_import(store: Store, report: dict[str, Any]) -> None:
    """Back up the database and apply a validated report in one transaction.

    Imported users remain pending and polling is disabled. Existing service
    settings, conflicting bot tokens and repeated imports raise ValueError.
    The report must come from parse_legacy(); this function does not reparse it.
    """
    if store.one("SELECT digest FROM imports WHERE digest=?", (report["digest"],)):
        raise ValueError("This import was already applied")
    backups = store.directory / "backups"
    backups.mkdir(exist_ok=True)
    store.backup(backups / f"before-import-{time.time_ns()}.db")
    with store.transaction():
        for kind, config in report["services"].items():
            if store.setting(f"service:{kind}"):
                raise ValueError(
                    f"Existing {kind} configuration would be overwritten; import only into a fresh setup"
                )
            store.set_setting(f"service:{kind}", config)
        for key, value in report["settings"].items():
            if store.setting(key) not in (None, "", value) and key == "telegram_token":
                raise ValueError("Existing Telegram token conflicts with the import")
            store.set_setting(key, value)
        for user in report["users"]:
            store.execute(
                "INSERT OR IGNORE INTO users(id,name,role,status) VALUES(?,?,?,'pending')",
                (user["id"], str(user["id"]), user["role"]),
            )
        store.set_setting("polling_enabled", False)
        store.execute("INSERT INTO imports VALUES(?,?)", (report["digest"], time.time()))
        store.audit("migration", "legacy_import")


def read_legacy(path: Path) -> dict[str, Any]:
    """Read a YAML file or directory plus adjacent legacy user lists, then build an import report."""
    config = path / "config.yaml" if path.is_dir() else path
    lists = {
        name: (config.parent / name).read_text(encoding="utf-8")
        for name in ("admin.txt", "allowlist.txt", "chatid.txt")
        if (config.parent / name).exists()
    }
    return parse_legacy(config.read_text(encoding="utf-8"), lists)
