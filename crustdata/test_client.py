"""Run: python -m crustdata.test_client          (offline checks + live ping, free)
     python -m crustdata.test_client --full   (+ live smoke test of every function, ~4 credits first run, cached after)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from unittest import mock

import requests

from crustdata import client


def _resp(status: int, body: Any = None, headers: dict[str, str] | None = None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = b"" if body is None else json.dumps(body).encode()
    r.headers.update(headers or {})
    return r


def check_transport() -> None:
    ok = {"account": {"credits": 15000}}
    err402 = {"error": {"type": "insufficient_credits", "message": "out"}}
    with mock.patch.dict(os.environ, {"CRUSTDATA_API_KEY": "test"}), mock.patch.object(client.time, "sleep"):
        with mock.patch.object(client._session, "request", side_effect=[_resp(429, headers={"x-ratelimit-reset": "1"}), _resp(200, ok)]) as m:
            assert client.ping() is True and m.call_count == 2, "429 should be retried"
        with mock.patch.object(client._session, "request", return_value=_resp(402, err402)) as m:
            assert client.get_credits() is None and m.call_count == 1, "402 must not be retried"
            assert "insufficient_credits" in (client.last_error or "")
        with mock.patch.object(client._session, "request", side_effect=requests.ConnectionError("down")) as m:
            assert client.ping() is False and m.call_count == client.MAX_RETRIES + 1
        bad = _resp(200)
        bad._content = b"<html>oops"
        with mock.patch.object(client._session, "request", return_value=bad):
            assert client.get_credits() is None
        # creating a watch: a 500 must NOT be retried (could create a duplicate)
        with mock.patch.object(client._session, "request", return_value=_resp(500, {"error": {}})) as m:
            assert client.watch_company(1, notify_emails=["team@x.com"]) is None and m.call_count == 1
        with mock.patch.dict(os.environ, {"WATCH_WEBHOOK_URL": ""}):
            assert client.watch_company(1) is None and "needs webhook_url" in (client.last_error or "")
        with mock.patch.dict(os.environ, {"WATCH_WEBHOOK_URL": "https://x.ngrok.app/webhook"}), \
             mock.patch.object(client._session, "request", return_value=_resp(200, {"id": 77})) as m:  # fmt: skip
            assert client.watch_company(1) == 77
            assert m.call_args.kwargs["json"]["notifications"] == [{"type": "webhook", "url": "https://x.ngrok.app/webhook"}]
        # search with no criteria refuses without calling the API
        with mock.patch.object(client._session, "request") as m:
            assert client.search_companies() is None and m.call_count == 0
    with mock.patch.dict(os.environ, {"CRUSTDATA_API_KEY": ""}):
        assert client.ping() is False and "not set" in (client.last_error or "")


def check_signals_and_backtest() -> None:
    ts = [{"date": f"2025-{m:02d}-01", "employee_count": n} for m, n in [(1, 10), (5, 12), (8, 15), (11, 20)]]
    s = client.headcount_signals(ts)
    assert s["headcount_now"] == 20 and s["latest_point_date"] == "2025-11-01"
    assert s["headcount_3m_ago"] == 15 and s["headcount_6m_ago"] == 12 and s["headcount_12m_ago"] is None
    assert s["growth_3m_pct"] == 33.3 and s["growth_12m_pct"] is None
    past = client.headcount_signals(ts, "2025-06-15")  # backtest: later points invisible
    assert past["headcount_now"] == 12 and past["headcount_3m_ago"] == 10
    assert client.headcount_signals([])["headcount_now"] is None

    role = lambda t, s: {"title": t, "company_name": "X", "crustdata_company_id": 1, "start_date": s, "end_date": None,  # noqa: E731
                         "seniority_level": None, "function_category": None, "company_industries": [], "description": None}  # fmt: skip
    profile: Any = {
        "funding_rounds": [
            {"date": "2024-03-01", "round_type": "pre_seed", "amount_usd": 500000.0, "lead_investors": [], "investors": ["A"]},
            {"date": "2025-10-22", "round_type": "seed", "amount_usd": 6000000.0, "lead_investors": ["B"], "investors": ["B"]},
        ],
        "founders": [{"current_roles": [role("CEO", "2024-01-01"), role("Advisor", "2026-01-01")], "past_roles": [role("SRE", "2019-01-01")]}],
        "headcount_timeseries": ts, "open_jobs_count": 5, "funding_stage": "seed", "total_funding_usd": 6500000.0,
    }  # fmt: skip
    snap = client.snapshot_as_of(profile, "2025-06-01")
    assert [r["round_type"] for r in snap["funding_rounds"]] == ["pre_seed"]
    assert [r["round_type"] for r in snap["outcome_rounds"]] == ["seed"], "future round must be the outcome, not input"
    assert snap["funding_stage"] == "pre_seed" and snap["total_funding_usd"] == 500000.0 and snap["investors"] == ["A"]
    assert snap["headcount"] == 12 and snap["open_jobs_count"] is None
    assert [r["title"] for r in snap["founders"][0]["current_roles"]] == ["CEO"]


def check_normalizers() -> None:
    raw = {
        "crustdata_person_id": 7,
        "basic_profile": {"name": "A B", "current_title": "Co-Founder", "location": {"full_location": "Bengaluru"}},
        "social_handles": {"professional_network_identifier": {"profile_url": "https://linkedin.com/in/ab"}},
        "experience": {"employment_details": {"current": [{"title": "Co-Founder", "name": "Acme", "start_date": "2024-01-01T00:00:00"},
                                                          {"title": "Technical Advisor", "name": "Big Co"}], "past": None}},  # fmt: skip
        "education": {"schools": [{"school": "IIT Kanpur", "degree": ""}]},
    }
    p = client._norm_person(raw, "/person/search", "t")
    assert p["linkedin_url"] == "https://linkedin.com/in/ab" and p["location"] == "Bengaluru"
    assert p["current_roles"][0]["start_date"] == "2024-01-01" and p["past_roles"] == [] and p["education"][0]["degree"] is None
    assert p["source"]["record_id"] == 7 and p["source"]["url"] == p["linkedin_url"]
    assert [r["company_name"] for r in p["founder_roles"]] == ["Acme"]
    assert client._is_founder_title("Co-Founder, Data Scientist and CTO") and not client._is_founder_title("Associate Principal")
    assert client._norm_company({}, "/company/search", "t")["industries"] == []  # empty record doesn't crash

    event = {"metadata": {"watch_id": 9, "test": True}, "results": [{"changes": [{"field": "headcount.total", "type": "changed", "from": 1, "to": 2}],
             "record": {"crustdata_company_id": 5, "basic_info": {"name": "Co"}}}]}  # fmt: skip
    (e,) = client.parse_watch_event(event)
    assert e["watch_id"] == 9 and e["company_id"] == 5 and e["is_test"] and e["changes"][0]["to"] == 2
    assert client.parse_watch_event({}) == []


def check_email() -> None:
    contact = {"business_emails": [
        {"email": "old@other.com", "status": "deliverable", "crustdata_company_id": 1},
        {"email": "f@startup.com", "status": "unknown", "crustdata_company_id": 2},
        {"email": "founder@startup.com", "status": "deliverable", "crustdata_company_id": 2}]}  # fmt: skip
    body = [{"matched_on": "u", "matches": [{"person_data": {"contact": contact}}]}]
    with mock.patch.object(client, "_cached_post", return_value=(body, "t")):
        e = client.find_email("u", company_id=2)
        assert e and e["email"] == "founder@startup.com" and len(e["candidates"]) == 3, "prefer deliverable @ the startup"
        assert client.find_email("u")["email"] == "old@other.com"  # type: ignore[index]
    with mock.patch.object(client, "_cached_post", return_value=([{"matched_on": "u", "matches": []}], "t")):
        assert client.find_email("u")["email"] is None  # type: ignore[index]

    with mock.patch.dict(os.environ, {"DEMO_RECIPIENTS": "team1@gmail.com, team2@gmail.com,notanemail"}):
        r = client.outreach_recipient(42, "founder@startup.com")
        assert r and r["send_to"] in ("team1@gmail.com", "team2@gmail.com") and r["intended_for"] == "founder@startup.com"
        assert r["send_to"] == client.outreach_recipient(42)["send_to"]  # type: ignore[index]  # stable mapping
    with mock.patch.dict(os.environ, {"DEMO_RECIPIENTS": ""}):
        assert client.outreach_recipient(42, "founder@startup.com") is None, "must refuse rather than email a real person"


def check_cache(tmp: str) -> None:
    from pathlib import Path

    with mock.patch.object(client, "CACHE_DIR", Path(tmp)), mock.patch.object(client, "PRIVATE_CACHE_DIR", Path(tmp) / "private"), \
         mock.patch.dict(os.environ, {"CRUSTDATA_API_KEY": "test"}):  # fmt: skip
        with mock.patch.object(client._session, "request", return_value=_resp(200, {"ok": 1})) as m:
            client.set_cache_mode("on")
            assert client._cached_post("/x", {"a": 1})[0] == {"ok": 1} and client._cached_post("/x", {"a": 1})[0] == {"ok": 1}
            assert m.call_count == 1, "second call must come from cache"
            client._cached_post("/x", {"secret": 1}, private=True)
            assert len(list((Path(tmp) / "private").glob("*.json"))) == 1, "contact data goes to the git-ignored dir"
            client.set_cache_mode("only")
            assert client._cached_post("/x", {"a": 1})[0] == {"ok": 1}  # replay works
            assert client._cached_post("/x", {"new": 1})[0] is None and "cache miss" in (client.last_error or "")
            assert m.call_count == 2, "replay-only mode must never call the API"
        client.set_cache_mode("on")


def offline_checks() -> None:
    import tempfile

    with mock.patch.object(client, "CACHE_MODE", "off"):
        check_transport()
    with tempfile.TemporaryDirectory() as tmp:
        check_cache(tmp)
    check_email()
    check_signals_and_backtest()
    check_normalizers()
    print("offline checks: OK")


def live_ping() -> bool:
    if client.ping():
        print(f"ping: OK - API key works, {client.get_credits()} credits left")
        return True
    print(f"ping: FAILED - {client.last_error}")
    return False


def live_smoke() -> None:
    """One real call per function, on Crustdata itself (a known YC seed company)."""
    cid = 6036032
    comps = client.search_companies("developer tools infrastructure", country="IND", founded_after=2022, funding_stages=client.EARLY_STAGES, limit=3)
    print("search_companies:", [(c["name"], c["funding_stage"], c["headcount"]) for c in comps or []], client.last_error or "")
    founders = client.search_founders(company_ids=[cid], limit=3)
    print("search_founders:", [(p["name"], p["current_title"], len(p["past_roles"])) for p in founders or []], client.last_error or "")
    infra = client.search_founders(country="India", past_keywords=["infrastructure", "devops"], limit=3)
    print("search_founders(past infra, India):", [(p["name"], p["current_title"]) for p in infra or []], client.last_error or "")
    print("identify_company:", [(c["name"], c.get("confidence")) for c in client.identify_company(domain="crustdata.com") or []])
    prof = (client.enrich_companies([cid]) or {}).get(cid)
    assert prof, f"enrich failed: {client.last_error}"
    print("enrich_companies:", prof["name"], "| rounds:", [(r["date"], r["round_type"]) for r in prof["funding_rounds"]],
          "| leaders:", [(l["name"], l["title"]) for l in prof["leadership"]][:4], "| open jobs:", prof["open_jobs_count"])  # fmt: skip
    print("headcount_signals:", client.headcount_signals(prof["headcount_timeseries"]))
    snap = client.snapshot_as_of(prof, "2025-06-01")
    print("snapshot_as_of 2025-06-01: stage", snap["funding_stage"], "| headcount", snap["headcount"], "| outcome", [r["round_type"] for r in snap["outcome_rounds"]])
    h = client.get_hiring(cid, window_days=365)
    print("get_hiring:", {k: h[k] for k in ("postings_indexed_total", "recent_postings_count", "departments", "latest_posted_at")} if h else client.last_error)
    founder = next((f for f in prof["founders"] if f["linkedin_url"]), None)
    if founder:
        e = client.find_email(founder["linkedin_url"], company_id=cid)
        masked = (e["email"][0] + "***@" + e["email"].split("@")[1]) if e and e["email"] else None
        print("find_email:", founder["name"], "->", masked, e and e["status"], "|", client.last_error or "")
        print("outreach_recipient:", client.outreach_recipient(founder["crustdata_person_id"] or founder["name"] or "", masked), client.last_error or "")
    print("watch_company(dry_run):", client.watch_company(cid, headcount_threshold=60, dry_run=True), client.last_error or "")
    print("credits left:", client.get_credits())


if __name__ == "__main__":
    offline_checks()
    if not live_ping():
        sys.exit(1)
    if "--full" in sys.argv:
        live_smoke()
