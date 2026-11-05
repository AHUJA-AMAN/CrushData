# CrushData — ContextCon 04 (IIT Kanpur) hackathon

Theme: **Services, Replaced** — build agents that do a whole paid service end to end (not a chat UI on a model).
Team of 3. Overnight: building 11:00 PM Nov 5 → **code freeze 7:00 AM Nov 6 (IST)**.

## Hard rules
- Repo public; commit history starts after 11:00 PM Nov 5. Commit as you go.
- Agents talk only to our team, Crustdata, Techkriti — never real outside people (no real emails/messages sent).
- Submit by 7:00 AM: repo link, 2-min demo video (Loom / unlisted YouTube, one link, plays in private window), public diagram link, every member's details.

## Judging (100 pts) — optimise for these
| Criterion | Pts | What wins it |
|---|---|---|
| End-to-end execution | 25 | Real request in → finished work out, no human in the loop except where it changes the result |
| Facts & verification | 20 | Every fact correct + cited with source; dedupe entities; say "can't verify" instead of guessing |
| Robustness & edge cases | 20 | Messy input, missing fields, tool timeouts/garbage; resume after crash, never send/pay twice |
| Customer value & idea | 20 | A job businesses pay for today; non-obvious approach |
| Demo & understanding | 15 | Approaches weighed, what worked/didn't, hardest case, what's next |

Ties → end-to-end, then facts. Service shape: take request → plan → gather facts (record sources) → decide (with reasons) → act within limits → show its work.

## Crustdata API
- Base `https://api.crustdata.com`, headers: `authorization: Bearer $CRUSTDATA_API_KEY`, `x-api-version: 2025-11-01`, `content-type: application/json`.
- Docs: docs.crustdata.com (llms.txt for agents). Pricing: docs.crustdata.com/general/pricing.
- Endpoints (req/min): Person Search 30, Person Enrich 15, Company Search 30, Company Identify 30 (**free**), Company Enrich 15, Job Search 30, Web Search & Fetch 10, Watcher 10. 200 req/min per key overall.
- Errors: 401 bad key · 402 out of credits (`GET /account/credits` is free) · 403 endpoint not allowed · 429 wait `x-ratelimit-reset` then retry · no results → loosen one filter, use Autocomplete API for exact values.
- MCP: `https://install.crustdata.com/mcp` (configured in `.mcp.json`, signs in via browser).

Smoke test (free):
```bash
curl -s -X POST https://api.crustdata.com/company/identify -H "authorization: Bearer $CRUSTDATA_API_KEY" -H "content-type: application/json" -H "x-api-version: 2025-11-01" -d '{"domains":["crustdata.com"]}'
```

## README must cover (judges start here at 7:15 AM)
The service & who pays for it · what it does now / where it needs a person · what's next & why not now · how to run · how it's built (diagram: agents, models, tools, where Crustdata is called, where state lives) · approaches tried, what worked and what didn't.

Log approaches and findings in `NOTES.md` as you go — that's the raw material for the README and demo.
