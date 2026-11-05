# Build notes

Running log: what we tried, what worked, what didn't. Feeds the README and demo.

## Approaches considered

## Log
- Crustdata layer: `crustdata/client.py` never raises; returns None and sets `client.last_error` so the agent can say "couldn't verify (reason)" instead of guessing. Retries 429/5xx using `x-ratelimit-reset`, stops immediately on 402/403.
- Backtest feasibility checked live: company enrich gives weekly headcount timeseries (back to 2023) + dated funding milestones + founders' full career history → we can rebuild "what was known on date D". Search filters use *current* values, so backtest candidate lists must avoid filtering on growth/funding (leak). Details: `crustdata/API_NOTES.md`.
