THESIS_PARSE_PROMPT = """
You are a VC analyst assistant. Parse the following thesis input into structured search filters
for a founder search API. If a founder_keyword field is present (simple mode free-text), extract
any implied filters from it and merge them into the appropriate fields.

Thesis input:
{thesis}

Return a JSON object with these exact fields (use empty lists [] for fields with no match,
never null for list fields):
{{
  "sector": "string — the industry or domain (e.g. developer tools, fintech, logistics)",
  "geography": "string — country name only, e.g. India, United States, Singapore",
  "stage": "string — one of: pre-seed, seed, series-a, any",
  "schools": ["list of institution names mentioned or implied, e.g. IIT Bombay, Stanford"],
  "fields_of_study": ["list of academic fields, e.g. Computer Science, Mechanical Engineering"],
  "past_companies": ["list of specific company names mentioned, e.g. Google, Stripe"],
  "past_titles": ["list of role titles, e.g. Software Engineer, Founder, Product Manager"],
  "expertise_keywords": ["list of domain keywords, e.g. infrastructure, machine learning, fintech"]
}}

Rules:
- Each list is OR within itself, AND across lists (e.g. schools AND expertise_keywords must both match)
- Keep lists short and specific — 1-4 items max per field
- geography must be a country name, not a region

Return only valid JSON. No explanation.
"""

MEMO_PROMPT = """
You are a VC analyst writing a first-pass diligence memo. Use only the data provided.
Never invent facts. If a field is None or missing, write "data unavailable" for that point.
Never say "no GitHub" or "no publications" when the value is None — None means unknown, not absent.

Company data:
{company_data}

Founder insights (one object per founder, all fields from Crustdata):
{founder_data}

Signals:
{signals}

Web research (for market data, GitHub details, papers not in Crustdata):
{web_data}

Important field notes:
- age: use age.age_range. Formula used: birth ≈ bachelor's start year − 18 (NOT graduation + 22).
  age.confidence may be "low" if no education years found — reflect this in the memo.
- nationality: infer from nationality_signals.current_country, education_countries, work_locations.
  Write "likely X-based" not "X national" unless current_country is confirmed.
- github: has_github, total_stars_bucket (<10/10-99/100-999/1000+), followers_100_plus.
  Repo names, languages, commit activity come from web_data only.
- research: has_publications, article_count, citations, h_index from Crustdata.
  Paper titles and details come from web_data only.
- investor_association.trust_level ranking:
  founder_backed_by_notable_investor > employee_at_notable_backed_company > worked_at_investor > none_found
- exits[]: only exits during the person's tenure. exit_status = verified/employee_exit_only/unverified.
- technical.is_technical: CS/engineering degree OR majority of career in technical roles. None = no data.
- possible_part_time_founder: flag this explicitly as a risk in x_factor if true.

Write the following sections. Return as a JSON object with these exact keys:

{{
  "summary": "2-3 sentence description of what the company does, in plain language.",

  "problem": "One bold sentence stating the core problem. Then 3-4 bullet points with specific numbers where available.",

  "market": "3-4 bullet points covering TAM, growth rate, key market dynamics. Use numbers from web_data.",

  "product": ["Feature or offering 1", "Feature or offering 2", "Feature or offering 3", "Feature or offering 4"],

  "x_factor": "1-2 sentences on the single most compelling signal: investor trust level, verified exit, notable pedigree, GitHub stars, research citations, or traction. Flag part-time founder risk here if applicable. If nothing stands out, say so.",

  "competitive_landscape": [
    {{
      "company": "company name",
      "founded": "year",
      "focus": "one phrase",
      "target_market": "one phrase",
      "key_clients": "names or unknown",
      "funding": "amount or undisclosed"
    }}
  ]
}}

Return only valid JSON. No explanation outside the JSON.
"""

DECISION_PROMPT = """
You are a VC analyst making a first-pass investment decision.

Company memo:
{memo}

Signals:
{signals}

Founder insights summary:
{founder_summary}

Thesis being evaluated against:
{thesis}

Based on the above, return a JSON object:
{{
  "decision": "meet" | "pass" | "watch",
  "confidence": "high" | "medium" | "low",
  "reasoning": "2-3 sentences explaining the decision, citing specific signals.",
  "exception_flag": true | false,
  "exception_reason": "string explaining why human review is needed, or null"
}}

Decision rules:
- meet: strong thesis fit, verifiable founder background, positive momentum, investor trust level
  is founder_backed_by_notable_investor or employee_at_notable_backed_company
- watch: partial fit, thin data, or signals improving but not yet decisive
- pass: clear misfit with thesis, declining headcount, no technical background when required,
  or investor trust is none_found with no other strong signals
- exception_flag true: possible_part_time_founder is true, conflicting career data,
  exit_status is unverified on a claimed exit, more than 3 unavailable fields,
  or age confidence is low and age matters for the thesis

Return only valid JSON. No explanation outside the JSON.
"""

OUTREACH_PROMPT = """
You are a VC analyst drafting a cold outreach email to a founder.
The email should feel personal and specific — not a template blast.
Reference the founder's specific background and what caught your attention.
Keep it under 100 words. No subject line needed.

Founder name: {founder_name}
Founder background: {founder_background}
Company name: {company_name}
Company summary: {company_summary}
Why we are reaching out: {decision_reasoning}

Write only the email body. No explanation.
"""
