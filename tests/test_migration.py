"""
Filename: test_migration.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Legacy import checks for validation, backups and preserved access controls.
"""

import json
import sqlite3
from string import Formatter

import pytest
import yaml

from addarr.i18n import LOCALES, MESSAGES
from addarr.migration import apply_import, parse_legacy, public_report
from addarr.store import Store


def test_legacy_mapping_and_unknown_fields(tmp_path):
    content = """radarr:
  enable: true
  server: {addr: localhost, port: 7878, ssl: false, path: /radarr}
  auth: {apikey: PRIVATE}
  features: {minimumAvailability: preDB, search: false}
  paths: {excludedRootFolders: [/secret]}
  metadata: unknown
admins: [1]
authenticated_users: [2]
chat_id: [-100123]
unknown: value
"""
    report = parse_legacy(content, {"admin.txt": "3\n", "allowlist.txt": "4\n"})
    assert report["services"]["radarr"]["url"] == "http://localhost:7878/radarr"
    assert report["services"]["radarr"]["minimum_availability"] == "released"
    assert "PRIVATE" not in json.dumps(public_report(report))
    assert len(report["users"]) == 4
    assert any("excludedRootFolders" in w for w in report["warnings"])
    with_store = Store(tmp_path / "import")
    try:
        apply_import(with_store, report)
        assert all(u["status"] == "pending" for u in with_store.all("SELECT * FROM users"))
        with pytest.raises(ValueError, match="already applied"):
            apply_import(with_store, report)
        backups = list((with_store.directory / "backups").glob("*.db"))
        assert len(backups) == 1
        with sqlite3.connect(backups[0]) as backup:
            assert backup.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    finally:
        with_store.close()


@pytest.mark.parametrize(
    "content",
    ["[]", "null", "!!python/object/apply:os.system ['whoami']", "a" * 1_000_001],
    ids=["list", "null", "unsafe_tag", "oversize"],
)
def test_malformed_import_rejected(content):
    with pytest.raises((ValueError, yaml.YAMLError)):
        parse_legacy(content)


def test_catalog_complete_and_placeholders_match():
    parser = Formatter()
    for key, texts in MESSAGES.items():
        assert len(texts) == len(LOCALES), key
        fields = [{field for _, field, _, _ in parser.parse(text) if field} for text in texts]
        assert all(fields[0] == f for f in fields), key
        assert all(text.strip() for text in texts), key


def test_future_database_not_opened(tmp_path):
    store = Store(tmp_path)
    store.execute("PRAGMA user_version=999")
    store.close()
    with pytest.raises(RuntimeError, match="newer"):
        Store(tmp_path)
