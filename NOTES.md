# Build notes

Running log: what we tried, what worked, what didn't. Feeds the README and demo.

## Approaches considered

## Log
- Crustdata layer: `crustdata/client.py` never raises; returns None and sets `client.last_error` so the agent can say "couldn't verify (reason)" instead of guessing. Retries 429/5xx using `x-ratelimit-reset`, stops immediately on 402/403.
- Backtest feasibility checked live: company enrich gives weekly headcount timeseries (back to 2023) + dated funding milestones + founders' full career history → we can rebuild "what was known on date D". Search filters use *current* values, so backtest candidate lists must avoid filtering on growth/funding (leak). Details: `crustdata/API_NOTES.md`.
- Spec revision (crustdata layer): dropped person-enrich as a default step (person search already returns career history at ~0.4 credits vs 1), kept email but split "find" from "send": real business email comes from person enrich (contact-enrich endpoint is disabled on our plan, person-enrich `contact.business_emails` is not), while every outreach email is routed to team-owned DEMO_RECIPIENTS inboxes (event rule: no contacting real people), computed 3/6/12-month headcount from the weekly timeseries instead of separate calls, reframed "active postings" as "posted in last N days" (no open/closed flag exists). See `crustdata/README.md`.
- Found: fuzzy founder-title search returns people whose *primary* title isn't founder but who hold a side founder role → exposed `founder_roles` so the memo can flag part-time founders.
- Added on-disk cache for read calls: reruns/backtests cost 0 credits and the demo survives an API outage.
