"""Exercise a built app image with disposable, isolated Docker data.

Run: python scripts/smoke_container.py --image family-tree:local
Uses the fictional bundled GEDCOM. Never touches an existing installation.
"""
import argparse
import http.cookiejar
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=120)
    if result.returncode:
        raise RuntimeError(f"docker {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


class Client:
    def __init__(self):
        self.base = ""
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, data=None, *, content_type=None, status=200):
        headers = {"Content-Type": content_type} if content_type else {}
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=10) as response:
                actual, body = response.status, response.read()
        except urllib.error.HTTPError as error:
            actual, body = error.code, error.read()
        assert actual == status, f"{path}: expected HTTP {status}, got {actual}"
        return body

    def json(self, path, data=None, **kwargs):
        return json.loads(self.request(path, data, **kwargs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Existing app image to test")
    image = parser.parse_args().image
    run_id = uuid.uuid4().hex
    label = "family-tree.smoke-test"
    prefix = "family-tree-smoke-" + run_id
    containers, volumes = [], []
    owner, other = Client(), Client()

    def owned(kind, name):
        template = "{{json .Config.Labels}}" if kind == "container" else "{{json .Labels}}"
        labels = json.loads(docker(kind, "inspect", "--format", template, name))
        assert labels.get(label) == run_id, f"Refusing to modify unowned {kind} {name}"

    def volume(suffix):
        name = prefix + "-" + suffix
        docker("volume", "create", "--label", f"{label}={run_id}", name)
        owned("volume", name)
        volumes.append(name)
        return name

    def container(suffix, data_volume):
        name = prefix + "-" + suffix
        args = ["create", "--name", name, "--label", f"{label}={run_id}",
                "--publish", "127.0.0.1::8000", "--mount",
                f"type=volume,source={data_volume},target=/app/api_store",
                "--health-interval=1s", "--health-start-period=1s", "--health-retries=10"]
        for setting in ("APP_DATA_DIR=/app/api_store", "DATABASE_URL=sqlite:////app/api_store/app.db",
                        "SESSION_SECRET=", "SESSION_HTTPS_ONLY=0", "INVITE_CODE=",
                        "OPENROUTER_API_KEY=", "JEV_CACHE=/app/api_store/jev-cache.json"):
            args.extend(["--env", setting])
        docker(*args, image)
        owned("container", name)
        containers.append(name)
        return name

    def ready(name):
        binding = docker("port", name, "8000/tcp")
        assert re.fullmatch(r"127\.0\.0\.1:\d+", binding), "Test port is not loopback-only"
        base = "http://" + binding
        probe = Client()
        probe.base = base
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            state = json.loads(docker("inspect", "--format", "{{json .State}}", name))
            assert state["Running"], "App container exited before becoming ready"
            try:
                if state.get("Health", {}).get("Status") == "healthy":
                    assert probe.json("/api/health") == {"status": "ok"}
                    owner.base = other.base = base
                    return
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.5)
        raise AssertionError("App did not become healthy within 60 seconds")

    def check_tree(tree_id):
        assert owner.json("/api/auth/me")["email"] == "owner@example.test"
        assert owner.json(f"/api/trees/{tree_id}/meta")["n_people"] == 7
        rows = owner.json(f"/api/trees/{tree_id}/origins")["models"]["immigrant"]["breakdown"]
        assert {row["name"]: row["pct"] for row in rows} == {
            "Danish": 25.0, "Irish": 25.0, "Scottish": 25.0, "Norwegian": 25.0}
        assert len(owner.json(f"/api/trees/{tree_id}/fan")["recs"]) == 7
        other.request(f"/api/trees/{tree_id}/export", status=404)

    try:
        data_volume = volume("data")
        app = container("app", data_volume)
        docker("start", app)
        ready(app)
        html = owner.request("/").decode()
        assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
        assert assets, "Built frontend assets were not linked"
        for asset in assets:
            assert owner.request(asset), "A frontend asset was empty"
        assert len(owner.json("/world-countries.geojson")["features"]) == 177
        assert b"leaflet" in owner.request("/third-party-licenses.txt").lower()
        example = owner.request("/example.ged")
        assert b"fictional demonstration family" in example
        assert b"_FSFTID" not in example
        owner.request("/api/trees", status=401)
        credentials = {"email": "owner@example.test", "password": "fictional-smoke-password"}
        owner.json("/api/auth/register", credentials)
        boundary = "family-tree-smoke-" + run_id
        upload = (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
                  'filename="example.ged"\r\nContent-Type: text/plain\r\n\r\n').encode()
        upload += example + f"\r\n--{boundary}--\r\n".encode()
        tree = owner.json("/api/trees", upload, content_type="multipart/form-data; boundary=" + boundary)
        assert tree["meta"]["root"] == "Avery Example"
        other.json("/api/auth/register", {"email": "other@example.test", "password": "fictional-smoke-password"})
        check_tree(tree["id"])
        print("Image health, assets, example import, analysis, and account isolation passed.")

        docker("restart", app)
        ready(app)
        check_tree(tree["id"])
        owned("container", app)
        docker("rm", "--force", app)
        containers.remove(app)
        app = container("recreated", data_volume)
        docker("start", app)
        ready(app)
        check_tree(tree["id"])
        print("Restart and container replacement preserved accounts, trees, and sessions.")

        with tempfile.TemporaryDirectory(prefix="family-tree-smoke-") as temp:
            backup = Path(temp) / "app-data"
            docker("stop", app)
            docker("cp", app + ":/app/api_store", str(backup))
            assert (backup / "app.db").is_file(), "Database backup missing"
            assert len((backup / "session-secret").read_text().strip()) == 64
            restored = container("restored", volume("restored-data"))
            docker("cp", str(backup) + "/.", restored + ":/app/api_store")
            docker("start", restored)
            ready(restored)
            check_tree(tree["id"])
            # Account credentials must also survive, independently of the old cookie.
            owner.json("/api/auth/logout", {})
            owner.json("/api/auth/login", credentials)
            check_tree(tree["id"])
        print("Stopped-database backup and restoration into fresh storage passed.")
    finally:
        for name in containers:
            owned("container", name)
            docker("rm", "--force", name)
        for name in volumes:
            owned("volume", name)
            docker("volume", "rm", name)


if __name__ == "__main__":
    main()
