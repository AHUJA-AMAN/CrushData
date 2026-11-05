THESIS_PARSE_PROMPT = """
You are a VC analyst assistant. Parse the following thesis input into structured search filters.
If a founder_keyword field is present (simple mode free-text), extract any implied filters from it
and merge them into founder_filters.

Thesis input:
{thesis}

Return a JSON object with these fields (omit fields that are not mentioned or cannot be inferred):
{{
  "sector": "string — the industry or domain (e.g. developer tools, fintech, logistics)",
  "geography": "string — country or region (e.g. India, Southeast Asia, US)",
  "stage": "string — one of: pre-seed, seed, series-a, any",
  "keywords": ["list of keyword strings for people/company search"],
  "founder_filters": {{
    "domain_expertise": ["list of domains"],
    "previous_company": "string or null",
    "institution": "string or null",
    "technical_founder": true/false/null,
    "previous_startup": true/false/null,
    "accelerator_alumni": ["list or null"]
  }}
}}

Return only valid JSON. No explanation.
"""

MEMO_PROMPT = """
You are a VC analyst writing a first-pass diligence memo. Use only the data provided.
Never invent facts. If a field is missing, say "data unavailable" for that point.

Company data:
{company_data}

Founder data:
{founder_data}

Signals:
{signals}

Web research:
{web_data}

Write the following sections. Return as a JSON object with these exact keys:

{{
  "summary": "2-3 sentence description of what the company does, in plain language.",

  "problem": "One bold sentence stating the core problem. Then 3-4 bullet points with specific numbers where available.",

  "market": "3-4 bullet points covering TAM, growth rate, key market dynamics. Use numbers where found in web data.",

  "product": ["Feature or offering 1", "Feature or offering 2", "Feature or offering 3", "Feature or offering 4"],

  "x_factor": "1-2 sentences on the single most compelling signal — a notable backer, deal, pedigree, or traction point. If nothing stands out, say so.",

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

Founder background:
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
- meet: strong thesis fit, verifiable founder background, positive momentum signals
- watch: partial fit or thin data — worth revisiting when more signals emerge
- pass: clear misfit with thesis, red flags, or insufficient data to evaluate
- exception_flag true: conflicting data, ambiguous founder identity, more than 3 unavailable fields, possible part-time founder

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
