"""Run: python -m crustdata.test_client

1. Offline checks of retry / never-raise behaviour (no key or credits needed).
2. Live connectivity check: ping() with CRUSTDATA_API_KEY.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest import mock

import requests

from crustdata import client


def _resp(status: int, body: Any = None, headers: dict[str, str] | None = None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = b"" if body is None else __import__("json").dumps(body).encode()
    r.headers.update(headers or {})
    return r


def offline_checks() -> None:
    ok = {"account": {"credits": 15000}}
    err402 = {"error": {"type": "insufficient_credits", "message": "out"}}
    with mock.patch.dict(os.environ, {"CRUSTDATA_API_KEY": "test"}), mock.patch.object(client.time, "sleep"):
        # 429 then 200 -> retried, succeeds
        with mock.patch.object(client._session, "request", side_effect=[_resp(429, headers={"x-ratelimit-reset": "1"}), _resp(200, ok)]) as m:
            assert client.ping() is True and m.call_count == 2
        # 402 -> no retry, None, reason recorded
        with mock.patch.object(client._session, "request", return_value=_resp(402, err402)) as m:
            assert client.get_credits() is None and m.call_count == 1
            assert client.last_error and "insufficient_credits" in client.last_error
        # network errors every time -> gives up, never raises
        with mock.patch.object(client._session, "request", side_effect=requests.ConnectionError("down")) as m:
            assert client.ping() is False and m.call_count == client.MAX_RETRIES + 1
        # garbage body -> None, not an exception
        bad = _resp(200)
        bad._content = b"<html>oops"
        with mock.patch.object(client._session, "request", return_value=bad):
            assert client.get_credits() is None
    with mock.patch.dict(os.environ, {"CRUSTDATA_API_KEY": ""}):
        assert client.ping() is False and "not set" in (client.last_error or "")
    print("offline checks: OK")


def live_check() -> bool:
    if client.ping():
        print(f"ping: OK - API key works, {client.get_credits()} credits left")
        return True
    print(f"ping: FAILED - {client.last_error}")
    return False


if __name__ == "__main__":
    offline_checks()
    sys.exit(0 if live_check() else 1)
