# Build notes

Running log: what we tried, what worked, what didn't. Feeds the README and demo.

## Approaches considered

## Log
- Crustdata layer: `crustdata/client.py` never raises; returns None and sets `client.last_error` so the agent can say "couldn't verify (reason)" instead of guessing. Retries 429/5xx using `x-ratelimit-reset`, stops immediately on 402/403.
- Backtest feasibility checked live: company enrich gives weekly headcount timeseries (back to 2023) + dated funding milestones + founders' full career history → we can rebuild "what was known on date D". Search filters use *current* values, so backtest candidate lists must avoid filtering on growth/funding (leak). Details: `crustdata/API_NOTES.md`.
- Spec revision (crustdata layer): dropped person-enrich as a default step (person search already returns career history at ~0.4 credits vs 1), kept email but split "find" from "send": real business email comes from person enrich (contact-enrich endpoint is disabled on our plan, person-enrich `contact.business_emails` is not), while every outreach email is routed to team-owned DEMO_RECIPIENTS inboxes (event rule: no contacting real people), computed 3/6/12-month headcount from the weekly timeseries instead of separate calls, reframed "active postings" as "posted in last N days" (no open/closed flag exists). See `crustdata/README.md`.
- Found: fuzzy founder-title search returns people whose *primary* title isn't founder but who hold a side founder role → exposed `founder_roles` so the memo can flag part-time founders.
- Founder profile fields (agreed with Aman): built `founder_insights()`. One batched enrich of every company in each founder's career gives exits (acquired_by / IPO) and investor lists. "Trust" = were they backed by a notable investor/accelerator (curated list + Crustdata's `accelerator` investor category + YC batch in company name). GitHub = filter-only threshold checks (repo details not on our plan → agent web-searches). Research = Crustdata research profiles.
- What didn't work first: (1) `is_investor` flags corporates like TATA Power → now requires a VC/investment industry. (2) Exits for big employers were noise (Adobe "acquired" 4×) → keep only exits during the person's tenure. (3) Fuzzy title search returned "Founding Captain" → strict founder-title post-filter. (4) Precomputed founder_roles ignored backtest dates → derived from date-trimmed roles.
- Added on-disk cache for read calls: reruns/backtests cost 0 credits and the demo survives an API outage.
