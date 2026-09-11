"""
Filename: container_smoke.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Container checks for setup, persistence, crash recovery and clean shutdown.
"""

import argparse
import json
import subprocess
import socket
import time
import uuid

import httpx


def docker(*args):
    """Run Docker and return captured output, raising CalledProcessError on failure."""
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT).strip()


def wait_ready(client):
    """Poll readiness for up to 120 attempts and raise RuntimeError if startup never succeeds."""
    for _ in range(120):
        try:
            if client.get("/health/ready").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("Container did not become ready")


def main():
    """Exercise a disposable non-root container through setup, restart, kill and orderly shutdown."""
    parser = argparse.ArgumentParser()
    parser.add_argument("image", default="addarr:rebuild", nargs="?")
    args = parser.parse_args()
    name = "addarr-smoke-" + uuid.uuid4().hex[:8]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        requested_port = sock.getsockname()[1]
    try:
        docker(
            "run",
            "-d",
            "--name",
            name,
            "--label",
            "addarr.test=true",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "-p",
            f"127.0.0.1:{requested_port}:8090",
            args.image,
        )
        port = docker("port", name, "8090/tcp").rsplit(":", 1)[1]
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", follow_redirects=True, timeout=30) as client:
            wait_ready(client)
            assert client.get("/").url.path == "/setup"
            token = docker("exec", name, "cat", "/config/bootstrap-token")
            response = client.post(
                "/setup",
                data={
                    "csrf": client.cookies["csrf"],
                    "bootstrap": token,
                    "username": "container-owner",
                    "password": "container-test-password",
                },
                headers={"Origin": f"http://127.0.0.1:{port}"},
            )
            assert response.status_code == 200 and response.url.path == "/"
            assert docker("exec", name, "id", "-u") == "1000"
            response = client.post("/settings", data={"csrf": client.cookies["csrf"], "language": "de-de"})
            assert response.status_code == 200
            docker("restart", name)
            wait_ready(client)
            assert client.get("/").url.path == "/", "Session did not survive restart"
            docker("kill", name)
            docker("start", name)
            wait_ready(client)
            assert client.get("/").url.path == "/", "Session did not survive process kill"
            assert client.get("/settings").status_code == 200
            docker("stop", "--time", "45", name)
            assert docker("inspect", "-f", "{{.State.ExitCode}}", name) == "0"
        print(
            json.dumps(
                {
                    "image": args.image,
                    "setup": True,
                    "restart": True,
                    "crash_recovery": True,
                    "non_root": True,
                    "read_only": True,
                    "clean_shutdown": True,
                }
            )
        )
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True, check=False)


if __name__ == "__main__":
    main()
