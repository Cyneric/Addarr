"""
Filename: updater_smoke.py
Author: Christian Blank
Created Date: 2026-09-12
Description: Disposable Docker upgrade and rollback checks using the real companion engine.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid


def docker(*args):
    """Run Docker without a shell; all resources use a unique test prefix."""
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT).strip()


def inside(target, image, revision, fail):
    """Exercise installation with an already-built local fixture image.

    Discovery and registry authorization are covered separately by HTTP tests.
    This runner bypasses only pulling the local fixture; container replacement,
    data backup, maintenance checks and rollback use production code.
    """
    from addarr.updater import Docker, UpdateManager

    daemon = Docker()
    manager = UpdateManager(Path("/state"), Path("/config"), target, daemon)
    original = daemon.inspect(target)
    manager.validate(original)
    with (manager.state / "original.json").open("w") as stream:
        json.dump(original, stream)
    (manager.state / "original.json").chmod(0o600)
    job_id = uuid.uuid4().hex[:12]
    active = manager.job.get("active_jobs", [])
    manager.job = {"id": job_id, "revision": revision, "image": image, "old_id": original["Id"],
                   "old_name": target, "backup_name": target + "-previous-" + job_id, "candidate": "",
                   "active_jobs": active}
    manager.save("pulling")
    daemon.pull = lambda _: None
    health = manager.healthy
    if fail:
        def reject_candidate(container, expected):
            if health(container, expected):
                # Simulate a migration that wrote new data before a startup check failed.
                Path("/config/candidate-only").write_text("must disappear on rollback")
                raise RuntimeError("Injected candidate failure after maintenance readiness")
            return False
        manager.healthy = reject_candidate
    manager.install()
    expected = "rolled_back" if fail else "succeeded"
    assert manager.job["phase"] == expected, manager.public()
    if fail:
        assert not Path("/config/candidate-only").exists()
        assert daemon.inspect(target)["Id"] == original["Id"]
    else:
        current = daemon.inspect(target)
        assert current["Id"] != original["Id"]
        for key in ("Binds", "ReadonlyRootfs", "CapDrop", "SecurityOpt", "Tmpfs", "Init"):
            assert current["HostConfig"].get(key) == original["HostConfig"].get(key), key
        assert current["Config"]["User"] == original["Config"]["User"]
        assert current["NetworkSettings"]["Ports"] == original["NetworkSettings"]["Ports"]
    print(json.dumps({"phase": expected, "backup": True, "configuration_preserved": True}))


def main():
    """Upgrade and roll back isolated data, leaving existing containers untouched."""
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", default="addarr:rebuild")
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--target")
    parser.add_argument("--revision", default="2" * 40)
    parser.add_argument("--fail", action="store_true")
    args = parser.parse_args()
    if args.inside:
        inside(args.target, args.image, args.revision, args.fail)
        return
    import httpx

    prefix = "addarr-update-test-" + uuid.uuid4().hex[:8]
    target, network = prefix, prefix + "-net"
    config, state = prefix + "-config", prefix + "-state"
    fixture = prefix + ":candidate"
    try:
        docker("build", "-t", fixture, "--build-arg", "ADDARR_REVISION=" + args.revision, ".")
        docker("network", "create", network)
        docker("volume", "create", config)
        docker("volume", "create", state)
        docker("run", "-d", "--name", target, "--label", "io.addarr.updates=enabled", "--label", "addarr.test=true",
               "--network", network, "--network-alias", "addarr", "--init", "--read-only", "--tmpfs", "/tmp",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
               "-p", "127.0.0.1::8090", "-v", config + ":/config", "-v", state + ":/updates:ro", args.image)
        port = docker("port", target, "8090/tcp").rsplit(":", 1)[1]
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", follow_redirects=True, timeout=10) as http:
            def ready():
                for _ in range(120):
                    try:
                        response = http.get("/health/ready")
                        if response.status_code == 200 and not response.json().get("maintenance"):
                            return
                    except httpx.HTTPError:
                        pass
                    time.sleep(1)
                raise RuntimeError("Test container did not become ready")

            ready()
            http.get("/setup")
            token = docker("exec", target, "cat", "/config/bootstrap-token")
            assert http.post("/setup", data={"csrf": http.cookies["csrf"], "bootstrap": token,
                                            "username": "upgrade-test", "password": "disposable-test-password"}).url.path == "/"
            session_digest = hashlib.sha256(http.cookies["session"].encode()).hexdigest()
            script = str(Path(__file__).resolve())
            for failure in (False, True):
                runner = prefix + "-runner"
                command = ["run", "--rm", "--name", runner, "--network", network, "--user", "0:0",
                           "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL", "--cap-add", "CHOWN",
                           "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER", "--security-opt", "no-new-privileges:true",
                           "-v", "/var/run/docker.sock:/var/run/docker.sock", "-v", config + ":/config",
                           "-v", state + ":/state", "--mount", f"type=bind,source={script},target=/runner.py,readonly",
                           "--entrypoint", "python", "-e", "PYTHONPATH=/app", fixture,
                           "/runner.py", "--inside", "--target", target, "--revision", args.revision, fixture]
                if failure:
                    command.append("--fail")
                print(docker(*command))
                ready()
                assert http.get("/").url.path == "/", "Admin session did not survive replacement"
                assert hashlib.sha256(http.cookies["session"].encode()).hexdigest() == session_digest
                assert http.get("/health/ready").json()["revision"] == args.revision
        print("Disposable upgrade and rollback passed; admin account and session survived both.")
    finally:
        # Names originate solely from this test's UUID prefix; never prune global resources.
        names = docker("ps", "-a", "--format", "{{.Names}}").splitlines()
        for name in names:
            if name == prefix or name.startswith(prefix + "-"):
                subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        for volume in (config, state):
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
        subprocess.run(["docker", "network", "rm", network], capture_output=True)
        subprocess.run(["docker", "image", "rm", fixture], capture_output=True)


if __name__ == "__main__":
    main()
