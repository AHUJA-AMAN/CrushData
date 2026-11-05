# CrushData frontend

Vite + React + TypeScript. Runs on mock data by default, so it works without the backend.

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production build
```

## Connecting to the backend

All HTTP calls are in `src/api.ts`, one function per endpoint:

| Function | Endpoint |
| --- | --- |
| `startRun(req)` | `POST /run` |
| `getStatus(jobId)` | `GET /status/{job_id}` |
| `getResults(jobId)` | `GET /results/{job_id}` |

Copy `.env.example` to `.env.local` and set `VITE_USE_MOCK=false` to use the real API.
`VITE_API_BASE` defaults to `http://localhost:8000`. The backend must allow CORS from `http://localhost:5173`.

Response types are in `src/types.ts`; mock data in `src/mock.ts` uses the same shape.

## Screens

- `/` Thesis input (simple fields plus collapsible advanced founder profile)
- `/status` Pipeline status (polls every 2s, redirects to results when done)
- `/results` Memo cards with Meet / Watch / Pass filter
- `/exceptions` Companies with `exception_flag = true`, with "Mark resolved"

## Request format

Multi-select fields are sent as one comma-separated string, e.g. `"sector": "developer tools, fintech"`,
`"geography": "Asia, India"`, `"stage": "pre-seed, seed"`. Advanced fields left on "Any" are omitted from `founder_profile`.
The simple-mode keyword is sent as `thesis.founder_keyword`.
