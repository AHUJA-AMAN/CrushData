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

def call_llm(prompt: str) -> str:
    global _key_index
    for attempt in range(len(API_KEYS)):
        try:
            client = genai.Client(api_key=API_KEYS[_key_index])
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            return response.text
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                _key_index = (_key_index + 1) % len(API_KEYS)
                time.sleep(2)
            else:
                raise
    raise Exception("All Gemini API keys exhausted")


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


# --- Build citations from data sources ---

def build_citations(company_data: dict, founder_data: list, web_data: str) -> list[Citation]:
    citations = []

    if company_data.get("headcount_history"):
        citations.append(Citation(
            claim="Headcount history",
            source="Crustdata company data",
            confidence=Confidence.verified
        ))
    if company_data.get("funding_rounds"):
        citations.append(Citation(
            claim="Funding information",
            source="Crustdata company data",
            confidence=Confidence.verified
        ))
    for f in founder_data:
        if f.get("past_roles"):
            citations.append(Citation(
                claim=f"Career history for {f.get('name', 'founder')}",
                source="Crustdata people data",
                confidence=Confidence.verified
            ))
    if web_data:
        citations.append(Citation(
            claim="Market data and company description",
            source="Web search",
            confidence=Confidence.web
        ))

    return citations


# --- Count unavailable fields for exception threshold ---

EXCEPTION_THRESHOLD = 3

def count_unavailable(company_data: dict, founder_data: list) -> int:
    missing = 0
    if not company_data.get("description"):
        missing += 1
    if not company_data.get("funding_rounds"):
        missing += 1
    if not company_data.get("headcount_history"):
        missing += 1
    if not founder_data:
        missing += 1
    elif not founder_data[0].get("past_roles"):
        missing += 1
    return missing


# --- Main pipeline ---

async def run_pipeline(thesis: dict, job_id: str, jobs: dict):
    try:
        # Try importing Bhav's module — fall back to empty results if not ready
        try:
            from crustdata.client import (
                search_companies, search_people,
                get_company_details, get_person_details,
                get_headcount_growth, get_job_postings,
                watch_company, find_email, outreach_recipient
            )
            crustdata_ready = True
        except ImportError:
            crustdata_ready = False
            find_email = None
            outreach_recipient = None

        # Step 1: Parse thesis
        jobs[job_id]["progress"]["stage"] = "discovery"
        filters = parse_thesis(thesis)

        # Step 2: Discover companies
        companies = []
        if crustdata_ready:
            companies = search_companies(
                sector=filters.get("sector"),
                geography=filters.get("geography"),
                stage=thesis.get("stage"),
                keywords=filters.get("keywords", []),
                limit=10
            ) or []

        jobs[job_id]["progress"]["companies_found"] = len(companies)

        if not companies:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["results"] = []
            return

        results = []

        for i, company in enumerate(companies):
            jobs[job_id]["progress"]["stage"] = "verification"
            jobs[job_id]["progress"]["companies_processed"] = i

            company_id = company.get("crustdata_company_id") or company.get("id")
            company_name = company.get("name", "Unknown")

            # Step 3a: Enrich company
            company_data = {}
            if crustdata_ready and company_id:
                company_data = get_company_details(company_id) or {}

            # Step 3b: Find and enrich founders
            founder_data = []
            if crustdata_ready and company_id:
                people = search_people(
                    company_id=company_id,
                    founder_only=True
                ) or []
                for person in people[:3]:  # cap at 3 founders
                    person_id = person.get("crustdata_person_id") or person.get("id")
                    if person_id:
                        details = get_person_details(person_id) or {}
                        founder_data.append(details)

            # Step 3c: Signals
            jobs[job_id]["progress"]["stage"] = "signal_analysis"
            signals_raw = {}
            if crustdata_ready and company_id:
                headcount = get_headcount_growth(company_id, months=6) or {}
                postings = get_job_postings(company_id) or []
                signals_raw = {
                    "headcount_now": headcount.get("current"),
                    "headcount_6m_ago": headcount.get("six_months_ago"),
                    "headcount_growth_rate": headcount.get("growth_rate"),
                    "recent_job_postings": len(postings),
                    "hiring_departments": list({p.get("department") for p in postings if p.get("department")})
                }

            # Step 3d: Web search fallback for missing data
            domain = company_data.get("website") or company.get("domain", "")
            web_query = f"{company_name} {filters.get('sector', '')} startup funding"
            web_data = web_search(web_query)
            if domain:
                web_data += " " + web_search(f"site:{domain} product features")

            # Step 4: Generate memo
            jobs[job_id]["progress"]["stage"] = "memo_generation"
            memo = generate_memo(company_data, founder_data, signals_raw, web_data)

            # Step 5: Make decision
            founder_summary = "; ".join([
                f"{f.get('name')} — {f.get('current_title')} — prev: {', '.join([r.get('company','') for r in f.get('past_roles', [])[:2]])}"
                for f in founder_data
            ]) or "No founder data available"

            decision_data = make_decision(memo, signals_raw, founder_summary, thesis)

            # Step 6: Check exception threshold
            missing_count = count_unavailable(company_data, founder_data)
            if missing_count >= EXCEPTION_THRESHOLD and not decision_data.get("exception_flag"):
                decision_data["exception_flag"] = True
                decision_data["exception_reason"] = f"{missing_count} key data fields unavailable"

            # Step 7: Draft outreach if meet
            outreach = None
            if decision_data.get("decision") == "meet" and founder_data:
                primary_founder = founder_data[0]
                past_companies = [r.get("company", "") for r in primary_founder.get("past_roles", [])[:2]]
                outreach = draft_outreach(
                    founder_name=primary_founder.get("name", "Founder"),
                    founder_background=f"{primary_founder.get('current_title')} — previously at {', '.join(past_companies)}",
                    company_name=company_name,
                    company_summary=memo.get("summary", ""),
                    decision_reasoning=decision_data.get("reasoning", "")
                )
                # Send to demo inbox — never to the real founder email (hackathon rules)
                if crustdata_ready and outreach:
                    real_email_data = find_email(
                        primary_founder.get("linkedin_url"), company_id
                    )
                    real_email = real_email_data.get("email") if real_email_data else None
                    recipient = outreach_recipient(
                        primary_founder.get("crustdata_person_id"), real_email
                    )
                    if recipient:
                        send_outreach_email(
                            send_to=recipient["send_to"],
                            intended_for=real_email or primary_founder.get("name", "founder"),
                            subject=f"Quick note on {company_name}",
                            body=outreach
                        )

            # Step 8: Set watcher if watch
            if crustdata_ready and company_id and decision_data.get("decision") == "watch":
                watch_company(
                    company_id=company_id,
                    headcount_threshold=signals_raw.get("headcount_now", 0) + 5
                )

            # Step 9: Build citations
            citations = build_citations(company_data, founder_data, web_data)

            # Step 10: Assemble result
            founders = [
                Founder(
                    name=f.get("name", "Unknown"),
                    current_title=f.get("current_title"),
                    education=f.get("education"),
                    past_companies=[r.get("company", "") for r in f.get("past_roles", [])[:3]],
                    part_time_flag=f.get("possible_part_time_founder", False)
                )
                for f in founder_data
            ]

            comp_landscape = [
                CompetitorRow(**c) for c in memo.get("competitive_landscape", [])
                if isinstance(c, dict)
            ]

            result = CompanyResult(
                company_name=company_name,
                domain=domain,
                founded=company_data.get("founded_year"),
                location=company_data.get("location") or company.get("location"),
                stage=thesis.get("stage"),
                total_funding=company_data.get("total_funding"),
                decision=Decision(decision_data.get("decision", "watch")),
                confidence=decision_data.get("confidence", "low"),
                founders=founders,
                memo_sections=MemoSections(
                    summary=memo.get("summary", ""),
                    problem=memo.get("problem", ""),
                    market=memo.get("market", ""),
                    product=memo.get("product", []),
                    competitive_landscape=comp_landscape,
                    x_factor=memo.get("x_factor", "")
                ),
                signals=Signals(**{
                    k: v for k, v in signals_raw.items()
                    if k in Signals.model_fields
                }),
                citations=citations,
                exception_flag=decision_data.get("exception_flag", False),
                exception_reason=decision_data.get("exception_reason"),
                outreach_email=outreach
            )

            results.append(result.model_dump())

        jobs[job_id]["status"] = "done"
        jobs[job_id]["results"] = results

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        raise


async def run_backtest_pipeline(thesis: dict, job_id: str, jobs: dict, as_of_date: str):
    """
    Backtest mode: evaluate thesis as if it were as_of_date.
    Rules:
    - Search only on stable fields: geography, sector, founding year, founder background
    - Never filter on headcount or funding (those are today's values)
    - Use snapshot_as_of() to get historical profile data
    - Score results against outcome_rounds (did they raise after as_of_date?)
    """
    try:
        from crustdata.client import (
            search_companies, get_company_details,
            get_person_details, search_people,
            snapshot_as_of, outcome_rounds
        )

        jobs[job_id]["progress"]["stage"] = "discovery"
        filters = parse_thesis(thesis)

        # Search on stable fields only — no headcount/funding filters
        companies = search_companies(
            sector=filters.get("sector"),
            geography=filters.get("geography"),
            keywords=filters.get("keywords", []),
            # deliberately omit stage/headcount/funding filters for backtest
            limit=10
        ) or []

        jobs[job_id]["progress"]["companies_found"] = len(companies)

        results = []
        for i, company in enumerate(companies):
            jobs[job_id]["progress"]["companies_processed"] = i
            company_id = company.get("crustdata_company_id") or company.get("id")
            company_name = company.get("name", "Unknown")

            # Get historical snapshot as of backtest date
            company_data = get_company_details(company_id) or {}
            historical_profile = snapshot_as_of(company_data, as_of_date)

            founder_data = []
            people = search_people(company_id=company_id, founder_only=True) or []
            for person in people[:3]:
                person_id = person.get("crustdata_person_id") or person.get("id")
                if person_id:
                    details = get_person_details(person_id) or {}
                    founder_data.append(snapshot_as_of(details, as_of_date))

            # Historical signals only
            signals_raw = {
                "headcount_now": historical_profile.get("headcount"),
                "headcount_6m_ago": None,
                "headcount_growth_rate": None,
                "recent_job_postings": None,
                "hiring_departments": []
            }

            web_data = web_search(f"{company_name} {filters.get('sector', '')} startup")
            memo = generate_memo(historical_profile, founder_data, signals_raw, web_data)

            founder_summary = "; ".join([
                f"{f.get('name')} — {f.get('current_title')}"
                for f in founder_data
            ]) or "No founder data"

            decision_data = make_decision(memo, signals_raw, founder_summary, thesis)

            # Check actual outcome: did they raise after as_of_date?
            actual_rounds = outcome_rounds(company_id, after_date=as_of_date) or []
            did_raise = len(actual_rounds) > 0

            result = {
                "company_name": company_name,
                "decision": decision_data.get("decision"),
                "confidence": decision_data.get("confidence"),
                "reasoning": decision_data.get("reasoning"),
                "actual_outcome": {
                    "raised_after_date": did_raise,
                    "rounds": actual_rounds
                },
                # correct = meet and they raised, or pass and they didn't
                "correct_call": (
                    (decision_data.get("decision") == "meet" and did_raise) or
                    (decision_data.get("decision") == "pass" and not did_raise)
                )
            }
            results.append(result)

        # Compute precision and recall
        meets = [r for r in results if r["decision"] == "meet"]
        true_positives = [r for r in meets if r["actual_outcome"]["raised_after_date"]]
        all_that_raised = [r for r in results if r["actual_outcome"]["raised_after_date"]]

        jobs[job_id]["status"] = "done"
        jobs[job_id]["results"] = results
        jobs[job_id]["backtest_summary"] = {
            "as_of_date": as_of_date,
            "total_companies": len(results),
            "meet_calls": len(meets),
            "precision": round(len(true_positives) / len(meets), 2) if meets else 0,
            "recall": round(len(true_positives) / len(all_that_raised), 2) if all_that_raised else 0
        }

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        raise
