import os
import json
import sys
import time
import smtplib
from email.mime.text import MIMEText
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai
from google.genai import types
from dotenv import load_dotenv
from agent.prompts import THESIS_PARSE_PROMPT, MEMO_PROMPT, DECISION_PROMPT, OUTREACH_PROMPT
from agent.models import (
    CompanyResult, Decision, Founder, MemoSections,
    Signals, Citation, Confidence, CompetitorRow
)

load_dotenv()

# --- LLM setup with key rotation ---

API_KEYS = [k for k in [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
] if k]

_key_index = 0
# ponytail: a model that times out or 404s is skipped until the server restarts
_dead_models: set = set()
LLM_TIMEOUT_MS = 45000

def call_llm(prompt: str) -> str:
    global _key_index
    if not API_KEYS:
        raise RuntimeError("No Gemini API key set: add GEMINI_API_KEY to .env")
    models_to_try = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
    for model_name in [m for m in models_to_try if m not in _dead_models]:
        for attempt in range(3):  # 3 retries per model
            try:
                client = genai.Client(api_key=API_KEYS[_key_index], http_options={"timeout": LLM_TIMEOUT_MS})
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return response.text
            except Exception as e:
                err = str(e)
                if "504" in err or "DEADLINE" in err or "timed out" in err.lower() or "timeout" in type(e).__name__.lower():
                    print(f"{model_name} timed out, skipping it from now on", flush=True)
                    _dead_models.add(model_name)
                    break
                if "429" in err or "quota" in err.lower():
                    # rotate key and retry
                    _key_index = (_key_index + 1) % len(API_KEYS)
                    time.sleep(2)
                elif "503" in err or "UNAVAILABLE" in err or "overload" in err.lower():
                    # overloaded: move to the next model now instead of waiting on this one
                    print(f"{model_name} unavailable (503), trying next model", flush=True)
                    break
                elif "404" in err or "NOT_FOUND" in err:
                    # model doesn't exist — skip to next model immediately
                    print(f"{model_name} not found, trying next model", flush=True)
                    _dead_models.add(model_name)
                    break
                else:
                    raise
    raise Exception("All Gemini models unavailable")


def parse_json_response(text: str) -> dict:
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# --- Thesis parsing ---

def parse_thesis(thesis: dict) -> dict:
    prompt = THESIS_PARSE_PROMPT.format(thesis=json.dumps(thesis))
    result = call_llm(prompt)
    return parse_json_response(result)


# --- Web search fallback ---

def web_search(query: str) -> str:
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        results = client.search(query, max_results=3)
        return " ".join([r.get("content", "") for r in results.get("results", [])])
    except Exception:
        return ""


# --- Memo and decision generation ---

def generate_memo(company_data: dict, founder_data: list, signals: dict, web_data: str) -> dict:
    prompt = MEMO_PROMPT.format(
        company_data=json.dumps(company_data),
        founder_data=json.dumps(founder_data),
        signals=json.dumps(signals),
        web_data=web_data
    )
    result = call_llm(prompt)
    return parse_json_response(result)


def make_decision(memo: dict, signals: dict, founder_summary: str, thesis: dict) -> dict:
    prompt = DECISION_PROMPT.format(
        memo=json.dumps(memo),
        signals=json.dumps(signals),
        founder_summary=founder_summary,
        thesis=json.dumps(thesis)
    )
    result = call_llm(prompt)
    return parse_json_response(result)


def draft_outreach(founder_name: str, founder_background: str, company_name: str,
                   company_summary: str, decision_reasoning: str) -> str:
    prompt = OUTREACH_PROMPT.format(
        founder_name=founder_name,
        founder_background=founder_background,
        company_name=company_name,
        company_summary=company_summary,
        decision_reasoning=decision_reasoning
    )
    return call_llm(prompt).strip()


def send_outreach_email(send_to: str, intended_for: str, subject: str, body: str) -> bool:
    # Always sends to a demo inbox, never to the real founder email
    # Adds "Intended for: <real email>" at the top so the demo shows who it was written for
    full_body = f"[DEMO] Intended for: {intended_for}\n\n{body}"
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")
    if not smtp_email or not smtp_password:
        print(f"SMTP not configured — email not sent. Would have sent to {send_to}")
        return False
    try:
        msg = MIMEText(full_body)
        msg["Subject"] = subject
        msg["From"] = smtp_email
        msg["To"] = send_to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, send_to, msg.as_string())
        return True
    except Exception as e:
        print(f"Email send failed: {e}")
        return False


# --- Shaping Crustdata data for the memo, the decision and the frontend ---

def _fmt_usd(value) -> str | None:
    # Crustdata stores 0 when funding is unknown; never show that as "$0 raised"
    if not value:
        return None
    return f"${value / 1e6:.1f}M" if value >= 1e6 else f"${value:,.0f}"


def build_company_data(company: dict, profile: dict | None) -> dict:
    """Flat company dict for memo/citations/result.

    company = founder_insights()[...]["company"] (id, name, team size, co-founders)
    profile = enrich_companies() profile, or snapshot_as_of() output in a backtest; None if
    the founder's company isn't on Crustdata (hybrid memo: founder data only).
    """
    p = profile or {}
    return {
        "crustdata_company_id": company.get("crustdata_company_id") or p.get("crustdata_company_id"),
        "name": p.get("name") or company.get("name"),
        "description": p.get("description"),
        "website": p.get("website") or p.get("domain"),
        "domain": p.get("domain"),
        "linkedin_url": p.get("linkedin_url"),
        "founded_year": p.get("year_founded"),
        "location": ", ".join(x for x in [p.get("city"), p.get("country")] if x) or None,
        "industries": p.get("industries") or [],
        "stage": p.get("funding_stage"),
        "total_funding": p.get("total_funding_usd") or None,  # 0 = unknown in Crustdata
        "last_fundraise_date": p.get("last_fundraise_date"),
        "funding_rounds": p.get("funding_rounds") or [],
        "investors": p.get("investors") or [],
        "headcount": p.get("headcount") or company.get("team_size"),
        "founder_count": company.get("founder_count"),
        "co_founded": company.get("co_founded"),
        "cofounders": company.get("cofounders") or [],
        "data_as_of": p.get("as_of"),
    }


def build_signals(company_data: dict, hc: dict | None, hiring: dict | None) -> dict:
    """Signals for the memo/decision. Keys outside the Signals model are memo-only extras."""
    hc = hc or {}
    hiring = hiring or {}
    growth = hc.get("growth_6m_pct")
    return {
        "headcount_now": hc.get("headcount_now") or company_data.get("headcount"),
        "headcount_6m_ago": hc.get("headcount_6m_ago"),
        "headcount_growth_rate": f"{growth:+.1f}% over 6 months" if growth is not None else None,
        "recent_job_postings": hiring.get("recent_postings_count"),
        "hiring_departments": list((hiring.get("departments") or {}).keys()),
        # extras for the memo
        "headcount_3m_ago": hc.get("headcount_3m_ago"),
        "headcount_12m_ago": hc.get("headcount_12m_ago"),
        "growth_12m_pct": hc.get("growth_12m_pct"),
        "headcount_data_as_of": hc.get("latest_point_date"),
        "recent_job_titles": (hiring.get("recent_titles") or [])[:8],
        "latest_job_posted_at": hiring.get("latest_posted_at"),
    }


def education_text(education: list | None) -> str | None:
    parts = []
    for s in education or []:
        what = ", ".join(x for x in [s.get("degree"), s.get("field_of_study")] if x)
        parts.append(f"{what} @ {s.get('school')}" if what else (s.get("school") or ""))
    return "; ".join(p for p in parts if p) or None


def past_company_names(fi: dict, n: int = 3) -> list[str]:
    names = [r.get("company_name") for r in fi.get("past_roles") or [] if r.get("company_name")]
    return list(dict.fromkeys(names))[:n]


def normalize_decision(value) -> Decision:
    """LLM may answer 'Meet', 'PASS', 'pass_' ...; anything unrecognised becomes watch."""
    v = str(value or "").strip().lower().rstrip("_")
    return {"meet": Decision.meet, "pass": Decision.pass_, "watch": Decision.watch}.get(v, Decision.watch)


# --- Citations ---

def build_citations(company_data: dict, founder_insights_list: list, web_data: str) -> list[Citation]:
    citations = []
    cid = company_data.get("crustdata_company_id")
    co_src = f"Crustdata company record {cid}" + (f" ({company_data['linkedin_url']})" if company_data.get("linkedin_url") else "")

    if company_data.get("headcount") is not None:
        citations.append(Citation(claim=f"Headcount: {company_data['headcount']}", source=co_src, confidence=Confidence.verified))
    if company_data.get("total_funding"):
        citations.append(Citation(claim=f"Total funding: {_fmt_usd(company_data['total_funding'])}", source=co_src, confidence=Confidence.verified))
    for r in company_data.get("funding_rounds") or []:
        citations.append(Citation(
            claim=f"{r.get('round_type') or 'Round'} on {r.get('date') or 'unknown date'}: {_fmt_usd(r.get('amount_usd')) or 'amount undisclosed'}"
                  + (f", led by {', '.join(r['lead_investors'])}" if r.get("lead_investors") else ""),
            source=co_src, confidence=Confidence.verified))

    for fi in founder_insights_list:
        name = fi.get("name") or "founder"
        person_src = "Crustdata person record" + (f" ({fi['linkedin_url']})" if fi.get("linkedin_url") else "")
        if fi.get("past_roles") or fi.get("current_roles"):
            citations.append(Citation(claim=f"Career history for {name}", source=person_src, confidence=Confidence.verified))
        age = fi.get("age") or {}
        if age.get("age_range"):
            citations.append(Citation(
                claim=f"Age estimate for {name}: {age['age_range'][0]}-{age['age_range'][1]} ({age.get('confidence', 'low')} confidence)",
                source=f"{person_src}; method: {age.get('method')}", confidence=Confidence.inferred))
        investor = fi.get("investor_association") or {}
        if investor.get("trust_level") and investor["trust_level"] != "none_found":
            backers = sorted({i for b in investor.get("backed_companies") or [] for i in b.get("notable_investors") or []})
            citations.append(Citation(
                claim=f"Investor association for {name}: {investor['trust_level']}" + (f" ({', '.join(backers)})" if backers else ""),
                source="Crustdata investor data for companies in their career", confidence=Confidence.verified))
        for exit_ in fi.get("exits") or []:
            how = "as founder" if exit_.get("person_was_founder") else "as employee"
            what = f"acquired by {exit_['acquirer']}" if exit_.get("acquirer") else exit_.get("type", "exit")
            citations.append(Citation(
                claim=f"{name} was at {exit_.get('company_name')} {how} when it was {what} ({exit_.get('date') or 'date unknown'})",
                source=f"Crustdata company record {exit_.get('crustdata_company_id')}", confidence=Confidence.verified))
        github = fi.get("github") or {}
        if github.get("has_github"):
            citations.append(Citation(claim=f"GitHub presence for {name}: {github.get('total_stars_bucket') or 'unknown'} stars",
                                      source="Crustdata GitHub data", confidence=Confidence.verified))
        research = fi.get("research") or {}
        if research.get("has_publications"):
            citations.append(Citation(
                claim=f"Research publications for {name}: {research.get('article_count')} articles, h-index {research.get('h_index')}",
                source="Crustdata research profiles", confidence=Confidence.verified))
    if web_data.strip():
        citations.append(Citation(claim="Market data, product details, GitHub/paper details", source="Web search", confidence=Confidence.web))
    return citations


# --- Count unavailable fields for exception threshold ---

EXCEPTION_THRESHOLD = 3

def count_unavailable(company_data: dict, founder_insights_list: list) -> int:
    missing = 0
    if not company_data.get("description"):
        missing += 1
    if not company_data.get("total_funding"):
        missing += 1
    if company_data.get("headcount") is None:
        missing += 1
    if not founder_insights_list:
        missing += 1
    elif not (founder_insights_list[0].get("past_roles") or founder_insights_list[0].get("current_roles")):
        missing += 1
    return missing


# --- Build a text summary of founder insights for decision prompt ---

_EXIT_TEXT = {"verified": "yes, as founder", "employee_exit_only": "only as an employee", "unverified": "none found"}

def build_founder_summary(founder_insights_list: list) -> str:
    parts = []
    for fi in founder_insights_list:
        age = fi.get("age") or {}
        investor = fi.get("investor_association") or {}
        technical = fi.get("technical") or {}
        github = fi.get("github") or {}
        research = fi.get("research") or {}

        summary = f"{fi.get('name', 'Unknown')} ({fi.get('current_title') or 'title unknown'})"
        if age.get("age_range"):
            summary += f", age ~{age['age_range'][0]}-{age['age_range'][1]} [{age.get('confidence', 'low')} confidence]"
        summary += f", years_experience={fi.get('years_of_experience')}"
        summary += f", technical={technical.get('is_technical')}"
        summary += f", investor_trust={investor.get('trust_level', 'none_found')}"
        summary += f", serial_founder={fi.get('serial_founder')}"
        summary += f", previous_exit={_EXIT_TEXT.get(fi.get('exit_status'), 'unknown')}"
        summary += f", github_stars={github.get('total_stars_bucket') or 'unknown'}"
        summary += f", publications={research.get('article_count', 'unknown')}"
        summary += f", part_time_flag={fi.get('possible_part_time_founder', False)}"
        parts.append(summary)
    return " | ".join(parts) if parts else "No founder data available"


def _group_by_company(insights: dict) -> dict:
    companies: dict = {}
    for person_id, fi in insights.items():
        company = fi.get("company") or {}
        key = company.get("crustdata_company_id") or company.get("name") or person_id
        companies.setdefault(key, {"company": company, "founders": []})["founders"].append(fi)
    return companies


def _error_result(company_name: str, error: Exception) -> dict:
    """One company failing must not kill the whole job: show it as an exception instead."""
    return CompanyResult(
        company_name=company_name,
        decision=Decision.watch,
        confidence="low",
        memo_sections=MemoSections(summary=f"Analysis could not be completed: {error}", problem="", market="",
                                   product=[], competitive_landscape=[], x_factor=""),
        signals=Signals(),
        exception_flag=True,
        exception_reason=f"Processing error: {error}",
    ).model_dump()


# --- Main pipeline ---
# Two phases so the user picks which companies get a memo:
#   run_pipeline:  thesis -> founders -> companies -> job["candidates"], status "awaiting_selection"
#   prepare_memos: memo + decision for each picked company, appended to job["results"] as soon as it's done
# Plain `def` on purpose: every call in here blocks (Crustdata, Gemini, SMTP, sleeps). FastAPI runs
# sync background tasks in a worker thread, so /run returns at once and /status keeps answering.
# As `async def` it ran on the event loop and froze the whole server until the job finished.

class Cancelled(Exception):
    pass


def _check_cancel(job: dict):
    # ponytail: checked between steps; a Gemini/Crustdata call already in flight finishes first
    if job.get("cancel"):
        raise Cancelled()


def _candidate(key: str, group: dict, company_data: dict) -> dict:
    fi_list = group["founders"]
    return {
        "id": key,
        "company_name": company_data.get("name") or (fi_list[0].get("name", "Unknown") + " (company not on Crustdata)"),
        "domain": company_data.get("website"),
        "location": company_data.get("location"),
        "founded": company_data.get("founded_year"),
        "stage": company_data.get("stage"),
        "total_funding": _fmt_usd(company_data.get("total_funding")),
        "headcount": company_data.get("headcount"),
        "description": (company_data.get("description") or "")[:240] or None,
        "founders": [{"name": fi.get("name") or "Unknown", "current_title": fi.get("current_title")} for fi in fi_list],
    }


def run_pipeline(thesis: dict, job_id: str, jobs: dict):
    job = jobs[job_id]
    try:
        from crustdata.client import search_founders, founder_insights, enrich_companies

        # Step 1: Parse thesis into search_founders parameters
        job["progress"]["stage"] = "discovery"
        filters = parse_thesis(thesis)
        _check_cancel(job)

        # Step 2: Search founders
        people = search_founders(
            country=filters.get("geography"),
            schools=filters.get("schools", []),
            fields_of_study=filters.get("fields_of_study", []),
            past_companies=filters.get("past_companies", []),
            past_titles=filters.get("past_titles", []),
            expertise_keywords=filters.get("expertise_keywords", [])
        ) or []
        _check_cancel(job)
        if not people:
            job.update(status="done", results=[], candidates=[])
            job["progress"]["stage"] = "done"
            return

        # Step 3: Founder insights (10-15 credits per founder first time, cached after)
        job["progress"]["stage"] = "verification"
        insights = founder_insights(people) or {}
        _check_cancel(job)

        # Step 4: Group founders by company, then load full company profiles (cached: founder_insights already fetched them)
        groups = {str(k): g for k, g in _group_by_company(insights).items()}
        company_ids = [g["company"].get("crustdata_company_id") for g in groups.values()]
        company_ids = [c for c in company_ids if isinstance(c, int)]
        profiles = (enrich_companies(company_ids) or {}) if company_ids else {}
        _check_cancel(job)

        # Step 5: Show the companies and wait for the user to pick which ones get a memo
        candidates = []
        for key, g in groups.items():
            cid = g["company"].get("crustdata_company_id")
            candidates.append(_candidate(key, g, build_company_data(g["company"], profiles.get(cid) if cid else None)))
        job["_ctx"] = {"thesis": thesis, "filters": filters, "groups": groups, "profiles": profiles, "done": set()}
        job["candidates"] = candidates
        job["results"] = []
        job["progress"].update(stage="selection", companies_found=len(candidates), companies_processed=0)
        job["status"] = "awaiting_selection"

    except Cancelled:
        job["status"] = "cancelled"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        raise


def prepare_memos(job_id: str, jobs: dict, company_ids: list):
    """Memo + decision for each picked company; each result is visible in /results as soon as it's done."""
    job = jobs[job_id]
    ctx = job["_ctx"]
    todo = [c for c in company_ids if c in ctx["groups"] and c not in ctx["done"]]
    job["progress"].update(stage="memo_generation", companies_found=len(todo), companies_processed=0)
    job["_busy"] = True
    try:
        for i, key in enumerate(todo):
            _check_cancel(job)
            group = ctx["groups"][key]
            cid = group["company"].get("crustdata_company_id")
            try:
                result = _analyze_company(job, group, ctx["profiles"].get(cid) if cid else None, ctx["filters"], ctx["thesis"])
            except Cancelled:
                raise
            except Exception as e:
                name = _candidate(key, group, build_company_data(group["company"], None))["company_name"]
                print(f"[{job_id}] {name} failed: {e}", flush=True)
                result = _error_result(name, e)
            result["candidate_id"] = key
            job["results"].append(result)
            ctx["done"].add(key)
            job["progress"]["companies_processed"] = i + 1
        job["progress"]["stage"] = "done"
        job["status"] = "done"
    except Cancelled:
        job["status"] = "cancelled"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        raise
    finally:
        job["_busy"] = False


def _analyze_company(job: dict, group: dict, profile: dict | None, filters: dict, thesis: dict) -> dict:
    from crustdata.client import headcount_signals, get_hiring, watch_company, find_email, outreach_recipient

    fi_list = group["founders"]
    company_id = group["company"].get("crustdata_company_id")
    company_data = build_company_data(group["company"], profile)
    company_name = company_data.get("name") or (fi_list[0].get("name", "Unknown") + " (company not on Crustdata)")

    # Signals from the headcount history and job postings
    hc = headcount_signals(profile["headcount_timeseries"]) if profile else None
    hiring = get_hiring(company_id) if company_id else None
    signals_raw = build_signals(company_data, hc, hiring)
    _check_cancel(job)

    # Business emails, listed in the UI only. Outreach still goes to a team demo inbox, never these.
    emails = {}
    for fi in fi_list:
        if fi.get("linkedin_url"):
            emails[id(fi)] = find_email(fi["linkedin_url"], company_id)
    _check_cancel(job)

    # Web search for market data + github/research details Crustdata doesn't have
    domain = company_data.get("domain") or ""
    web_data = web_search(f"{company_name} {filters.get('sector', '')} startup")
    if domain:
        web_data += " " + web_search(f"site:{domain} product")
    for fi in fi_list:
        name = fi.get("name", "")
        if (fi.get("github") or {}).get("has_github"):
            web_data += " " + web_search(f"{name} github repositories languages")
        if (fi.get("research") or {}).get("has_publications"):
            web_data += " " + web_search(f"{name} research papers publications")
    _check_cancel(job)

    # Memo (drop the long per-role lists; the memo prompt reads the derived fields)
    memo_founders = [{k: v for k, v in fi.items() if k not in ("current_roles", "source")} for fi in fi_list]
    memo = generate_memo(company_data, memo_founders, signals_raw, web_data)
    _check_cancel(job)

    # Decision
    decision_data = make_decision(memo, signals_raw, build_founder_summary(fi_list), thesis)
    decision = normalize_decision(decision_data.get("decision"))
    _check_cancel(job)

    # Exception checks
    missing_count = count_unavailable(company_data, fi_list)
    if missing_count >= EXCEPTION_THRESHOLD and not decision_data.get("exception_flag"):
        decision_data["exception_flag"] = True
        decision_data["exception_reason"] = f"{missing_count} key data fields unavailable"
    part_time = [fi for fi in fi_list if fi.get("possible_part_time_founder")]
    if part_time and not decision_data.get("exception_flag"):
        decision_data["exception_flag"] = True
        decision_data["exception_reason"] = f"Possible part-time founder: {', '.join(f.get('name', '') for f in part_time)}"

    # Draft outreach if meet (always sent to a team demo inbox, never the founder)
    outreach = None
    if decision == Decision.meet and fi_list:
        primary = fi_list[0]
        outreach = draft_outreach(
            founder_name=primary.get("name", "Founder"),
            founder_background=f"{primary.get('current_title') or 'Founder'} — previously at {', '.join(past_company_names(primary, 2)) or 'n/a'}",
            company_name=company_name,
            company_summary=memo.get("summary", ""),
            decision_reasoning=decision_data.get("reasoning", "")
        )
        _check_cancel(job)
        if outreach and primary.get("linkedin_url"):
            real_email = (emails.get(id(primary)) or {}).get("email")
            recipient = outreach_recipient(primary.get("crustdata_person_id") or primary.get("name"), real_email)
            if recipient:
                send_outreach_email(
                    send_to=recipient["send_to"],
                    intended_for=real_email or f"{primary.get('name', 'founder')} (no email on file)",
                    subject=f"Quick note on {company_name}",
                    body=outreach
                )

    # Watcher if watch: fire on new round / new founder or CXO / ~20% headcount growth
    if company_id and decision == Decision.watch:
        now = signals_raw.get("headcount_now")
        watch_company(company_id, headcount_threshold=(now + max(5, round(now * 0.2))) if now else None)

    # Citations and result
    def email_fields(fi):
        if not fi.get("linkedin_url"):
            return {"business_email": None, "email_status": "no LinkedIn on file"}
        found = emails.get(id(fi))
        if not found:
            return {"business_email": None, "email_status": "lookup failed"}
        return {"business_email": found.get("email"), "email_status": found.get("status") if found.get("email") else "not on file"}

    founders = [
        Founder(
            name=fi.get("name") or "Unknown",
            current_title=fi.get("current_title"),
            education=education_text(fi.get("education")),
            past_companies=past_company_names(fi),
            part_time_flag=bool(fi.get("possible_part_time_founder")),
            **email_fields(fi),
        )
        for fi in fi_list
    ]
    comp_landscape = [CompetitorRow(**c) for c in memo.get("competitive_landscape", []) if isinstance(c, dict) and c.get("company")]
    return CompanyResult(
        company_name=company_name,
        domain=company_data.get("website"),
        founded=company_data.get("founded_year"),
        location=company_data.get("location"),
        stage=company_data.get("stage") or thesis.get("stage"),
        total_funding=_fmt_usd(company_data.get("total_funding")),
        decision=decision,
        confidence=str(decision_data.get("confidence", "low")),
        founders=founders,
        memo_sections=MemoSections(
            summary=memo.get("summary", ""),
            problem=memo.get("problem", ""),
            market=memo.get("market", ""),
            product=memo.get("product", []) if isinstance(memo.get("product"), list) else [str(memo.get("product"))],
            competitive_landscape=comp_landscape,
            x_factor=memo.get("x_factor", "")
        ),
        signals=Signals(**{k: v for k, v in signals_raw.items() if k in Signals.model_fields}),
        citations=build_citations(company_data, fi_list, web_data),
        exception_flag=bool(decision_data.get("exception_flag", False)),
        exception_reason=decision_data.get("exception_reason"),
        outreach_email=outreach
    ).model_dump()


def run_backtest_pipeline(thesis: dict, job_id: str, jobs: dict, as_of_date: str):
    """
    Backtest mode: evaluate thesis as if it were as_of_date.
    Rules:
    - Search only on stable fields: geography, sector, founding year, founder background
    - Never filter on headcount or funding (those are today's values)
    - Company data comes from snapshot_as_of(): only rounds/headcount dated on or before as_of_date
    - Score against the snapshot's outcome_rounds (did they raise after as_of_date?)
    - No web search: today's web pages would leak what happened after as_of_date
    """
    try:
        from crustdata.client import search_founders, founder_insights, enrich_companies, headcount_signals, snapshot_as_of

        jobs[job_id]["progress"]["stage"] = "discovery"
        filters = parse_thesis(thesis)

        # Search on stable fields only — no headcount/funding (today's values leak future data)
        people = search_founders(
            country=filters.get("geography"),
            schools=filters.get("schools", []),
            fields_of_study=filters.get("fields_of_study", []),
            past_companies=filters.get("past_companies", []),
            past_titles=filters.get("past_titles", []),
            expertise_keywords=filters.get("expertise_keywords", [])
        ) or []

        if not people:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["results"] = []
            jobs[job_id]["backtest_summary"] = {"as_of_date": as_of_date, "total_companies": 0}
            return

        # founder_insights with as_of drops later roles and exits
        # (investor lists, GitHub and research are today's values: see leakage_warnings)
        jobs[job_id]["progress"]["stage"] = "verification"
        insights = founder_insights(people, as_of=as_of_date) or {}
        companies = _group_by_company(insights)
        company_ids = [k for k in companies if isinstance(k, int)]
        profiles = (enrich_companies(company_ids) or {}) if company_ids else {}
        jobs[job_id]["progress"]["companies_found"] = len(companies)

        results = []
        for i, group in enumerate(companies.values()):
            if jobs[job_id].get("cancel"):
                jobs[job_id]["status"] = "cancelled"
                return
            jobs[job_id]["progress"]["companies_processed"] = i
            jobs[job_id]["progress"]["stage"] = "memo_generation"
            fi_list = group["founders"]
            company_id = group["company"].get("crustdata_company_id")
            profile = profiles.get(company_id) if company_id else None
            snap = snapshot_as_of(profile, as_of_date) if profile else None
            company_data = build_company_data(group["company"], snap)
            company_name = company_data.get("name") or "Unknown"
            try:
                hc = headcount_signals(profile["headcount_timeseries"], as_of_date) if profile else None
                signals_raw = build_signals(company_data, hc, None)  # job postings: no reliable history

                memo = generate_memo(company_data, fi_list, signals_raw, "")
                decision_data = make_decision(memo, signals_raw, build_founder_summary(fi_list), thesis)
                decision = normalize_decision(decision_data.get("decision")).value

                # Actual outcome: rounds dated after as_of_date. Unknown if the company isn't on Crustdata.
                actual_rounds = snap["outcome_rounds"] if snap else None
                did_raise = bool(actual_rounds) if actual_rounds is not None else None
                results.append({
                    "company_name": company_name,
                    "decision": decision,
                    "confidence": str(decision_data.get("confidence", "low")),
                    "reasoning": decision_data.get("reasoning"),
                    "actual_outcome": {"raised_after_date": did_raise, "rounds": actual_rounds or []},
                    # correct = meet and they raised, or pass and they didn't; None when the outcome is unknown
                    "correct_call": None if did_raise is None else (
                        (decision == "meet" and did_raise) or (decision == "pass" and not did_raise)
                    ),
                })
            except Exception as e:
                print(f"[{job_id}] backtest {company_name} failed: {e}")
                results.append({"company_name": company_name, "decision": None, "error": str(e),
                                "actual_outcome": {"raised_after_date": None, "rounds": []}, "correct_call": None})

        # Precision and recall over companies whose outcome is known
        known = [r for r in results if r["actual_outcome"]["raised_after_date"] is not None]
        meets = [r for r in known if r["decision"] == "meet"]
        true_positives = [r for r in meets if r["actual_outcome"]["raised_after_date"]]
        all_that_raised = [r for r in known if r["actual_outcome"]["raised_after_date"]]

        jobs[job_id]["progress"]["companies_processed"] = len(companies)
        jobs[job_id]["progress"]["stage"] = "done"
        jobs[job_id]["status"] = "done"
        jobs[job_id]["results"] = results
        jobs[job_id]["backtest_summary"] = {
            "as_of_date": as_of_date,
            "total_companies": len(results),
            "companies_with_known_outcome": len(known),
            "meet_calls": len(meets),
            "precision": round(len(true_positives) / len(meets), 2) if meets else 0,
            "recall": round(len(true_positives) / len(all_that_raised), 2) if all_that_raised else 0
        }

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        raise
