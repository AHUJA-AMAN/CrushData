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


# --- Build citations from new founder_insights structure ---

def build_citations(company_data: dict, founder_insights_list: list, web_data: str) -> list[Citation]:
    citations = []

    if company_data.get("headcount"):
        citations.append(Citation(
            claim="Headcount data",
            source="Crustdata company data",
            confidence=Confidence.verified
        ))
    if company_data.get("total_funding"):
        citations.append(Citation(
            claim="Funding information",
            source="Crustdata company data",
            confidence=Confidence.verified
        ))
    for fi in founder_insights_list:
        name = fi.get("name", "founder")
        if fi.get("past_roles"):
            citations.append(Citation(
                claim=f"Career history for {name}",
                source="Crustdata people data",
                confidence=Confidence.verified
            ))
        age = fi.get("age") or {}
        if age.get("age_range"):
            citations.append(Citation(
                claim=f"Age estimate for {name}: {age.get('age_range')} (confidence: {age.get('confidence', 'low')})",
                source="Crustdata education data — birth ≈ bachelor's start − 18",
                confidence=Confidence.inferred
            ))
        investor = fi.get("investor_association") or {}
        if investor.get("trust_level") and investor["trust_level"] != "none_found":
            citations.append(Citation(
                claim=f"Investor association for {name}: {investor['trust_level']}",
                source="Crustdata investor data",
                confidence=Confidence.verified
            ))
        exits = fi.get("exits") or []
        for exit_ in exits:
            citations.append(Citation(
                claim=f"Exit: {exit_.get('company')} ({exit_.get('exit_status', 'unverified')})",
                source="Crustdata exit data",
                confidence=Confidence.verified if exit_.get("exit_status") == "verified" else Confidence.inferred
            ))
        github = fi.get("github") or {}
        if github.get("has_github"):
            citations.append(Citation(
                claim=f"GitHub presence for {name}: {github.get('total_stars_bucket', 'unknown')} stars",
                source="Crustdata GitHub data",
                confidence=Confidence.verified
            ))
        research = fi.get("research") or {}
        if research.get("has_publications"):
            citations.append(Citation(
                claim=f"Research publications for {name}: {research.get('article_count', '?')} articles, h-index {research.get('h_index', '?')}",
                source="Crustdata research data",
                confidence=Confidence.verified
            ))
    if web_data:
        citations.append(Citation(
            claim="Market data, product details, GitHub/paper details",
            source="Web search",
            confidence=Confidence.web
        ))
    return citations


# --- Count unavailable fields for exception threshold ---

EXCEPTION_THRESHOLD = 3

def count_unavailable(company_data: dict, founder_insights_list: list) -> int:
    missing = 0
    if not company_data.get("description"):
        missing += 1
    if not company_data.get("total_funding"):
        missing += 1
    if not company_data.get("headcount"):
        missing += 1
    if not founder_insights_list:
        missing += 1
    elif not founder_insights_list[0].get("past_roles"):
        missing += 1
    return missing


# --- Build a text summary of founder insights for decision prompt ---

def build_founder_summary(founder_insights_list: list) -> str:
    parts = []
    for fi in founder_insights_list:
        name = fi.get("name", "Unknown")
        title = fi.get("current_title", "")
        age = fi.get("age") or {}
        investor = fi.get("investor_association") or {}
        technical = fi.get("technical") or {}
        github = fi.get("github") or {}
        research = fi.get("research") or {}
        exits = fi.get("exits") or []

        summary = f"{name} ({title})"
        if age.get("age_range"):
            summary += f", age ~{age['age_range']} [{age.get('confidence','low')} confidence]"
        summary += f", technical={technical.get('is_technical')}"
        summary += f", investor_trust={investor.get('trust_level', 'none_found')}"
        summary += f", serial_founder={fi.get('serial_founder')}"
        summary += f", previous_exit={'yes' if exits else 'none'}"
        summary += f", github_stars={github.get('total_stars_bucket', 'none')}"
        summary += f", publications={research.get('article_count', 'none')}"
        summary += f", part_time_flag={fi.get('possible_part_time_founder', False)}"
        parts.append(summary)
    return " | ".join(parts) if parts else "No founder data available"


# --- Main pipeline ---

async def run_pipeline(thesis: dict, job_id: str, jobs: dict):
    try:
        try:
            from crustdata.client import (
                search_founders, founder_insights,
                watch_company, find_email, outreach_recipient
            )
            crustdata_ready = True
        except ImportError:
            crustdata_ready = False
            find_email = None
            outreach_recipient = None

        # Step 1: Parse thesis into search_founders parameters
        jobs[job_id]["progress"]["stage"] = "discovery"
        filters = parse_thesis(thesis)

        # Step 2: Search founders
        people = []
        if crustdata_ready:
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
            return

        # Step 3: Get insights for all founders (10-15 credits per founder, cached after)
        jobs[job_id]["progress"]["stage"] = "verification"
        insights = {}
        if crustdata_ready:
            insights = founder_insights(people) or {}

        # Step 4: Group founders by company
        companies: dict = {}
        for person_id, fi in insights.items():
            company = fi.get("company") or {}
            company_key = company.get("crustdata_company_id") or company.get("name") or person_id
            if company_key not in companies:
                companies[company_key] = {"company_data": company, "founders": []}
            companies[company_key]["founders"].append(fi)

        jobs[job_id]["progress"]["companies_found"] = len(companies)

        results = []

        for i, (_, group) in enumerate(companies.items()):
            jobs[job_id]["progress"]["companies_processed"] = i
            company_data = group["company_data"]
            fi_list = group["founders"]
            company_name = company_data.get("name") or "Unknown"
            company_id = company_data.get("crustdata_company_id")
            domain = company_data.get("website") or ""

            # Step 5: Extract signals from company data
            jobs[job_id]["progress"]["stage"] = "signal_analysis"
            signals_raw = {
                "headcount_now": company_data.get("headcount"),
                "headcount_6m_ago": company_data.get("headcount_6m_ago"),
                "headcount_growth_rate": company_data.get("headcount_growth_rate"),
                "recent_job_postings": company_data.get("recent_job_postings"),
                "hiring_departments": company_data.get("hiring_departments") or []
            }

            # Step 6: Web search for market data + github/research details Crustdata doesn't have
            web_query = f"{company_name} {filters.get('sector', '')} startup"
            web_data = web_search(web_query)
            if domain:
                web_data += " " + web_search(f"site:{domain} product")
            for fi in fi_list:
                github = fi.get("github") or {}
                research = fi.get("research") or {}
                name = fi.get("name", "")
                if github.get("has_github"):
                    web_data += " " + web_search(f"{name} github repositories languages")
                if research.get("has_publications"):
                    web_data += " " + web_search(f"{name} research papers publications")

            # Step 7: Generate memo
            jobs[job_id]["progress"]["stage"] = "memo_generation"
            memo = generate_memo(company_data, fi_list, signals_raw, web_data)

            # Step 8: Make decision
            founder_summary = build_founder_summary(fi_list)
            decision_data = make_decision(memo, signals_raw, founder_summary, thesis)

            # Step 9: Exception checks
            missing_count = count_unavailable(company_data, fi_list)
            if missing_count >= EXCEPTION_THRESHOLD and not decision_data.get("exception_flag"):
                decision_data["exception_flag"] = True
                decision_data["exception_reason"] = f"{missing_count} key data fields unavailable"

            part_time = [fi for fi in fi_list if fi.get("possible_part_time_founder")]
            if part_time and not decision_data.get("exception_flag"):
                decision_data["exception_flag"] = True
                decision_data["exception_reason"] = (
                    f"Possible part-time founder: {', '.join(f.get('name','') for f in part_time)}"
                )

            # Step 10: Draft outreach if meet
            outreach = None
            if decision_data.get("decision") == "meet" and fi_list:
                primary = fi_list[0]
                past_companies = [r.get("company", "") for r in (primary.get("past_roles") or [])[:2]]
                outreach = draft_outreach(
                    founder_name=primary.get("name", "Founder"),
                    founder_background=f"{primary.get('current_title')} — previously at {', '.join(past_companies)}",
                    company_name=company_name,
                    company_summary=memo.get("summary", ""),
                    decision_reasoning=decision_data.get("reasoning", "")
                )
                if crustdata_ready and outreach and find_email and outreach_recipient:
                    real_email_data = find_email(primary.get("linkedin_url"), company_id)
                    real_email = real_email_data.get("email") if real_email_data else None
                    recipient = outreach_recipient(primary.get("crustdata_person_id"), real_email)
                    if recipient:
                        send_outreach_email(
                            send_to=recipient["send_to"],
                            intended_for=real_email or primary.get("name", "founder"),
                            subject=f"Quick note on {company_name}",
                            body=outreach
                        )

            # Step 11: Set watcher if watch
            if crustdata_ready and company_id and decision_data.get("decision") == "watch":
                watch_company(
                    company_id=company_id,
                    headcount_threshold=(signals_raw.get("headcount_now") or 0) + 5
                )

            # Step 12: Build citations and assemble result
            citations = build_citations(company_data, fi_list, web_data)

            founders = [
                Founder(
                    name=fi.get("name", "Unknown"),
                    current_title=fi.get("current_title"),
                    education=fi.get("education"),
                    past_companies=[r.get("company", "") for r in (fi.get("past_roles") or [])[:3]],
                    part_time_flag=fi.get("possible_part_time_founder", False)
                )
                for fi in fi_list
            ]

            comp_landscape = [
                CompetitorRow(**c) for c in memo.get("competitive_landscape", [])
                if isinstance(c, dict)
            ]

            result = CompanyResult(
                company_name=company_name,
                domain=domain,
                founded=company_data.get("founded_year"),
                location=company_data.get("location"),
                stage=company_data.get("stage") or thesis.get("stage"),
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
            search_founders, founder_insights, outcome_rounds
        )

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
        # Note: investor lists, GitHub and research are today's values (leakage_warnings from Bhav)
        insights = founder_insights(people, as_of=as_of_date) or {}

        # Group by company
        companies: dict = {}
        for person_id, fi in insights.items():
            company = fi.get("company") or {}
            company_key = company.get("crustdata_company_id") or company.get("name") or person_id
            if company_key not in companies:
                companies[company_key] = {"company_data": company, "founders": []}
            companies[company_key]["founders"].append(fi)

        jobs[job_id]["progress"]["companies_found"] = len(companies)

        results = []
        for i, (_, group) in enumerate(companies.items()):
            jobs[job_id]["progress"]["companies_processed"] = i
            company_data = group["company_data"]
            fi_list = group["founders"]
            company_name = company_data.get("name") or "Unknown"
            company_id = company_data.get("crustdata_company_id")

            # Historical signals only — no headcount growth rate (would leak)
            signals_raw = {
                "headcount_now": company_data.get("headcount"),
                "headcount_6m_ago": None,
                "headcount_growth_rate": None,
                "recent_job_postings": None,
                "hiring_departments": []
            }

            web_data = web_search(f"{company_name} {filters.get('sector', '')} startup")
            memo = generate_memo(company_data, fi_list, signals_raw, web_data)
            founder_summary = build_founder_summary(fi_list)
            decision_data = make_decision(memo, signals_raw, founder_summary, thesis)

            # Check actual outcome: did they raise after as_of_date?
            actual_rounds = outcome_rounds(company_id, after_date=as_of_date) or [] if company_id else []
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
