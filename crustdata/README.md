# crustdata/: data layer for the VC sourcing agent

```python
from crustdata import (search_companies, search_founders, identify_company, enrich_companies,
                       enrich_people, founder_insights, headcount_signals, snapshot_as_of, get_hiring,
                       find_email, outreach_recipient, watch_company, parse_watch_event, EARLY_STAGES)
from crustdata import client   # client.last_error explains any None / partial result
```

Setup: `pip install -r requirements.txt`, put `CRUSTDATA_API_KEY=...` in `.env`, then run `python -m crustdata.test_client` (add `--full` for a live smoke test of every function).

**Rules every function follows:** it never raises. On failure it returns `None` and `client.last_error` says why (`402 insufficient_credits`, `network error`, ...). Use that to write "could not verify X because Y" in the memo. Every record has a `source` (`endpoint`, `record_id`, `url` = LinkedIn page a human can open, `retrieved_at`) for citations.

**Cache (committed to the repo, so the demo replays without Wi-Fi):** read calls are stored in `.cache/crustdata/`. Wire main.py's `--use-cache` flag to `client.set_cache_mode("only")`, which serves everything from cache with **zero API calls**. A miss returns `None` with `last_error = "cache miss ..."`. Modes: `"on"` (default: cache, call API on miss), `"off"` (always fresh), `"only"` (replay). Env alternative: `CRUSTDATA_CACHE=on|off|only`. Run the demo thesis once online so it gets recorded, then commit `.cache/`. Real email lookups go to `.cache/crustdata/private/`, which is git-ignored because the repo is public.

**.env keys:** `CRUSTDATA_API_KEY`, `DEMO_RECIPIENTS` (team inboxes for outreach), `WATCH_WEBHOOK_URL` (`https://<ngrok-url>/webhook`; `watch_company` posts there by default).

## Functions (mapped to the spec)

| Spec step | Function | Returns | Cost |
|---|---|---|---|
| 1 Company search | `search_companies(query, country="IND", founded_after=2022, max_headcount=50, funding_stages=EARLY_STAGES, include_unfunded=True, extra_filters=None, limit=25)` | `list[Company]`: id, name, description, domain, website, linkedin_url, industries, categories, country, city, year_founded, headcount, funding_stage, total_funding_usd | ~0.5 / result |
| 1 People search | `search_founders(country="India" or "IND", schools=[...], fields_of_study=[...], past_companies=["Flipkart"], past_titles=["SRE"], expertise_keywords=["kubernetes"], company_ids=None, titles=FOUNDER_TITLES, limit=25)`. Lists are OR inside, AND across | `list[Person]`, **already includes career history, education, skills, research profiles** | ~0.8 / result |
| 2 Founder fields | `founder_insights(people, as_of=None)` → `{person_id: insights}`. See "Founder profile fields" below | age, nationality signals, experience, founder history, technical, team, exits, investor trust, GitHub, research | 2 / career company (shared, cached) |
| 1/2 Dedupe / identity | `identify_company(name=..., domain=...)` | `list[Company]` with `confidence` | free |
| 2 Company enrich | `enrich_companies([ids])` | `{id: CompanyProfile or None}`: everything in Company + `funding_rounds[{date, round_type, amount_usd, lead_investors, investors}]`, `investors`, `founders[Person]`, `leadership[{name, title, linkedin_url}]`, `headcount_timeseries`, `open_jobs_count` | 2 / company |
| 2 People enrich | `enrich_people([linkedin_urls])` | `{url: Person or None}` | 1 / person |
| 2 Email | `find_email(linkedin_url, company_id=None)` | `{email, status, candidates[], source}`, the **real** business email (prefers deliverable @ the startup). Display/cite only | ~2 / person |
| Outreach | `outreach_recipient(person_id, real_email)` | `{send_to, intended_for, demo_mode}`: `send_to` is **always** a team inbox from `DEMO_RECIPIENTS` | free |
| 3 Headcount | `headcount_signals(profile["headcount_timeseries"], as_of=None)` | now / 3m / 6m / 12m ago + growth % | free (no call) |
| 3 Jobs | `get_hiring(company_id, window_days=90, as_of=None)` | recent_postings_count, departments `{Engineering: 5}`, recent_titles, latest_posted_at, postings | ~0.03 / posting |
| 3 Watch (your `set_watcher`) | `watch_company(id, headcount_threshold=60, webhook_url=None → WATCH_WEBHOOK_URL, dry_run=False)` | watch id | free to create, 5 / notification |
| 3 Watch event | `parse_watch_event(webhook_body)` | `[{company_id, company_name, changes[{field, from, to}]}]` | free |
| Backtest | `snapshot_as_of(profile, "2025-06-01")` | profile as of that date + `outcome_rounds` (rounds after the date) + `leakage_warnings` | free |

`Person` = crustdata_person_id, name, headline, current_title (primary), location, country, linkedin_url, current_roles, **founder_roles**, past_roles (title, company_name, start/end date, seniority, function, company_headcount, location, description), education (school, degree, field_of_study, start/end year, country), skills, research_profiles, recently_changed_jobs, source.

## Founder profile fields (`founder_insights`)

| Spec field | Key in insights | How |
|---|---|---|
| University, field of study, previous company, previous title, domain keywords, location | `search_founders(...)` filters | Previous company names are resolved to Crustdata ids (fuzzy name fallback). Keywords match skills, headline and role descriptions |
| Age range | `age.age_range`, `age.birth_year_range`, `age.method`, `age.confidence` | Bachelor's start − 18 (or end − 22); master's/PhD offsets; fallback first full-time job − 22 (low confidence) |
| Nationality | `nationality_signals.current_country / current_location / education_countries / work_locations` | Raw signals, the agent infers |
| Years of experience | `years_of_experience`, `career_start` | First non-intern role → today (Crustdata's own field is disabled on our plan) |
| Previous startup / serial founder | `founded_companies`, `founder_company_count`, `serial_founder`, `previous_startup_experience`, `past_founder_roles` | Founder/Co-founder/CEO/CTO titles across current + past, one per company |
| Part-time founder | `possible_part_time_founder` | Holds a founder role but primary title isn't founder-level |
| Side roles | `open_ended_past_roles` | Past roles with no end date (advisory/side, NOT primary job) |
| Technical founder | `technical.is_technical`, `degree_technical`, `technical_career_share`, `first_role_technical` | Degree OR ≥50% of full-time roles technical. `None` = no data |
| Solo vs co-founded, team size | `company.founder_count`, `co_founded`, `cofounders[]`, `team_size` | From the founder company's founder list + headcount |
| Previous exit | `exits[]` (company, acquired/ipo, acquirer, date, amount, person_was_founder), `exit_status` = verified / employee_exit_only / unverified | Acquisitions and IPOs of career companies **during the person's tenure** |
| Accelerator / big-investor trust | `investor_association.trust_level` = founder_backed_by_notable_investor / employee_at_notable_backed_company / worked_at_investor / none_found, plus `backed_companies[]` and `worked_at_investor[]` | Investors of every company in their career, matched against `NOTABLE_INVESTORS` (YC, Sequoia/Peak XV/Surge, Accel, Lightspeed, Antler, Techstars, a16z, Blume, Elevation, ...) + any investor Crustdata tags "accelerator" + YC batch in the company name |
| Open source | `github.has_github`, `total_stars_bucket` (<10 / 10-99 / 100-999 / 1000+), `followers_100_plus` | Filter-only checks. **Not available:** repo names, languages, commits, contributions. Web-search for those |
| Publications | `research.has_publications`, `article_count`, `citations`, `h_index`, `profiles[].top_articles` | Crustdata research profiles. Papers outside that index need a web search |

## Changes from the original spec, and why
1. **Person search returns career history, so Step 2 people enrich is mostly unnecessary.** `search_founders` and `enrich_companies` (via `founders`) both return full history. `enrich_people` is only for someone known by LinkedIn URL alone.
2. **Email works, with all sends routed to team inboxes.** The contact-enrich API is disabled on our plan, but person enrich returns business emails (+1 credit), so `find_email` gets the real address for the memo. The rules forbid agents contacting real people, so **send every outreach email to `outreach_recipient(...)["send_to"]`**. That is always one of the team's own inboxes in `DEMO_RECIPIENTS` (same founder → same inbox). If `DEMO_RECIPIENTS` is empty it returns `None` and nothing should be sent. Put "Intended for: <real email>" in the email body so the demo video shows who it was written for.
3. **Headcount at 3/6/12 months is computed, not fetched.** Enrich returns weekly headcount back to ~2023, and `headcount_signals` reads it. The same data works for any past date, which is what the backtest needs.
4. **"Active job postings" doesn't exist in Crustdata.** There's no open/closed flag. We report postings in the last N days plus `latest_posted_at`. Example: Crustdata itself has 27 postings indexed, the latest from 2026-04-22. Say "11 postings in the last year", never "11 open roles".
5. **Funding stage `None` means "no disclosed funding", not "pre-seed".** `search_companies(..., include_unfunded=True)` keeps those companies, because they *are* the "before their first round" targets. Valid stages: `pre_seed, angel, seed, series_a, series_b, ..., undisclosed, grant, convertible_note, debt_financing`.
6. **Leadership change = new founder or new CXO**, tracked as `people.founders` / `people.cxos` "added". Departures can't be tracked as an event; they show up in the record diff. All three triggers were validated against the API (free preview).
7. **Added `founder_roles`.** Many founders' primary title is something else (e.g. "Associate Principal" at a big company with a side "Founder" role). The memo can flag this as a part-time founder risk.

## Things the agent owner needs to know
- **Sending email is your side** (SMTP / Gmail API / Resend). This layer only decides *who* receives it: always `outreach_recipient(...)["send_to"]`, never `find_email(...)["email"]`. `DEMO_RECIPIENTS` in `.env` = team-owned dummy inboxes, comma-separated.
- **Backtest leak:** search filters (`max_headcount`, `funding_stages`) use *today's* values. For a backtest, search with stable filters only (country, founded_after, founder background), then `enrich_companies` and `snapshot_as_of(profile, D)`. Score "Meet" against `outcome_rounds`. `description`, `leadership` and `industries` are current-only (listed in `leakage_warnings`).
- **Two people can have the same name.** Dedupe on `crustdata_person_id` / `crustdata_company_id`, never on name. Use `identify_company` when the user types a company name; several close-confidence matches = ambiguous-identity exception.
- **Roles with `end_date: None` in `past_roles` are open-ended side roles** (mentor, advisor), not proof the person still works there.
- **Data freshness:** profiles refresh every 1–30 days. Use `headcount_signals(...)["latest_point_date"]` / `source.retrieved_at` to say how fresh a fact is.
- **Watcher delivery:** Crustdata POSTs to `WATCH_WEBHOOK_URL` (the FastAPI `/webhook` route via ngrok). In that route call `parse_watch_event(body)` and re-queue each `company_id`. Payloads with `is_test=True` are test pings. The ngrok URL changes on every restart, so watches created with an old URL stop delivering: create watches *after* ngrok is up, and recreate them if it restarts.
- **Rate limits:** enrich 15/min, search 30/min. The client paces and retries on its own, but a 50-company run takes ~4 min uncached. Enrich in batches (`enrich_companies` takes a list and sends 25 per call).
- **Budget:** a full thesis run (25 companies searched + enriched + jobs) costs ~75 credits. `founder_insights` costs ~10–15 credits per founder the first time (it enriches every company in their career), and nothing on re-runs. We have ~15,000 credits, so cost isn't a constraint.
- **Backtests with `founder_insights(people, as_of=D)`:** roles started and exits dated after D are dropped, but investor lists, GitHub and research are today's values (see `leakage_warnings`).
- **Exit data is noisy for big companies** (Crustdata has old/partial deals for Adobe, Uber, ...). That's why exits are kept only if they happened during the person's tenure. Trust `person_was_founder: True` exits most.
