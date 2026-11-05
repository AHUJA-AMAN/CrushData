"""Crustdata API layer. The agent talks to Crustdata only through this module.

Contract:
- Public functions never raise. On failure they return None and set `last_error`
  so the agent can say *why* data is missing (no match vs. out of credits vs. API
  down) instead of guessing.
- Every record carries a `source` dict (endpoint, record id, profile URL, when it
  was retrieved) so each fact in a memo can be cited.
- Read calls (search / enrich / identify / jobs) are cached on disk, so re-running
  a thesis or a backtest costs no extra credits and survives an API outage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TypedDict

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
CACHE_DIR = Path(os.environ.get("CRUSTDATA_CACHE_DIR") or Path(__file__).resolve().parent.parent / ".cache" / "crustdata")
# Contact data (real emails) is cached here, which is git-ignored: the repo is public.
PRIVATE_CACHE_DIR = CACHE_DIR / "private"
_CACHE_MODES = {"on", "off", "only"}
CACHE_MODE = {"1": "on", "0": "off"}.get(os.environ.get("CRUSTDATA_CACHE", "on"), os.environ.get("CRUSTDATA_CACHE", "on"))
"""on = use cache, call API on miss (default) | off = always call API | only = never call API (demo replay)."""

FOUNDER_TITLES = ["founder", "co-founder", "ceo", "cto"]
EARLY_STAGES = ["pre_seed", "angel", "seed"]

log = logging.getLogger("crustdata")
_session = requests.Session()

last_error: str | None = None
"""Why the most recent call returned None or partial data (e.g. '402 insufficient_credits: ...')."""


# --------------------------------------------------------------------------- types


class Source(TypedDict):
    provider: str
    endpoint: str
    record_id: int | str | None
    url: str | None  # public profile URL a human can open to check the fact
    retrieved_at: str  # ISO timestamp of the API call (original call if served from cache)


class Role(TypedDict):
    title: str | None
    company_name: str | None
    crustdata_company_id: int | None
    start_date: str | None  # YYYY-MM-DD
    end_date: str | None  # None = ongoing OR unknown (Crustdata leaves side roles open-ended)
    seniority_level: str | None
    function_category: str | None
    company_industries: list[str]
    description: str | None


class School(TypedDict):
    school: str | None
    degree: str | None
    field_of_study: str | None
    start_year: int | None
    end_year: int | None


class Person(TypedDict):
    crustdata_person_id: int | None
    name: str | None
    headline: str | None
    current_title: str | None
    location: str | None
    linkedin_url: str | None
    current_roles: list[Role]
    founder_roles: list[Role]  # current roles whose title says founder/CEO/CTO; may not be their primary job
    past_roles: list[Role]
    education: list[School]
    skills: list[str]
    recently_changed_jobs: bool | None
    source: Source


class Company(TypedDict):
    crustdata_company_id: int | None
    name: str | None
    description: str | None
    domain: str | None
    website: str | None
    linkedin_url: str | None
    industries: list[str]
    categories: list[str]
    country: str | None
    city: str | None
    headquarters: str | None
    year_founded: int | None
    headcount: int | None
    funding_stage: str | None  # last round type; None = no disclosed funding (NOT proof of pre-seed)
    total_funding_usd: float | None
    last_fundraise_date: str | None
    source: Source


class FundingRound(TypedDict):
    date: str | None
    round_type: str | None
    amount_usd: float | None
    lead_investors: list[str]
    investors: list[str]


class Leader(TypedDict):
    crustdata_person_id: int | None
    name: str | None
    title: str | None
    linkedin_url: str | None


class CompanyProfile(Company):
    funding_rounds: list[FundingRound]  # oldest first
    investors: list[str]
    founders: list[Person]  # full career history included
    leadership: list[Leader]  # founders + CXOs + decision makers, deduped
    headcount_timeseries: list[dict[str, Any]]  # [{date, employee_count}] oldest first, ~weekly
    open_jobs_count: int | None


class HeadcountSignals(TypedDict):
    as_of: str | None
    latest_point_date: str | None
    headcount_now: int | None
    headcount_3m_ago: int | None
    headcount_6m_ago: int | None
    headcount_12m_ago: int | None
    growth_3m_pct: float | None
    growth_6m_pct: float | None
    growth_12m_pct: float | None


class Posting(TypedDict):
    title: str | None
    department: str | None
    location: str | None
    posted_at: str | None
    url: str | None


class EmailLookup(TypedDict):
    linkedin_url: str
    email: str | None  # best real business email found: display + cite only, never send to it
    status: str | None  # "deliverable", "unknown", ...
    candidates: list[dict[str, Any]]  # every business email on file: {email, status, crustdata_company_id}
    source: Source


class Recipient(TypedDict):
    send_to: str  # always a team-owned DEMO_RECIPIENTS address
    intended_for: str | None  # the real founder email the message is written for
    demo_mode: bool


class Hiring(TypedDict):
    company_id: int
    as_of: str
    window_days: int
    postings_indexed_total: int | None  # all postings Crustdata ever indexed for the company
    recent_postings_count: int
    departments: dict[str, int]  # recent postings per department
    recent_titles: list[str]
    latest_posted_at: str | None
    recent_postings: list[Posting]
    source: Source


# ----------------------------------------------------------------------- transport


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


def _request(method: str, path: str, body: dict[str, Any] | None = None, idempotent: bool = True) -> Any | None:
    """Send one API call with retries. Returns parsed JSON, or None on any failure.

    Non-idempotent calls (creating a watch) retry only on 429, which means the
    server refused the request, so a retry can never create a duplicate.
    """
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
            if not idempotent:
                break
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
            retryable = _RETRYABLE if idempotent else {429}
            if resp.status_code not in retryable:
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def set_cache_mode(mode: str) -> None:
    """'on' (default), 'off' (always fresh), or 'only' (replay from cache, zero API calls).

    Hook this to main.py's --use-cache flag: set_cache_mode("only") for a Wi-Fi-proof demo.
    """
    global CACHE_MODE
    if mode not in _CACHE_MODES:
        raise ValueError(f"cache mode must be one of {sorted(_CACHE_MODES)}")
    CACHE_MODE = mode


def _cached_post(path: str, body: dict[str, Any], private: bool = False) -> tuple[Any | None, str]:
    """POST a read-only call through the on-disk cache. Returns (data, retrieved_at).

    private=True stores the response in the git-ignored PRIVATE_CACHE_DIR (contact data).
    ponytail: no TTL, cache lives for the hackathon; set_cache_mode("off") for fresh data.
    """
    global last_error
    key = hashlib.sha256(json.dumps([API_VERSION, path, body], sort_keys=True).encode()).hexdigest()[:32]
    file = (PRIVATE_CACHE_DIR if private else CACHE_DIR) / f"{key}.json"
    if CACHE_MODE != "off" and file.exists():
        try:
            hit = json.loads(file.read_text(encoding="utf-8"))
            last_error = None
            return hit["data"], hit["retrieved_at"]
        except (OSError, ValueError, KeyError):
            pass
    if CACHE_MODE == "only":
        last_error = f"cache miss in replay-only mode for {path} (run once online to record it)"
        return None, _now_iso()
    retrieved_at = _now_iso()
    data = _request("POST", path, body)
    if data is not None and CACHE_MODE == "on":
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps({"retrieved_at": retrieved_at, "data": data}), encoding="utf-8")
        except OSError as e:
            log.warning("cache write failed: %s", e)
    return data, retrieved_at


def _source(endpoint: str, retrieved_at: str, record_id: int | str | None, url: str | None) -> Source:
    return {"provider": "crustdata", "endpoint": endpoint, "record_id": record_id, "url": url, "retrieved_at": retrieved_at}


def _day(value: Any) -> str | None:
    """'2024-01-01T00:00:00' -> '2024-01-01'."""
    return str(value)[:10] if value else None


def _as_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


# --------------------------------------------------------------------- normalizers


def _norm_role(r: dict[str, Any]) -> Role:
    desc = r.get("description")
    return {
        "title": r.get("title"),
        "company_name": r.get("name") or r.get("company_name"),
        "crustdata_company_id": r.get("crustdata_company_id") or r.get("company_id"),
        "start_date": _day(r.get("start_date")),
        "end_date": _day(r.get("end_date")),
        "seniority_level": r.get("seniority_level"),
        "function_category": r.get("function_category"),
        "company_industries": r.get("company_industries") or [],
        "description": desc[:400] if isinstance(desc, str) and desc else None,
    }


def _is_founder_title(title: str | None) -> bool:
    words = (title or "").lower().replace("-", " ").replace("&", " ").replace(",", " ").split()
    return "founder" in words or "cofounder" in words or bool({"ceo", "cto"} & set(words))


def _norm_person(p: dict[str, Any], endpoint: str, retrieved_at: str) -> Person:
    bp = p.get("basic_profile") or {}
    exp = p.get("experience") or {}
    ed = exp.get("employment_details") or {}
    loc = bp.get("location")
    location = (loc.get("full_location") or loc.get("raw")) if isinstance(loc, dict) else loc
    linkedin = ((p.get("social_handles") or {}).get("professional_network_identifier") or {}).get("profile_url")
    schools = (p.get("education") or {}).get("schools") or []
    current = [_norm_role(r) for r in ed.get("current") or []]
    return {
        "crustdata_person_id": p.get("crustdata_person_id"),
        "name": bp.get("name"),
        "headline": bp.get("headline"),
        "current_title": bp.get("current_title"),
        "location": location,
        "linkedin_url": linkedin,
        "current_roles": current,
        "founder_roles": [r for r in current if _is_founder_title(r["title"])],
        "past_roles": [_norm_role(r) for r in ed.get("past") or []],
        "education": [
            {
                "school": s.get("school"),
                "degree": s.get("degree") or None,
                "field_of_study": s.get("field_of_study") or None,
                "start_year": s.get("start_year"),
                "end_year": s.get("end_year"),
            }
            for s in schools
        ],
        "skills": (p.get("skills") or {}).get("professional_network_skills") or [],
        "recently_changed_jobs": exp.get("recently_changed_jobs"),
        "source": _source(endpoint, retrieved_at, p.get("crustdata_person_id"), linkedin),
    }


def _norm_company(c: dict[str, Any], endpoint: str, retrieved_at: str) -> Company:
    bi = c.get("basic_info") or {}
    loc = c.get("locations") or {}
    tax = c.get("taxonomy") or {}
    fu = c.get("funding") or {}
    hc = c.get("headcount") or {}
    industries = tax.get("professional_network_industries") or (
        [tax["professional_network_industry"]] if tax.get("professional_network_industry") else []
    )
    cid = c.get("crustdata_company_id") or bi.get("crustdata_company_id")
    return {
        "crustdata_company_id": cid,
        "name": bi.get("name"),
        "description": bi.get("description"),
        "domain": bi.get("primary_domain"),
        "website": bi.get("website"),
        "linkedin_url": bi.get("professional_network_url"),
        "industries": industries,
        "categories": tax.get("categories") or [],
        "country": loc.get("country"),
        "city": loc.get("city"),
        "headquarters": loc.get("headquarters"),
        "year_founded": bi.get("year_founded"),
        "headcount": hc.get("total"),
        "funding_stage": fu.get("last_round_type"),
        "total_funding_usd": fu.get("total_investment_usd"),
        "last_fundraise_date": _day(fu.get("last_fundraise_date")),
        "source": _source(endpoint, retrieved_at, cid, bi.get("professional_network_url")),
    }


def _split_names(value: Any) -> list[str]:
    # ponytail: comma split breaks names like "Foo, Inc."; investors_detailed is preferred when present.
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [s.strip() for s in str(value).split(",") if s.strip()] if value else []


def _norm_profile(c: dict[str, Any], retrieved_at: str) -> CompanyProfile:
    base = _norm_company(c, "/company/enrich", retrieved_at)
    fu = c.get("funding") or {}
    rounds: list[FundingRound] = []
    for m in fu.get("milestones") or []:
        detailed = [i.get("name") for i in m.get("investors_detailed") or [] if i.get("name")]
        rounds.append(
            {
                "date": _day(m.get("date") or m.get("funding_date")),
                "round_type": m.get("round_type"),
                "amount_usd": m.get("amount_usd"),
                "lead_investors": _split_names(m.get("lead_investors")),
                "investors": detailed or _split_names(m.get("investors")),
            }
        )
    rounds.sort(key=lambda r: r["date"] or "")

    people = c.get("people") or {}
    founders = [_norm_person(p, "/company/enrich", retrieved_at) for p in people.get("founders") or []]
    leadership: list[Leader] = []
    seen: set[Any] = set()
    for group in ("founders", "cxos", "decision_makers"):
        for p in people.get(group) or []:
            person = _norm_person(p, "/company/enrich", retrieved_at)
            key = person["crustdata_person_id"] or person["name"]
            if key in seen:
                continue
            seen.add(key)
            leadership.append(
                {
                    "crustdata_person_id": person["crustdata_person_id"],
                    "name": person["name"],
                    "title": person["current_title"],
                    "linkedin_url": person["linkedin_url"],
                }
            )

    ts = sorted(
        ({"date": _day(p.get("date")), "employee_count": p.get("employee_count")} for p in (c.get("headcount") or {}).get("timeseries") or []),
        key=lambda p: p["date"] or "",
    )
    profile: CompanyProfile = {
        **base,  # type: ignore[typeddict-item]
        "funding_rounds": rounds,
        "investors": [i.get("name") for i in fu.get("investors_detailed") or [] if i.get("name")] or _split_names(fu.get("investors")),
        "founders": founders,
        "leadership": leadership,
        "headcount_timeseries": ts,
        "open_jobs_count": (c.get("hiring") or {}).get("openings_count"),
    }
    return profile


# ------------------------------------------------------------------------- health


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


# ------------------------------------------------------------- step 1: discovery


def search_companies(
    query: str | None = None,
    *,
    country: str | None = None,
    founded_after: int | None = None,
    max_headcount: int | None = None,
    funding_stages: list[str] | None = None,
    include_unfunded: bool = True,
    extra_filters: list[dict[str, Any]] | None = None,
    limit: int = 25,
) -> list[Company] | None:
    """Find companies matching a thesis. ~0.5 credits per result.

    query: natural-language thesis text, ranked hybrid search (e.g. "developer tools for infra teams").
    country: ISO-3 ("IND") or full name. founded_after: year, inclusive.
    funding_stages: last round types, e.g. EARLY_STAGES. include_unfunded keeps companies with no
      disclosed round, which is where "before their first round" founders are.
    extra_filters: raw Crustdata filter conditions, ANDed in.
    Max 100 results (one ranked page).
    """
    global last_error
    conds: list[dict[str, Any]] = []
    if country:
        conds.append({"field": "locations.country", "type": "=", "value": country})
    if founded_after:
        conds.append({"field": "basic_info.year_founded", "type": "=>", "value": founded_after})
    if max_headcount:
        conds.append({"field": "headcount.total", "type": "=<", "value": max_headcount})
    if funding_stages:
        stage = {"field": "funding.last_round_type", "type": "in", "value": funding_stages}
        if include_unfunded:
            stage = {"op": "or", "conditions": [stage, {"field": "funding.last_round_type", "type": "is_null", "value": None}]}
        conds.append(stage)
    conds.extend(extra_filters or [])
    if not query and not conds:
        last_error = "search_companies needs a query or at least one filter"
        return None

    body: dict[str, Any] = {
        "limit": max(1, min(limit, 100)),
        "fields": ["crustdata_company_id", "basic_info", "taxonomy", "locations", "funding", "headcount"],
    }
    if query:
        body["search"] = {"query": query, "mode": "hybrid"}
    if conds:
        body["filters"] = conds[0] if len(conds) == 1 else {"op": "and", "conditions": conds}
    data, at = _cached_post("/company/search", body)
    if data is None:
        return None
    out: dict[Any, Company] = {}
    for c in data.get("companies") or []:
        comp = _norm_company(c, "/company/search", at)
        out.setdefault(comp["crustdata_company_id"], comp)
    return list(out.values())


def search_founders(
    *,
    company_ids: list[int] | None = None,
    titles: list[str] | None = None,
    country: str | None = None,
    past_keywords: list[str] | None = None,
    past_company_ids: list[int] | None = None,
    schools: list[str] | None = None,
    extra_filters: list[dict[str, Any]] | None = None,
    limit: int = 25,
) -> list[Person] | None:
    """Find founders, with full career history and education included (no enrich call needed).

    ~0.4 credits per result. titles: current-title words, default FOUNDER_TITLES.
    country: full name, e.g. "India" (person data uses full names, not ISO codes).
    past_keywords: any past role whose title or description mentions one of these
      (e.g. ["infrastructure", "platform", "devops", "SRE"]) - the "prior experience" filter.
    """
    conds: list[dict[str, Any]] = [
        {"op": "or", "conditions": [{"field": "experience.employment_details.current.title", "type": "(.)", "value": t} for t in titles or FOUNDER_TITLES]}
    ]
    if company_ids:
        conds.append({"field": "experience.employment_details.current.company_id", "type": "in", "value": company_ids})
    if country:
        conds.append({"field": "basic_profile.location.country", "type": "=", "value": country})
    if past_keywords:
        conds.append(
            {
                "op": "or",
                "conditions": [{"field": "experience.employment_details.past.title", "type": "(.)", "value": k} for k in past_keywords]
                + [{"field": "experience.employment_details.past.description", "type": "[.]", "value": k} for k in past_keywords],
            }
        )
    if past_company_ids:
        conds.append({"field": "experience.employment_details.past.company_id", "type": "in", "value": past_company_ids})
    if schools:
        conds.append({"op": "or", "conditions": [{"field": "education.schools.school", "type": "(.)", "value": s} for s in schools]})
    conds.extend(extra_filters or [])

    body = {
        "filters": {"op": "and", "conditions": conds},
        "limit": max(1, min(limit, 100)),
        "fields": ["crustdata_person_id", "basic_profile", "experience", "education", "social_handles", "skills"],
    }
    data, at = _cached_post("/person/search", body)
    if data is None:
        return None
    out: dict[Any, Person] = {}
    for p in data.get("profiles") or []:
        person = _norm_person(p, "/person/search", at)
        out.setdefault(person["crustdata_person_id"], person)
    return list(out.values())


def identify_company(name: str | None = None, domain: str | None = None) -> list[Company] | None:
    """Resolve a name or domain to candidate companies, best match first. FREE.

    Each Company gets an extra `confidence` key (0-1). Several close matches means the
    identity is ambiguous, which per the spec is an exception for a human.
    """
    global last_error
    if not (name or domain):
        last_error = "identify_company needs a name or a domain"
        return None
    body = {"domains": [domain]} if domain else {"names": [name]}
    data, at = _cached_post("/company/identify", body)
    if data is None:
        return None
    out: list[Company] = []
    for entry in data if isinstance(data, list) else []:
        for m in entry.get("matches") or []:
            comp = _norm_company(m.get("company_data") or {}, "/company/identify", at)
            comp["confidence"] = m.get("confidence_score")  # type: ignore[typeddict-unknown-key]
            out.append(comp)
    return out


# --------------------------------------------------------- step 2: verification


def enrich_companies(company_ids: list[int]) -> dict[int, CompanyProfile | None] | None:
    """Full profiles: description, HQ, founding year, leadership, founders' careers,
    funding rounds with dates and investors, weekly headcount history, open jobs.

    2 credits per company. Returns {company_id: profile, or None if Crustdata has no match}.
    Returns None only if every batch failed.
    """
    global last_error
    ids = list(dict.fromkeys(int(i) for i in company_ids))
    out: dict[int, CompanyProfile | None] = {i: None for i in ids}
    errors: list[str] = []
    ok = False
    for batch in _chunks(ids, 25):
        body = {"crustdata_company_ids": batch, "fields": ["basic_info", "headcount", "funding", "people", "locations", "taxonomy", "hiring"]}
        data, at = _cached_post("/company/enrich", body)
        if data is None:
            errors.append(last_error or "unknown error")
            continue
        ok = True
        for entry in data if isinstance(data, list) else []:
            for m in (entry.get("matches") or [])[:1]:
                profile = _norm_profile(m.get("company_data") or {}, at)
                if profile["crustdata_company_id"] in out:
                    out[profile["crustdata_company_id"]] = profile
    last_error = "; ".join(errors) or None
    return out if ok else None


def enrich_people(linkedin_urls: list[str]) -> dict[str, Person | None] | None:
    """Full career history, education and skills for people found elsewhere. 1 credit per profile.

    Founders from search_founders / enrich_companies already include this; use this only
    for people known by LinkedIn URL alone. Returns {url: person, or None if no match}.
    """
    global last_error
    urls = list(dict.fromkeys(u for u in linkedin_urls if u))
    out: dict[str, Person | None] = {u: None for u in urls}
    errors: list[str] = []
    ok = False
    for batch in _chunks(urls, 25):
        body = {"professional_network_profile_urls": batch, "fields": ["basic_profile", "experience", "education", "skills", "social_handles"]}
        data, at = _cached_post("/person/enrich", body)
        if data is None:
            errors.append(last_error or "unknown error")
            continue
        ok = True
        for entry in data if isinstance(data, list) else []:
            matches = entry.get("matches") or []
            if matches and entry.get("matched_on") in out:
                out[entry["matched_on"]] = _norm_person(matches[0].get("person_data") or {}, "/person/enrich", at)
    last_error = "; ".join(errors) or None
    return out if ok else None


def find_email(linkedin_url: str, company_id: int | None = None) -> EmailLookup | None:
    """Look up a person's real business email. ~2 credits (enrich + business email add-on).

    Picks a deliverable address at company_id (the startup) first, then any deliverable
    one, then whatever exists. email=None means Crustdata has none on file.
    Use the result for the memo / UI only; send via outreach_recipient().
    """
    body = {"professional_network_profile_urls": [linkedin_url], "fields": ["contact.business_emails"]}
    data, at = _cached_post("/person/enrich", body, private=True)
    if data is None:
        return None
    raw: list[dict[str, Any]] = []
    for entry in data if isinstance(data, list) else []:
        for m in (entry.get("matches") or [])[:1]:
            raw = ((m.get("person_data") or {}).get("contact") or {}).get("business_emails") or []
    cands = [{"email": e.get("email"), "status": e.get("status"), "crustdata_company_id": e.get("crustdata_company_id")} for e in raw if e.get("email")]
    rank = lambda e: (e["crustdata_company_id"] != company_id, e["status"] != "deliverable")  # noqa: E731
    best = min(cands, key=rank) if cands else None
    return {
        "linkedin_url": linkedin_url,
        "email": best["email"] if best else None,
        "status": best["status"] if best else None,
        "candidates": cands,
        "source": _source("/person/enrich", at, None, linkedin_url),
    }


def demo_recipients() -> list[str]:
    """Team-owned inboxes from DEMO_RECIPIENTS in .env (comma-separated)."""
    return [a.strip() for a in os.environ.get("DEMO_RECIPIENTS", "").split(",") if "@" in a]


def outreach_recipient(person_key: int | str, real_email: str | None = None) -> Recipient | None:
    """Where an outreach email is actually sent: always one of DEMO_RECIPIENTS.

    The hackathon rules forbid agents contacting real people, so this never returns
    the real address as send_to. The same person always maps to the same demo inbox.
    Returns None (and sets last_error) if DEMO_RECIPIENTS is empty.
    """
    global last_error
    inboxes = demo_recipients()
    if not inboxes:
        last_error = "DEMO_RECIPIENTS is not set; refusing to email anyone (no real founders during the event)"
        return None
    i = int(hashlib.sha256(str(person_key).encode()).hexdigest(), 16) % len(inboxes)
    return {"send_to": inboxes[i], "intended_for": real_email, "demo_mode": True}


# ------------------------------------------------------------ step 3: signals


def headcount_signals(timeseries: list[dict[str, Any]], as_of: str | date | None = None) -> HeadcountSignals:
    """Headcount now / 3 / 6 / 12 months back and growth %, from a profile's headcount_timeseries.

    as_of: evaluate as if it were that date (backtest): only points on or before it count.
    A value is None when the company has no data that far back. Pure function, no API call.
    """
    pts = sorted(((d, p.get("employee_count")) for p in timeseries if (d := _as_date(p.get("date")))), key=lambda x: x[0])
    cutoff = _as_date(as_of)
    if cutoff:
        pts = [p for p in pts if p[0] <= cutoff]
    empty: HeadcountSignals = {
        "as_of": cutoff.isoformat() if cutoff else None, "latest_point_date": None, "headcount_now": None,
        "headcount_3m_ago": None, "headcount_6m_ago": None, "headcount_12m_ago": None,
        "growth_3m_pct": None, "growth_6m_pct": None, "growth_12m_pct": None,
    }  # fmt: skip
    if not pts:
        return empty
    anchor = cutoff or pts[-1][0]

    def at(day: date) -> int | None:
        before = [n for d, n in pts if d <= day]
        return before[-1] if before else None

    def growth(then: int | None) -> float | None:
        now = pts[-1][1]
        return round((now - then) / then * 100, 1) if then and now is not None else None

    m3, m6, m12 = (at(anchor - timedelta(days=d)) for d in (91, 182, 365))
    return {
        **empty,
        "as_of": anchor.isoformat(),
        "latest_point_date": pts[-1][0].isoformat(),
        "headcount_now": pts[-1][1],
        "headcount_3m_ago": m3,
        "headcount_6m_ago": m6,
        "headcount_12m_ago": m12,
        "growth_3m_pct": growth(m3),
        "growth_6m_pct": growth(m6),
        "growth_12m_pct": growth(m12),
    }


def snapshot_as_of(profile: CompanyProfile, as_of: str | date) -> dict[str, Any]:
    """The profile as it would have looked on `as_of`, for backtesting.

    Keeps only funding rounds, headcount points and founder roles dated on or before
    as_of. Rounds after as_of are returned separately as `outcome_rounds` (what we
    score the call against). `leakage_warnings` lists fields that are current-only
    and may reveal the future (the agent should not lean on them in a backtest).
    """
    cutoff = _as_date(as_of)
    day = cutoff.isoformat() if cutoff else str(as_of)
    known = [r for r in profile["funding_rounds"] if r["date"] and r["date"] <= day]
    later = [r for r in profile["funding_rounds"] if not r["date"] or r["date"] > day]

    def trim(p: Person) -> Person:
        keep = lambda r: bool(r["start_date"]) and r["start_date"] <= day  # noqa: E731
        return {**p, "current_roles": [r for r in p["current_roles"] if keep(r)], "past_roles": [r for r in p["past_roles"] if keep(r)]}

    amounts = [r["amount_usd"] for r in known if r["amount_usd"]]
    signals = headcount_signals(profile["headcount_timeseries"], cutoff)
    return {
        **profile,
        "as_of": day,
        "funding_rounds": known,
        "outcome_rounds": later,
        "funding_stage": known[-1]["round_type"] if known else None,
        "total_funding_usd": sum(amounts) if amounts else None,
        "last_fundraise_date": known[-1]["date"] if known else None,
        "investors": list(dict.fromkeys(i for r in known for i in r["investors"])),
        "founders": [trim(p) for p in profile["founders"]],
        "headcount": signals["headcount_now"],
        "headcount_timeseries": [p for p in profile["headcount_timeseries"] if p["date"] and p["date"] <= day],
        "open_jobs_count": None,
        "leakage_warnings": ["description", "leadership", "industries", "categories"],
    }


def get_hiring(company_id: int, *, window_days: int = 90, as_of: str | date | None = None) -> Hiring | None:
    """Job-posting signals for one company: recent postings, titles, departments, latest date.

    Crustdata has no 'posting still open' flag, so "active" = posted within window_days
    of as_of (default today). ~0.03 credits per posting returned (max 100).
    """
    anchor = _as_date(as_of) or date.today()
    conds: list[dict[str, Any]] = [{"field": "company.basic_info.company_id", "type": "=", "value": int(company_id)}]
    if as_of:
        conds.append({"field": "metadata.date_added", "type": "=<", "value": anchor.isoformat()})
    body = {
        "filters": conds[0] if len(conds) == 1 else {"op": "and", "conditions": conds},
        "sorts": [{"field": "metadata.date_added", "order": "desc"}],
        "limit": 100,
        "fields": ["crustdata_job_id", "job_details.title", "job_details.category", "job_details.url", "metadata.date_added", "location.raw"],
    }
    data, at = _cached_post("/job/search", body)
    if data is None:
        return None
    start = anchor - timedelta(days=window_days)
    postings: list[Posting] = []
    latest: str | None = None
    for j in data.get("job_listings") or []:
        jd = j.get("job_details") or {}
        posted = _day((j.get("metadata") or {}).get("date_added"))
        latest = max(latest or "", posted or "") or None
        d = _as_date(posted)
        if d and start <= d <= anchor:
            postings.append(
                {"title": jd.get("title"), "department": jd.get("category"), "location": (j.get("location") or {}).get("raw"), "posted_at": posted, "url": jd.get("url")}
            )
    return {
        "company_id": int(company_id),
        "as_of": anchor.isoformat(),
        "window_days": window_days,
        "postings_indexed_total": data.get("total_count"),
        "recent_postings_count": len(postings),
        "departments": dict(Counter(p["department"] or "Unknown" for p in postings).most_common()),
        "recent_titles": list(dict.fromkeys(p["title"] for p in postings if p["title"]))[:20],
        "latest_posted_at": latest,
        "recent_postings": postings[:20],
        "source": _source("/job/search", at, int(company_id), None),
    }


# --------------------------------------------------------------------- watchers


def _watch_track(headcount_threshold: int | None) -> dict[str, Any]:
    conds: list[dict[str, Any]] = [
        {"field": "funding.milestones", "type": "added", "keys": [["round_type", "date"]]},  # new round, once per round
        {"field": "people.founders", "type": "added", "keys": ["crustdata_person_id"]},  # leadership: new founder
        {"field": "people.cxos", "type": "added", "keys": ["crustdata_person_id"]},  # leadership: new CXO hire
    ]
    if headcount_threshold:
        conds.append({"field": "headcount.total", "type": "=>", "value": int(headcount_threshold)})
    return {"op": "or", "conditions": conds}


def watch_company(
    company_id: int,
    *,
    headcount_threshold: int | None = None,
    webhook_url: str | None = None,
    notify_emails: list[str] | None = None,
    every_hours: int = 24,
    dry_run: bool = False,
) -> int | None:
    """Watch a 'Watch'-decision company for: new funding round, new founder/CXO, and
    (if given) headcount reaching headcount_threshold. Returns the watch id.

    webhook_url defaults to WATCH_WEBHOOK_URL in .env (the backend's ngrok URL + /webhook);
    notify_emails is optional (team inboxes only!).
    Creating is free; each notification costs 5 credits. Never retried on server
    errors, so it can't create a duplicate watch.
    dry_run=True validates the setup via the free preview endpoint and returns 0.
    """
    global last_error
    track = _watch_track(headcount_threshold)
    fields = ["basic_info", "headcount", "funding", "people"]
    if dry_run:
        r = _request("POST", "/watch/company/test", {"track": track, "fields": fields, "deliver": False})
        return 0 if r is not None else None
    notifications: list[dict[str, Any]] = []
    webhook_url = webhook_url or os.environ.get("WATCH_WEBHOOK_URL", "").strip() or None
    if webhook_url:
        notifications.append({"type": "webhook", "url": webhook_url})
    if notify_emails:
        notifications.append({"type": "email", "to": notify_emails})
    if not notifications:
        last_error = "watch_company needs webhook_url (or WATCH_WEBHOOK_URL in .env) or notify_emails"
        return None
    body = {
        "entities": {"crustdata_company_ids": [int(company_id)]},
        "track": track,
        "config": {"trigger": {"type": "interval", "every_hours": every_hours}},
        "notifications": notifications,
        "fields": fields,
    }
    r = _request("POST", "/watch/company", body, idempotent=False)
    return r.get("id") if isinstance(r, dict) else None


def cancel_watch(watch_id: int) -> bool:
    """Delete a company watch. Free."""
    return _request("DELETE", f"/watch/company/{int(watch_id)}", idempotent=False) is not None


def list_watches() -> Any | None:
    """Active company watches on the account (raw API response). Free."""
    return _request("GET", "/watch/company?status=active&limit=100")


def parse_watch_event(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn a watcher webhook POST body into [{watch_id, company_id, company_name, changes, record}].

    changes: [{field, type, from, to}] or [{field, type: 'added', new_elements}].
    Test deliveries (metadata.test = true) come back with is_test=True.
    """
    meta = (payload or {}).get("metadata") or {}
    out = []
    for r in (payload or {}).get("results") or []:
        rec = r.get("record") or {}
        out.append(
            {
                "watch_id": meta.get("watch_id"),
                "is_test": bool(meta.get("test")),
                "company_id": rec.get("crustdata_company_id"),
                "company_name": (rec.get("basic_info") or {}).get("name"),
                "changes": r.get("changes") or [],
                "record": rec,
            }
        )
    return out
