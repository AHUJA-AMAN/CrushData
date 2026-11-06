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
import re
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
    company_headcount: int | None
    location: str | None
    description: str | None


class School(TypedDict):
    school: str | None
    degree: str | None
    field_of_study: str | None
    start_year: int | None
    end_year: int | None
    country: str | None


class ResearchProfile(TypedDict):
    name: str | None
    affiliation: str | None
    profile_url: str | None
    interests: list[str]
    article_count: int | None
    citations: int | None
    h_index: int | None
    top_articles: list[dict[str, Any]]  # [{title, year, citations, url}] most cited first, max 5


class Person(TypedDict):
    crustdata_person_id: int | None
    name: str | None
    headline: str | None
    current_title: str | None  # PRIMARY current title
    location: str | None
    country: str | None
    linkedin_url: str | None
    current_roles: list[Role]
    founder_roles: list[Role]  # current roles whose title says founder/CEO/CTO; may not be their primary job
    past_roles: list[Role]
    education: list[School]
    skills: list[str]
    recently_changed_jobs: bool | None
    research_profiles: list[ResearchProfile]  # academic author profiles (publications); [] = none found
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
        "company_headcount": r.get("company_headcount_latest"),
        "location": r.get("location") if isinstance(r.get("location"), str) else (r.get("location") or {}).get("raw"),
        "description": desc[:400] if isinstance(desc, str) and desc else None,
    }


def _loc_country(loc: Any) -> str | None:
    return loc.get("country") if isinstance(loc, dict) else None


def _norm_research(rp: dict[str, Any]) -> ResearchProfile:
    arts = sorted(rp.get("articles") or [], key=lambda a: a.get("total_citations") or 0, reverse=True)[:5]
    return {
        "name": rp.get("name"),
        "affiliation": rp.get("affiliated_organisation") or rp.get("designation"),
        "profile_url": rp.get("profile_url"),
        "interests": rp.get("research_interests") or [],
        "article_count": rp.get("article_count"),
        "citations": (rp.get("citations_count") or {}).get("all"),
        "h_index": (rp.get("h_index") or {}).get("all"),
        "top_articles": [
            {"title": a.get("title"), "year": a.get("publication_year"), "citations": a.get("total_citations"), "url": a.get("url")} for a in arts
        ],
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
        "country": _loc_country(loc),
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
                "country": _loc_country(s.get("location")),
            }
            for s in schools
        ],
        "skills": (p.get("skills") or {}).get("professional_network_skills") or [],
        "recently_changed_jobs": exp.get("recently_changed_jobs"),
        "research_profiles": [_norm_research(rp) for rp in p.get("research_profiles") or [] if isinstance(rp, dict)],
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


_ISO3_TO_COUNTRY = {
    "IND": "India", "USA": "United States", "GBR": "United Kingdom", "SGP": "Singapore", "ARE": "United Arab Emirates",
    "CAN": "Canada", "DEU": "Germany", "FRA": "France", "AUS": "Australia", "NLD": "Netherlands", "ISR": "Israel",
    "IDN": "Indonesia", "JPN": "Japan", "CHN": "China", "BRA": "Brazil", "IRL": "Ireland", "CHE": "Switzerland",
}  # fmt: skip


def _any_of(field: str, op: str, values: list[str]) -> dict[str, Any]:
    conds = [{"field": field, "type": op, "value": v} for v in values]
    return conds[0] if len(conds) == 1 else {"op": "or", "conditions": conds}


def _resolve_company_ids(names: list[str]) -> list[int]:
    """Company names -> Crustdata ids via free identify; keeps every top-confidence match."""
    ids: list[int] = []
    for name in names:
        matches = identify_company(name=name) or []
        best = max((m.get("confidence") or 0 for m in matches), default=0)  # type: ignore[attr-defined]
        ids += [m["crustdata_company_id"] for m in matches if m["crustdata_company_id"] and best >= 0.8 and (m.get("confidence") or 0) >= best - 0.05]  # type: ignore[attr-defined]
    return list(dict.fromkeys(ids))


def search_founders(
    *,
    company_ids: list[int] | None = None,
    titles: list[str] | None = None,
    country: str | None = None,
    schools: list[str] | None = None,
    fields_of_study: list[str] | None = None,
    past_companies: list[str] | None = None,
    past_company_ids: list[int] | None = None,
    past_titles: list[str] | None = None,
    expertise_keywords: list[str] | None = None,
    past_keywords: list[str] | None = None,
    extra_filters: list[dict[str, Any]] | None = None,
    limit: int = 25,
) -> list[Person] | None:
    """Find founders, with career history, education, skills and research profiles included.

    Every list argument is OR within itself and AND across arguments. ~0.8 credits per result.
    titles: current-title words, default FOUNDER_TITLES (matches ANY current role, so side
      founders come back too; see founder_insights()["possible_part_time_founder"]).
    country: "India" or ISO-3 "IND". schools: e.g. ["IIT Kanpur", "Indian Institute of Technology Kanpur"].
    fields_of_study: e.g. ["Computer Science"]. past_companies: names, resolved to Crustdata ids
      (falls back to fuzzy name match). past_titles: e.g. ["SRE", "platform engineer"].
    expertise_keywords: domain words matched against skills, headline and past role descriptions.
    past_keywords: legacy, matches past role titles or descriptions.
    """
    exp = "experience.employment_details"
    conds: list[dict[str, Any]] = [_any_of(f"{exp}.current.title", "(.)", titles or FOUNDER_TITLES)]
    if company_ids:
        conds.append({"field": f"{exp}.current.company_id", "type": "in", "value": company_ids})
    if country:
        conds.append({"field": "basic_profile.location.country", "type": "=", "value": _ISO3_TO_COUNTRY.get(country.upper(), country)})
    if schools:
        conds.append(_any_of("education.schools.school", "(.)", schools))
    if fields_of_study:
        conds.append(_any_of("education.schools.field_of_study", "(.)", fields_of_study))
    if past_companies or past_company_ids:
        ids = list(dict.fromkeys((past_company_ids or []) + _resolve_company_ids(past_companies or [])))
        alts: list[dict[str, Any]] = [{"field": f"{exp}.past.company_id", "type": "in", "value": ids}] if ids else []
        alts += [{"field": f"{exp}.past.company_name", "type": "(.)", "value": n} for n in past_companies or []]
        conds.append(alts[0] if len(alts) == 1 else {"op": "or", "conditions": alts})
    if past_titles:
        conds.append(_any_of(f"{exp}.past.title", "(.)", past_titles))
    if expertise_keywords:
        kw = expertise_keywords
        conds.append({"op": "or", "conditions": [_any_of("skills.professional_network_skills", "(.)", kw), _any_of("basic_profile.headline", "[.]", kw),
                                                 _any_of(f"{exp}.past.description", "[.]", kw), _any_of(f"{exp}.current.description", "[.]", kw)]})  # fmt: skip
    if past_keywords:
        conds.append({"op": "or", "conditions": [_any_of(f"{exp}.past.title", "(.)", past_keywords), _any_of(f"{exp}.past.description", "[.]", past_keywords)]})
    conds.extend(extra_filters or [])

    body = {
        "filters": conds[0] if len(conds) == 1 else {"op": "and", "conditions": conds},
        "limit": max(1, min(limit, 100)),
        "fields": ["crustdata_person_id", "basic_profile", "experience", "education", "social_handles", "skills", "research_profiles"],
    }
    data, at = _cached_post("/person/search", body)
    if data is None:
        return None
    out: dict[Any, Person] = {}
    for p in data.get("profiles") or []:
        person = _norm_person(p, "/person/search", at)
        # Fuzzy title match lets "Founding Engineer" through; with default titles keep real founders only.
        if titles is None and not person["founder_roles"]:
            continue
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
        body = {"professional_network_profile_urls": batch, "fields": ["basic_profile", "experience", "education", "skills", "social_handles", "research_profiles"]}
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
    global last_error
    if not linkedin_url:
        last_error = "find_email needs a LinkedIn URL (this person has none on file)"
        return None
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


# ------------------------------------------------------------ founder insights

# Canonical investor -> word-boundary aliases (lowercase). Accelerators + top India/global VCs.
# ponytail: hand-kept list; any investor Crustdata tags "accelerator" is also caught via categories.
NOTABLE_INVESTORS: dict[str, list[str]] = {
    "Y Combinator": ["y combinator", "ycombinator"], "Sequoia / Peak XV": ["sequoia", "peak xv", "surge"],
    "Accel": ["accel", "accel partners"], "Lightspeed": ["lightspeed"], "Andreessen Horowitz": ["andreessen", "a16z"],
    "Tiger Global": ["tiger global"], "SoftBank": ["softbank"], "General Catalyst": ["general catalyst"],
    "Elevation Capital": ["elevation capital", "saif partners"], "Matrix Partners / Z47": ["matrix partners", "z47"],
    "Blume Ventures": ["blume"], "Kalaari Capital": ["kalaari"], "Nexus Venture Partners": ["nexus venture"],
    "Chiratae Ventures": ["chiratae", "idg ventures india"], "Stellaris": ["stellaris"], "3one4 Capital": ["3one4"],
    "Prosus / Naspers": ["prosus", "naspers"], "Info Edge Ventures": ["info edge"], "Together Fund": ["together fund"],
    "Antler": ["antler"], "Techstars": ["techstars"], "500 Global": ["500 startups", "500 global"],
    "Entrepreneur First": ["entrepreneur first"], "Pioneer Fund": ["pioneer fund"], "SV Angel": ["sv angel"],
    "Founders Fund": ["founders fund"], "Benchmark": ["benchmark capital", "benchmark"], "Index Ventures": ["index ventures"],
    "Greylock": ["greylock"], "Kleiner Perkins": ["kleiner"], "Bessemer": ["bessemer"], "Insight Partners": ["insight partners"],
    "Khosla Ventures": ["khosla"], "GV (Google Ventures)": ["google ventures", "gv"], "Elevar Equity": ["elevar"],
    "Better Capital": ["better capital"], "Venture Highway": ["venture highway"], "Alpha Wave": ["alpha wave"],
}  # fmt: skip
_INVESTOR_RES = [(canon, re.compile(r"\b(" + "|".join(re.escape(a) for a in aliases) + r")\b")) for canon, aliases in NOTABLE_INVESTORS.items()]
_YC_BATCH = re.compile(r"\(YC [A-Z]\d{2}\)|\bYC [SWFX]\d{2}\b")
_INTERN = re.compile(r"\b(intern|internship|trainee|student|apprentice)\b", re.I)
_TECH_DEGREE = re.compile(r"comput|software|electric|electron|mechanic|engineer|b\.?\s?tech|m\.?\s?tech|\bb\.?e\b|math|physics|statistic|data|information tech|artificial|machine learning|\bai\b", re.I)
_TECH_ROLE = re.compile(r"engineer|developer|\bsde\b|programmer|architect|scientist|\bcto\b|devops|\bsre\b|technical|researcher|ml\b", re.I)
_TECH_FUNCTIONS = {"Engineering", "Information Technology", "Research", "Quality Assurance"}
_PHD = re.compile(r"\b(ph\.?\s?d|doctor|dphil)\b", re.I)
_MASTER = re.compile(r"\b(master|m\.?\s?tech|m\.?\s?sc?|m\.?e|mba|m\.?a|pgdm|post\s?graduate)\b", re.I)
_BACHELOR = re.compile(r"\b(bachelor|b\.?\s?tech|b\.?\s?e|b\.?\s?sc?|b\.?\s?a|bba|b\.?\s?com|undergrad\w*|dual degree|integrated)\b", re.I)


def _notable(names: list[str]) -> list[str]:
    hits = [canon for canon, rx in _INVESTOR_RES if any(rx.search(n.lower()) for n in names)]
    return list(dict.fromkeys(hits))


def _career_companies(ids: list[int]) -> tuple[dict[int, dict[str, Any]], str | None]:
    """Exit + investor facts for every company in someone's career. 2 credits per company (cached)."""
    out: dict[int, dict[str, Any]] = {}
    errors: list[str] = []
    for batch in _chunks(list(dict.fromkeys(ids)), 25):
        data, at = _cached_post("/company/enrich", {"crustdata_company_ids": batch, "fields": ["basic_info", "funding", "revenue", "taxonomy"]})
        if data is None:
            errors.append(last_error or "unknown error")
            continue
        for entry in data if isinstance(data, list) else []:
            for m in (entry.get("matches") or [])[:1]:
                c = m.get("company_data") or {}
                bi, fu, rev = c.get("basic_info") or {}, c.get("funding") or {}, c.get("revenue") or {}
                detailed = fu.get("investors_detailed") or []
                names = [i.get("name") for i in detailed if i.get("name")] + _split_names(fu.get("investors"))
                names += [n for ms in fu.get("milestones") or [] for n in _split_names(ms.get("investors"))]
                names = list(dict.fromkeys(names))
                pm = rev.get("public_markets") or {}
                cid = c.get("crustdata_company_id") or bi.get("crustdata_company_id")
                tax = c.get("taxonomy") or {}
                industries = " ".join(tax.get("professional_network_industries") or [tax.get("professional_network_industry") or ""]).lower()
                out[cid] = {
                    "name": bi.get("name"),
                    # Crustdata flags any corporate that invests (e.g. TATA Power); require a VC-type industry too.
                    "is_investor": bool(fu.get("is_investor")) and ("venture capital" in industries or "investment" in industries),
                    "investors": names,
                    "notable_investors": _notable(names) + (["Y Combinator"] if _YC_BATCH.search(bi.get("name") or "") and "Y Combinator" not in _notable(names) else []),
                    "accelerator_investors": [i.get("name") for i in detailed if "accelerator" in (i.get("categories") or [])],
                    "acquired_by": [{"acquirer": a.get("name"), "date": _day(a.get("date")), "amount_usd": a.get("amount_usd")} for a in fu.get("acquired_by") or []],
                    "acquisition_status": rev.get("acquisition_status"),
                    "ipo_date": _day(pm.get("ipo_date")),
                    "status": bi.get("status"),
                    "source": _source("/company/enrich", at, cid, bi.get("professional_network_url")),
                }
    return out, "; ".join(errors) or None


def _github_signals(person_ids: list[int]) -> dict[int, dict[str, Any]]:
    """GitHub facts via filter-only search (Crustdata can't return repo details on our plan).

    One search per threshold across all people; a check that errors leaves its value None (unknown).
    """
    checks = {
        "has_github": {"field": "dev_platform_profiles.public_repo_count", "type": "=>", "value": 1},
        "stars_10": {"field": "dev_platform_profiles.total_stars", "type": "=>", "value": 10},
        "stars_100": {"field": "dev_platform_profiles.total_stars", "type": "=>", "value": 100},
        "stars_1000": {"field": "dev_platform_profiles.total_stars", "type": "=>", "value": 1000},
        "followers_100": {"field": "dev_platform_profiles.followers", "type": "=>", "value": 100},
    }
    hits: dict[str, set[int] | None] = {}
    for name, cond in checks.items():
        found: set[int] | None = set()
        for batch in _chunks(person_ids, 100):
            body = {"filters": {"op": "and", "conditions": [{"field": "crustdata_person_id", "type": "in", "value": batch}, cond]},
                    "limit": len(batch), "fields": ["crustdata_person_id"]}  # fmt: skip
            data, _ = _cached_post("/person/search", body)
            if data is None:
                found = None
                break
            found |= {p.get("crustdata_person_id") for p in data.get("profiles") or []}  # type: ignore[operator]
        hits[name] = found

    def has(name: str, pid: int) -> bool | None:
        s = hits[name]
        return None if s is None else pid in s

    out = {}
    for pid in person_ids:
        stars = None
        if hits["stars_10"] is not None and hits["stars_100"] is not None and hits["stars_1000"] is not None:
            stars = "1000+" if has("stars_1000", pid) else "100-999" if has("stars_100", pid) else "10-99" if has("stars_10", pid) else "<10"
        out[pid] = {"has_github": has("has_github", pid), "total_stars_bucket": stars if has("has_github", pid) else None,
                    "followers_100_plus": has("followers_100", pid)}  # fmt: skip
    return out


def _estimate_birth_year(education: list[School], roles: list[Role]) -> dict[str, Any]:
    """Birth-year range from education years (degree-level offsets) or, failing that, first job."""
    # Typical age at the start / end of each degree. Bachelor's is the most reliable anchor, so it wins.
    levels = [("bachelor's", _BACHELOR, 18, 22), ("master's", _MASTER, 22, 24), ("PhD", _PHD, 23, 28)]
    best: tuple[int, int, str] | None = None  # (birth_year, +/- years, method)
    for label, rx, start_age, end_age in levels:
        for s in education:
            if not (s["degree"] and rx.search(s["degree"])):
                continue
            if s["start_year"]:
                best = (s["start_year"] - start_age, 1, f"{label} start year {s['start_year']} - {start_age}")
            elif s["end_year"]:
                best = (s["end_year"] - end_age, 1, f"{label} end year {s['end_year']} - {end_age}")
            if best:
                break
        if best:
            break
    if best is None:
        starts = [s["start_year"] for s in education if s["start_year"]]
        if starts:
            best = (min(starts) - 18, 3, f"earliest education start {min(starts)} - 18 (degree level unknown)")
    if best is None:
        firsts = sorted(r["start_date"] for r in roles if r["start_date"] and not _INTERN.search(r["title"] or ""))
        if firsts:
            y = int(firsts[0][:4])
            best = (y - 22, 3, f"first full-time role {y} - 22 (no education years)")
    if best is None:
        return {"birth_year_range": None, "method": "no education or career dates on file", "confidence": "unknown"}
    by, spread, method = best
    return {"birth_year_range": [by - spread, by + spread], "method": method, "confidence": "medium" if spread == 1 else "low"}


def founder_insights(people: list[Person], *, as_of: str | date | None = None, include_github: bool = True) -> dict[Any, dict[str, Any]] | None:
    """Everything the agent needs to judge a founder, derived from Crustdata, keyed by crustdata_person_id.

    Per founder (all facts carry the data they came from):
      age: estimated birth_year_range / age_range + method + confidence (from education years)
      nationality_signals: current_country, current_location, education_countries, work_locations
      years_of_experience: from first non-intern role to as_of (Crustdata's own field is disabled on our plan)
      founded_companies, past_founder_roles, founder_company_count, serial_founder, previous_startup_experience
      possible_part_time_founder: has a founder role but primary title is something else
      open_ended_past_roles: past roles with no end date (side/advisory roles, NOT the primary job)
      technical: is_technical (True/False/None) + degree_technical, technical_career_share, first_role_technical
      company: primary founder company id/name, team_size (headcount), founder_count, co_founded, cofounders
      exits: acquisitions/IPOs of companies in their career + exit_status verified/employee_exit_only/unverified
      investor_association: trust_level + backed_companies (notable/accelerator investors) + worked_at_investor
      github: has_github, total_stars_bucket, followers_100_plus (filter-only; None = unknown)
      research: has_publications, article_count, citations, h_index, profiles
      not_on_crustdata: what the agent must web-search
    Costs: 2 credits per career company (cached, shared across founders) + small GitHub checks.
    as_of (backtest): ignores roles started and exits dated after it; see leakage_warnings.
    """
    global last_error
    ref = _as_date(as_of) or date.today()
    day = ref.isoformat()
    people = [p for p in people if p]
    if not people:
        return {}
    errors: list[str] = []

    def trim(roles: list[Role]) -> list[Role]:
        return [r for r in roles if not as_of or (r["start_date"] and r["start_date"] <= day)]

    # 1) one batched lookup for every company anyone worked at
    career_ids = [r["crustdata_company_id"] for p in people for r in p["current_roles"] + p["past_roles"] if r["crustdata_company_id"]]
    companies, err = _career_companies(career_ids)
    if err:
        errors.append(f"career companies: {err}")
    # 2) founders of each person's primary founder company (co-founded vs solo), from full enrich (cached)
    def primary_founder_role(p: Person) -> Role | None:
        return next((r for r in trim(p["current_roles"]) if _is_founder_title(r["title"])), None)

    primary_ids = list(dict.fromkeys(r["crustdata_company_id"] for p in people if (r := primary_founder_role(p)) and r["crustdata_company_id"]))
    profiles = enrich_companies(primary_ids) if primary_ids else {}
    if primary_ids and profiles is None:
        errors.append(f"founder companies: {last_error}")
    # 3) GitHub checks, batched
    pids = [p["crustdata_person_id"] for p in people if p["crustdata_person_id"]]
    github = _github_signals(pids) if include_github and pids else {}

    out: dict[Any, dict[str, Any]] = {}
    for p in people:
        current, past = trim(p["current_roles"]), trim(p["past_roles"])
        roles = current + past
        founder_current = [r for r in current if _is_founder_title(r["title"])]
        founder_past = [r for r in past if _is_founder_title(r["title"])]
        founded: dict[Any, dict[str, Any]] = {}
        for r, status in [(r, "current") for r in founder_current] + [(r, "past") for r in founder_past]:
            key = r["crustdata_company_id"] or (r["company_name"] or "").lower()
            founded.setdefault(key, {"company_name": r["company_name"], "crustdata_company_id": r["crustdata_company_id"], "title": r["title"],
                                     "start_date": r["start_date"], "end_date": r["end_date"], "status": status})  # fmt: skip

        full_time = [r for r in roles if r["start_date"] and not _INTERN.search(r["title"] or "")]
        start = min((r["start_date"] for r in full_time), default=None)
        yoe = round((ref - _as_date(start)).days / 365.25, 1) if start and _as_date(start) else None  # type: ignore[operator]

        tech_roles = [r for r in full_time if r["function_category"] in _TECH_FUNCTIONS or _TECH_ROLE.search(r["title"] or "")]
        degree_tech = any(_TECH_DEGREE.search(f"{s['degree'] or ''} {s['field_of_study'] or ''}") for s in p["education"]) if any(s["degree"] or s["field_of_study"] for s in p["education"]) else None
        share = round(len(tech_roles) / len(full_time), 2) if full_time else None
        first = min(full_time, key=lambda r: r["start_date"] or "9") if full_time else None
        first_tech = (first in tech_roles) if first else None
        is_tech = None if degree_tech is None and share is None else bool(degree_tech) or (share or 0) >= 0.5

        age = _estimate_birth_year(p["education"], roles)
        if age["birth_year_range"]:
            lo, hi = age["birth_year_range"]
            age["age_range"] = [ref.year - hi, ref.year - lo]

        primary = (founder_current[:1] or [None])[0]
        prof = (profiles or {}).get(primary["crustdata_company_id"]) if primary and primary["crustdata_company_id"] else None
        cofounders = [f for f in (prof or {}).get("founders", []) if f["crustdata_person_id"] != p["crustdata_person_id"]]

        exits, backed, worked_at = [], [], []
        for r in roles:
            c = companies.get(r["crustdata_company_id"])  # type: ignore[arg-type]
            if not c:
                continue
            was_founder = _is_founder_title(r["title"])

            def in_tenure(d: str | None, r: Role = r) -> bool:
                # An exit only says something about this person if it happened while they were there
                # (or within a year of leaving, for deals that close late). Undated exits are kept.
                if not d:
                    return True
                end = r["end_date"] or "9999"
                end_plus = f"{int(end[:4]) + 1}{end[4:]}" if end != "9999" else end
                return (r["start_date"] or "0000") <= d <= end_plus and (not as_of or d <= day)

            for a in c["acquired_by"]:
                if in_tenure(a["date"]):
                    exits.append({"company_name": c["name"], "crustdata_company_id": r["crustdata_company_id"], "type": "acquired", **a,
                                  "person_title": r["title"], "person_was_founder": was_founder, "source": c["source"]})  # fmt: skip
            if not c["acquired_by"] and c["acquisition_status"] == "acquired":
                exits.append({"company_name": c["name"], "crustdata_company_id": r["crustdata_company_id"], "type": "acquired", "acquirer": None,
                              "date": None, "amount_usd": None, "person_title": r["title"], "person_was_founder": was_founder, "source": c["source"]})  # fmt: skip
            if c["ipo_date"] and in_tenure(c["ipo_date"]):
                exits.append({"company_name": c["name"], "crustdata_company_id": r["crustdata_company_id"], "type": "ipo", "acquirer": None,
                              "date": c["ipo_date"], "amount_usd": None, "person_title": r["title"], "person_was_founder": was_founder, "source": c["source"]})  # fmt: skip
            if c["notable_investors"] or c["accelerator_investors"]:
                backed.append({"company_name": c["name"], "crustdata_company_id": r["crustdata_company_id"], "person_title": r["title"],
                               "person_was_founder": was_founder, "notable_investors": c["notable_investors"],
                               "accelerator_investors": c["accelerator_investors"], "source": c["source"]})  # fmt: skip
            if c["is_investor"] or _notable([c["name"] or ""]):
                worked_at.append({"firm": c["name"], "title": r["title"], "start_date": r["start_date"], "end_date": r["end_date"], "source": c["source"]})
        # Several roles at one company -> one entry; keep the founder flag if any role was founder-level.
        by_co: dict[Any, dict[str, Any]] = {}
        for b in backed:
            prev = by_co.setdefault(b["crustdata_company_id"], b)
            prev["person_was_founder"] = prev["person_was_founder"] or b["person_was_founder"]
        backed = list(by_co.values())
        exits = list({(e["crustdata_company_id"], e["type"], e["date"], e.get("acquirer")): e for e in sorted(exits, key=lambda e: e["person_was_founder"])}.values())
        worked_at = list({w["firm"]: w for w in worked_at}.values())
        trust = ("founder_backed_by_notable_investor" if any(b["person_was_founder"] for b in backed)
                 else "employee_at_notable_backed_company" if backed else "worked_at_investor" if worked_at else "none_found")  # fmt: skip
        founder_exits = [e for e in exits if e["person_was_founder"]]
        rps = p["research_profiles"]

        out[p["crustdata_person_id"] or p["name"]] = {
            "crustdata_person_id": p["crustdata_person_id"],
            "name": p["name"],
            # the person's own record, so callers don't need the Person list alongside
            "current_title": p.get("current_title"),
            "headline": p.get("headline"),
            "linkedin_url": p.get("linkedin_url"),
            "location": p.get("location"),
            "current_roles": current,
            "past_roles": past,
            "education": p.get("education") or [],
            "skills": p.get("skills") or [],
            "as_of": day,
            "age": age,
            "nationality_signals": {
                "current_country": p["country"],
                "current_location": p["location"],
                "education_countries": list(dict.fromkeys(s["country"] for s in p["education"] if s["country"])),
                "work_locations": list(dict.fromkeys(r["location"] for r in roles if r["location"]))[:5],
            },
            "years_of_experience": yoe,
            "career_start": start,
            "founded_companies": list(founded.values()),
            "founder_company_count": len(founded),
            "serial_founder": len(founded) >= 2,
            "previous_startup_experience": len(founded) >= 2 or bool(founder_past),
            "past_founder_roles": founder_past,
            "possible_part_time_founder": bool(founder_current) and not _is_founder_title(p["current_title"]),
            "open_ended_past_roles": [r for r in past if not r["end_date"]],
            "technical": {"is_technical": is_tech, "degree_technical": degree_tech, "technical_career_share": share,
                          "first_role_technical": first_tech, "first_role": first["title"] if first else None},  # fmt: skip
            "company": {
                "crustdata_company_id": primary["crustdata_company_id"] if primary else None,
                "name": primary["company_name"] if primary else None,
                "team_size": (prof or {}).get("headcount") or (primary["company_headcount"] if primary else None),
                "founder_count": (len(cofounders) + 1) if prof else None,
                "co_founded": (bool(cofounders) if prof else None),
                "cofounders": [{"crustdata_person_id": f["crustdata_person_id"], "name": f["name"], "title": f["current_title"], "linkedin_url": f["linkedin_url"]} for f in cofounders],
            },
            "exits": exits,
            "exit_status": "verified" if founder_exits else "employee_exit_only" if exits else "unverified",
            "investor_association": {"trust_level": trust, "backed_companies": backed, "worked_at_investor": worked_at},
            "github": github.get(p["crustdata_person_id"], {"has_github": None, "total_stars_bucket": None, "followers_100_plus": None}),  # type: ignore[arg-type]
            "research": {
                "has_publications": bool(rps) and any((r["article_count"] or 0) > 0 for r in rps),
                "article_count": sum(r["article_count"] or 0 for r in rps) if rps else 0,
                "citations": sum(r["citations"] or 0 for r in rps) if rps else 0,
                "h_index": max((r["h_index"] or 0 for r in rps), default=0),
                "profiles": rps,
            },
            "not_on_crustdata": [
                "GitHub repo names, languages, commit activity (only star/follower thresholds are available)",
                "open-source contributions to other people's repos",
                "publications outside Crustdata's research-profile index",
            ],
            "leakage_warnings": ["investor_association uses today's investor lists", "github and research are current values"] if as_of else [],
            "source": p["source"],
        }
    last_error = "; ".join(errors) or None
    return out


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
        # ngrok's free tier can show a warning page instead of forwarding; this header skips it.
        notifications.append({"type": "webhook", "url": webhook_url, "headers": {"ngrok-skip-browser-warning": "true"}})
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
