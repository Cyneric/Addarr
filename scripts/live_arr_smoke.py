"""
Filename: live_arr_smoke.py
Author: Christian Blank
Created Date: 2026-09-11
Description: API contract checks against disposable Arr containers without download clients or indexers.
"""

import asyncio
import json
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from addarr.adapters import ArrClient
from addarr.domain import Options, ServiceConfig, ServiceError
from addarr.store import Store


def docker(*args):
    """Run Docker and return captured output, raising CalledProcessError on failure."""
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT).strip()


async def submit_with_retry(client, request_id, reference, options):
    """Retry transient submissions while fresh Arr instances populate their metadata."""
    for attempt in range(30):
        try:
            return await client.submit(request_id, 1, reference, options)
        except ServiceError as exc:
            if not exc.retryable or attempt == 29:
                raise
            await asyncio.sleep(2)


async def check(name, kind, container_port, store):
    """Configure one disposable service and check lookup, submission, reconciliation and progress."""
    mapping = docker("port", name, f"{container_port}/tcp")
    port = mapping.rsplit(":", 1)[1]
    token = None
    for _ in range(90):
        try:
            config = ET.fromstring(docker("exec", name, "cat", "/config/config.xml"))
            token = config.findtext("ApiKey")
            if token:
                break
        except (subprocess.CalledProcessError, ET.ParseError):
            pass
        await asyncio.sleep(1)
    if not token:
        raise RuntimeError(f"{kind} startup failed")
    docker("exec", name, "mkdir", "-p", "/media")
    docker("exec", name, "chown", "1000:1000", "/media")
    config = ServiceConfig.model_validate(
        dict(kind=kind, url=f"http://127.0.0.1:{port}", api_key=token, search=True)
    )
    async with httpx.AsyncClient() as http:
        client = ArrClient(config, store, http)
        for attempt in range(90):
            try:
                caps = await client.capabilities()
                break
            except Exception:
                if attempt == 89:
                    raise
                await asyncio.sleep(1)
        config.quality_profile = caps["profiles"][0]["id"]
        config.root_folder = "/media"
        root_data = {"path": "/media"}
        if kind == "lidarr":
            config.metadata_profile = caps["metadata"][0]["id"]
            root_data.update(
                name="Test",
                defaultQualityProfileId=config.quality_profile,
                defaultMetadataProfileId=config.metadata_profile,
                defaultMonitorOption="none",
            )
        await client.call("POST", "rootfolder", data=root_data)
        term = {"radarr": "Big Buck Bunny", "sonarr": "Planet Earth", "lidarr": "Daft Punk"}[kind]
        result = await client.search(term)
        assert result, f"{kind}: no search results"
        opts = Options(monitoring="selected", seasons=[1]) if kind == "sonarr" else Options(monitoring="all")
        if kind == "lidarr":
            opts = Options(monitoring="all")
        remote_id = await submit_with_retry(client, 100 + container_port, result[0].ref, opts)
        second_id = await submit_with_retry(client, 100 + container_port, result[0].ref, opts)
        assert second_id == remote_id, "Reconciliation created a duplicate"
        done, progress = await client.progress(result[0].ref, opts, remote_id)
        assert not done
        summary = {
            "service": kind,
            "version": caps["version"],
            "search": True,
            "add": True,
            "search_command": True,
            "reconcile": True,
            "progress": progress[:300],
            "image": docker("inspect", "-f", "{{.Image}}", name),
        }
        if kind == "lidarr":
            albums = await client.search("Discovery", "album")
            assert albums, "No album results"
            # Select the same artist already in the library, without altering other albums.
            album = next((r for r in albums if r.ref.artist_id == result[0].ref.external_id), albums[0])
            await submit_with_retry(client, 99999, album.ref, Options())
            summary["album_add"] = True
        return summary


async def main():
    """Start three disposable Arr containers, collect contract results and remove their test volumes."""
    suffix = uuid.uuid4().hex[:8]
    containers = []
    with tempfile.TemporaryDirectory(prefix="addarr-live-") as directory:
        store = Store(Path(directory))
        try:
            for kind, port in (("radarr", 7878), ("sonarr", 8989), ("lidarr", 8686)):
                name = f"addarr-contract-{suffix}-{kind}"
                docker(
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--label",
                    "addarr.test=true",
                    "-e",
                    "PUID=1000",
                    "-e",
                    "PGID=1000",
                    "-p",
                    f"127.0.0.1::{port}",
                    f"lscr.io/linuxserver/{kind}:latest",
                )
                containers.append((name, kind, port))
            results = await asyncio.gather(
                *(check(name, kind, port, store) for name, kind, port in containers), return_exceptions=True
            )
            failures = []
            for (name, kind, port), result in zip(containers, results, strict=True):
                if isinstance(result, BaseException):
                    failures.append(f"{kind}: {type(result).__name__}: {result}")
                else:
                    print(json.dumps(result), flush=True)
            artifacts = Path("artifacts")
            artifacts.mkdir(exist_ok=True)
            (artifacts / "live-arr-results.json").write_text(
                json.dumps(
                    {
                        "results": [r for r in results if not isinstance(r, BaseException)],
                        "failures": failures,
                    },
                    indent=2,
                )
            )
            if failures:
                raise RuntimeError("; ".join(failures))
        finally:
            for name, _, _ in containers:
                docker("rm", "-f", "-v", name)
            store.close()


if __name__ == "__main__":
    asyncio.run(main())
