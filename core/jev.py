"""
jev.py -- tiny stdlib client for TypeSafe's Jev via OpenRouter's Decisions API.

Jev doesn't write text: it answers typed questions (choice / noul / score) about
a `state` with calibrated probabilities. Every answer is cached on disk, keyed by
a hash of (model, state, questions), so a re-run costs nothing, returns the same
answer, and never needs the network.

The key comes from $OPENROUTER_API_KEY, else from the nearest `.env` walking up
from the working directory (worktrees sit under the main checkout, which holds it).
"""

import hashlib
import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"   # pinned: cached answers are only valid per version
_RETRY_STATUS = {408, 429}   # plus any 5xx -- see _post


def api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    for d in [Path.cwd(), *Path.cwd().parents]:
        env = d / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("OPENROUTER_API_KEY not set and not found in any parent .env")


class Jev:
    """ask(state, questions) -> answers dict, cached in `cache_path` (JSON)."""

    def __init__(self, cache_path, model=MODEL, attempts=5, timeout=20):
        self.path = Path(cache_path)
        self.cache = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.model, self.attempts, self.timeout = model, attempts, timeout
        self.cost = 0.0
        self._key = None
        self._lock = threading.Lock()

    def ask(self, state, questions):
        body = {"model": self.model, "state": state, "questions": questions}
        h = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if h in self.cache:
            return self.cache[h]
        resp = self._post(body)
        with self._lock:
            self.cache[h] = resp["answers"]
            self.cost += resp.get("usage", {}).get("cost", 0.0)
        return resp["answers"]

    def _post(self, body):
        self._key = self._key or api_key()
        data = json.dumps(body, ensure_ascii=False).encode()
        for attempt in range(self.attempts):
            req = urllib.request.Request(URL, data, {
                "Authorization": "Bearer " + self._key, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                retry = e.code in _RETRY_STATUS or e.code >= 500   # incl. Cloudflare's 52x
                if not retry or attempt == self.attempts - 1:
                    raise RuntimeError("Jev HTTP %d: %s" % (e.code, e.read()[:300])) from e
            # URLError, timeouts and dropped connections (RemoteDisconnected is
            # an OSError *and* an HTTPException, but not a URLError).
            except (OSError, http.client.HTTPException):
                if attempt == self.attempts - 1:
                    raise
            time.sleep(2 ** attempt)

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")


def ask_all(jev, fn, items, workers=8):
    """[fn(item) for item in items] across `workers` threads (each fn calls
    jev.ask), printing progress; the cache is saved even if a call fails."""
    out = []
    try:
        with ThreadPoolExecutor(workers) as ex:
            for i, r in enumerate(ex.map(fn, items), 1):
                out.append(r)
                if i % 250 == 0:
                    print("  %d/%d  ($%.4f so far)" % (i, len(items), jev.cost), flush=True)
    finally:
        jev.save()
    return out
