"""Crustdata API client. The agent talks to Crustdata only through this module.

Contract: public functions never raise. On failure they return None and set
`last_error` so the caller can say *why* data is missing (no match vs. out of
credits vs. API down) instead of guessing.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional; plain env vars still work
    pass

BASE_URL = "https://api.crustdata.com"
API_VERSION = "2025-11-01"
TIMEOUT_S = 30
MAX_RETRIES = 3
# 400/401/402/403/404 won't change on retry; 429 and 5xx might.
_RETRYABLE = {429, 500, 502, 503, 504}

log = logging.getLogger("crustdata")
_session = requests.Session()

last_error: str | None = None
"""Why the most recent call returned None (e.g. '402 insufficient_credits: ...')."""


def _headers() -> dict[str, str] | None:
    key = os.environ.get("CRUSTDATA_API_KEY", "").strip()
    if not key:
        return None
    return {
        "authorization": f"Bearer {key}",
        "content-type": "application/json",
        "x-api-version": API_VERSION,
    }


def _wait_seconds(resp: requests.Response | None, attempt: int) -> float:
    """Server's x-ratelimit-reset if present, else exponential backoff; plus jitter."""
    reset = resp.headers.get("x-ratelimit-reset") if resp is not None else None
    base = float(reset) if reset and reset.replace(".", "", 1).isdigit() else 2.0**attempt
    return min(base, 60.0) + random.uniform(0, 1)


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> Any | None:
    """Send one API call with retries. Returns parsed JSON, or None on any failure."""
    global last_error
    last_error = None
    headers = _headers()
    if headers is None:
        last_error = "CRUSTDATA_API_KEY is not set"
        log.error(last_error)
        return None

    resp: requests.Response | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = _session.request(method, BASE_URL + path, headers=headers, json=body, timeout=TIMEOUT_S)
        except requests.RequestException as e:
            last_error = f"network error: {e}"
            resp = None
        else:
            if resp.ok:
                # Pace ourselves before the server makes us: sliding-window limit.
                if resp.headers.get("x-ratelimit-remaining") == "0":
                    time.sleep(_wait_seconds(resp, attempt))
                try:
                    return resp.json() if resp.content else {}
                except ValueError:
                    last_error = f"{resp.status_code} non-JSON response"
                    log.error("%s %s: %s", method, path, last_error)
                    return None
            last_error = _describe_error(resp)
            if resp.status_code not in _RETRYABLE:
                break
        if attempt < MAX_RETRIES:
            wait = _wait_seconds(resp, attempt)
            log.warning("%s %s failed (%s), retry %d in %.1fs", method, path, last_error, attempt + 1, wait)
            time.sleep(wait)

    log.error("%s %s gave up: %s", method, path, last_error)
    return None


def _describe_error(resp: requests.Response) -> str:
    """'<status> <error.type>: <error.message>' from Crustdata's error envelope."""
    try:
        err = resp.json().get("error", {})
        return f"{resp.status_code} {err.get('type', '')}: {err.get('message', '')}".strip()
    except (ValueError, AttributeError):
        return f"{resp.status_code} {resp.text[:200]}"


def ping() -> bool:
    """Check that the API key works. Free call (GET /account/credits)."""
    data = _request("GET", "/account/credits")
    return bool(data and "account" in data)


def get_credits() -> float | None:
    """Remaining credit balance for the account, or None on failure. Free call."""
    data = _request("GET", "/account/credits")
    try:
        return float(data["account"]["credits"]) if data else None
    except (KeyError, TypeError, ValueError):
        return None
