# Crustdata API — what we need for the VC sourcing agent

Verified against docs.crustdata.com (2026-11-06) plus one live `company/enrich` call on crustdata.com.

## Basics
- `https://api.crustdata.com`, headers `authorization: Bearer <key>`, `x-api-version: 2025-11-01`, `content-type: application/json`.
- Our account: **15,200 credits**. Check for free with `GET /account/credits`, which is what `ping()` uses.
- Errors come back as `{"error": {"type", "message", "metadata"}}`. Retry **429** (wait `x-ratelimit-reset` seconds, sliding window) and **5xx**. Never retry **400/401/402/403**. A 403 that names `denied_fields` means: ask for fewer `fields`.
- No match returns **200 with an empty list**, not 404. Treat that as "cannot verify", never as "doesn't exist".

## Endpoints, cost, rate limit
| Need | Endpoint | Cost | RPM |
|---|---|---|---|
| Find companies by thesis | `POST /company/search` | 0.03/result + premium groups (funding, headcount, hiring 0.2 each, filter and response billed separately) | 30 |
| Find founders/people | `POST /person/search` | 0.03/result + experience/education 0.1 each | 30 |
| Resolve name/domain → company | `POST /company/identify` | **free** | 30 |
| Full company profile | `POST /company/enrich` | **2 / company** (up to 25 per call) | 15 |
| Full person profile | `POST /person/enrich` | 1 / profile (max 25 URLs per call) | 15 |
| Jobs (hiring signal) | `POST /job/search` | 0.03/result | 30 |
| Web / news evidence | `POST /web/search/live`, `/web/enrich/live` | 1 / page | 10 |
| Field values for filters | `/company/search/autocomplete`, `/person/search/autocomplete` | free | 300 |
| Watch a company | `POST /watch/company` | create free, first run free, then 5 / notification | 10 |
| Account balance | `GET /account/credits` | free | 300 |

Rough budget: 50 companies enriched = 100 credits. That's cheap, so enrich freely and search with narrow `fields`.

## Search (company and person)
- Body: `filters`, optional `search: {query, mode: hybrid|lexical|semantic}`, `fields`, `sorts`, `limit`, `cursor`.
- **Ranked search** (`search` present): max 100 per page, at most 1,000 candidates, cursor expires 20 min after the first call, **no `sorts`**, `total_count` is always null.
- Filter-only search: `limit` 1–1000, include `sorts` when paginating, keep filters/sorts/fields identical between pages.
- Filter = `{field, type, value}` or `{op: "and"|"or", conditions: [...]}`.
- Operators: `= != < > in not_in is_null is_not_null (.)`(fuzzy all-words) `[.]`(exact phrase) `geo_distance`. **Use `=>` and `=<`, not `>=` and `<=`** (those return a 400).
- On person search, `=` matches the *whole* stored value: "Qorvo" gets 38 hits, "Qorvo, Inc." gets 4,146. Use `(.)` for names, or better, filter by `company_id`.
- `explain: true` on person search tells you which filter emptied the result.
- Omitting `fields` returns everything, which is huge and costly. Always pass `fields`.

### Company fields useful for the thesis
`basic_info.{name, primary_domain, year_founded, employee_count_range, industries}`, `locations.country` (ISO-3 like "IND" or the full name), `funding.{total_investment_usd, last_round_type, last_fundraise_date, investors}`, `headcount.{total, growth_percent.6m/12m}` (filterable, not sortable), `roles.distribution.engineering` (filter-only), `hiring.openings_count`, `taxonomy.categories`.

### Person fields useful for founders
`experience.employment_details.{current,past}.{title, company_name, company_id, start_date, seniority_level, function_category}`, `education.schools.school`, `basic_profile.location.country`, `years_of_experience_raw`, `recently_changed_jobs` (a role *ended* in the last 90 days, which is a "left to found something" signal), `assessment.authenticity.verdict` (fake-profile check, filter-only).
Filters on `current.*` and `past.*` let us express "founder now, infra engineer before".

## Enrich: real response shape (company)
`[{matched_on, match_type, matches: [{confidence_score, company_data}]}]`. Pass `fields` groups: `basic_info, headcount, funding, hiring, people, news, taxonomy, locations, web_traffic, ...` (default is `basic_info` only).
- `headcount.timeseries`: **weekly `[{date, employee_count}]` back to ~2023**, plus `growth_percent.{mom,qoq,six_months,yoy,two_years}`, `by_role_absolute`, `by_role_growth_6m_pct`.
- `funding.milestones[]`: one per round, `{date, amount_usd, round_type, investors, lead_investors, investors_detailed[]}`. Also `last_round_type`, `last_fundraise_date`, `total_investment_usd`.
- `people.founders[]` / `cxos[]` / `decision_makers[]`: **full person records with `experience` and `education`**, so one company enrich gives us founder backgrounds without separate person-enrich calls.
- With `headcount + funding + people` the payload is about **200KB**. Trim it before handing it to the LLM.

## Backtest ("only what was known on date D")
There's no as-of-date query; enrich returns *today's* profile. Rebuild date D ourselves:
- headcount at D = last `timeseries` point ≤ D; growth = compare points before D
- funding known at D = `milestones` with `date ≤ D` (anything after D is the **outcome** we score against)
- founder history at D = roles with `start_date ≤ D`
- **Leak risk**: search filters (`headcount.total`, `funding.*`) match *current* values, so thesis-time candidate lists must filter on stable fields (country, year_founded, founder background) and leave growth/funding to the date-filtered enrich data.

## Watchers (for "Watch" decisions)
`POST /watch/company` with `entities: {crustdata_company_ids: [...]}`, `track` (for example `{"op":"or","conditions":[{"field":"funding.milestones","type":"added","keys":[["round_type","date"]]},{"field":"headcount.total","type":"changed"}]}`), `config: {trigger: {type:"interval", every_hours: 24}}`, `notifications: [{type:"webhook", url}]`.
Webhook payload: `{metadata:{watch_id, run_id, ...}, results:[{changes:[{field,type,from,to}|{field,type:"added",new_elements}], record:{...}}]}`. The list can be edited with `PATCH`, `POST /watch/company/{id}/test` sends a sample, and the webhook needs a **public URL** (use ngrok during the demo).
