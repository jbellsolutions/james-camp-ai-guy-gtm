"""Tiny stdlib HTTP client. Only GETs retry; a POST that may have been accepted is never repeated."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class HTTPError(RuntimeError):
    def __init__(self, status: int, body: str, accepted_maybe: bool = False):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status, self.body, self.accepted_maybe = status, body, accepted_maybe


def request(method: str, url: str, *, headers: dict | None = None, body: dict | None = None, timeout: float = 30,
            retries: int = 3, form: dict | None = None, basic: tuple[str, str] | None = None) -> dict:
    import base64
    import urllib.parse
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        ctype = {"Content-Type": "application/x-www-form-urlencoded"}
    else:
        data = json.dumps(body).encode() if body is not None else None
        ctype = {"Content-Type": "application/json"} if data else {}
    auth = {"Authorization": "Basic " + base64.b64encode(f"{basic[0]}:{basic[1]}".encode()).decode()} if basic else {}
    hdrs = {"Accept": "application/json", **ctype, **auth, **(headers or {})}
    attempts = retries if method == "GET" else 1
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode() or "{}"
                return json.loads(raw)
        except urllib.error.HTTPError as err:
            text = err.read().decode(errors="replace")
            if method == "GET" and err.code in (429, 500, 502, 503, 504) and attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise HTTPError(err.code, text) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            if method == "GET" and attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 8))
                continue
            # A POST that timed out may have been accepted by the provider.
            raise HTTPError(0, str(err), accepted_maybe=method != "GET") from None
    raise HTTPError(0, "retries exhausted")
