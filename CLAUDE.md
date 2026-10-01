# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## PumpCycle

NSW petrol price tracker on the official Government FuelCheck API. Daily serverless ingestion → Postgres time-series → Next.js dashboard → price-cycle detection → (later) a RAG ask-box.

**Owner:** Jordan Tam. **Purpose:** public portfolio piece — every architectural decision must be explainable by Jordan in an interview.

---

## The Prime Directive (read first)

**Claude Code is an accelerator, not an author.** Jordan must be able to explain every line of interview-critical code.

| Jordan hand-writes (Claude may review/suggest only) | Claude Code may scaffold freely |
|---|---|
| OAuth token acquisition, refresh, retry/backoff | Next.js pages, layout, chart components |
| Database schema & migrations (design decisions) | Postgres client boilerplate / CRUD plumbing |
| The cycle-detection algorithm (incl. no-cycle state) | Test fixtures and mock data |
| Ingestion upsert/idempotency logic | GitHub Actions CI YAML |
| (v2) RAG router logic & eval harness | UI styling, responsive layout |
| | README boilerplate, ESLint/Prettier config |

**The re-explain rule:** after any Claude Code session touching the left column, Jordan closes the session and re-explains the key file from memory. If he can't, that file isn't done.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Ingestion | **Python on AWS Lambda + EventBridge** (daily cron) | Mirrors Jordan's production pipelines at work; fetch script already Python |
| Database | **PostgreSQL on Neon** (free tier) | Time-series queries in SQL; serverless-friendly; free public demo |
| App + API | **Next.js (TypeScript) with API routes** | One deployable; no separate Express server |
| Hosting | **Vercel** | Free, zero-ops, native Next.js |
| Charts | Recharts (or similar) | Simple time-series rendering |
| CI | GitHub Actions | lint + tests on every PR |

**Explicitly deferred — do not add before v2:**
- **Redis** — no cache problem exists in v1 (daily-changing data + HTTP cache headers suffice). Redis enters at v2 as the semantic cache for the ask-box, where it has a real job. Adding it earlier is cargo-culting.
- Auth/user accounts, alerting/notifications, mobile app, ML price forecasting (explicitly rejected — simple rules beat naive ML on sawtooth data, and honest no-signal reporting beats both).

## Architecture

```
            (daily, 06:00 AEST)
EventBridge ──► Lambda (Python)
                  │  OAuth2 client-credentials (token ~12h)
                  ▼
          NSW FuelCheck API  ── all-prices fetch (1 call/day vs 2,500/mo quota)
                  │
                  ▼  parse DD/MM/YYYY → UTC; join stations↔prices; UPSERT (idempotent)
          PostgreSQL (Neon)
                  ▲
                  │  SQL only — API never calls FuelCheck
        Next.js API routes (/api/*)         ← see API.md (the contract)
                  ▲
                  │
        Dashboard (Next.js on Vercel)
        cheapest-near-me · station history · citywide median · cycle status
```

## Repository layout

### What actually exists today (v0.1 spike)
- Not yet a git repo — there is no `.gitignore`, but `backend/.env` holds real credentials. **Create `.gitignore` (`.env`, `prices_snapshot*.txt`) before the first `git add`.**
- `backend/main.py` — a single-file spike: gets a token, calls `GET /FuelPriceCheck/v1/fuel/prices`, joins `prices[].stationcode` → `stations[].code`, and writes a ~2 MB human-readable `prices_snapshot_*.txt`. No DB, no tests, no `requirements.txt` (deps: `requests`, `python-dotenv`).
- `backend/test.sh` — a curl smoke test of the token endpoint.
- `frontend/` — empty.
- `pumpcycle_architecture.mermaid` — the architecture diagram (matches the diagram below).

The spike's code (`parse_timestamp`, `build_station_lookup`) is meant to be split into the `ingestion/` modules below. Until that move happens, treat `backend/main.py` as the left-column (hand-written) code.

### Target layout
```
pumpcycle/
├── CLAUDE.md            ← this file
├── API.md               ← the API contract (source of truth for endpoints)
├── ingestion/           # Python Lambda
│   ├── fetch.py         # OAuth + FuelCheck client  [HAND-WRITTEN]
│   ├── transform.py     # parse/join/normalise      [HAND-WRITTEN]
│   ├── upsert.py        # idempotent DB writes      [HAND-WRITTEN]
│   └── tests/
├── app/                 # Next.js (TypeScript)
│   ├── api/             # routes implementing API.md
│   ├── (dashboard)/     # pages + components        [SCAFFOLD OK]
│   └── lib/
│       ├── db.ts        # Postgres client
│       └── cycle.ts     # cycle detection           [HAND-WRITTEN, v1.5]
├── db/migrations/       # SQL, numbered              [HAND-WRITTEN]
└── .github/workflows/ci.yml                          [SCAFFOLD OK]
```

## Environment variables (never commit; .env in .gitignore from first commit)

| Var | Where used | Notes |
|---|---|---|
| `FUEL_API_KEY` / `FUEL_API_SECRET` | ingestion only | Basic-auth pair for OAuth token endpoint |
| `DATABASE_URL` | ingestion + app | Neon Postgres connection string |

⚠️ The current spike (`backend/main.py`, `backend/test.sh`) uses different names: `AUTHORIZATION_HEADER` (a pre-built `Basic …` value) and `API_KEY`. Renaming them is Jordan's call — flag the mismatch, don't silently rename.

## Commands (current)
```bash
cd backend && python main.py                                   # live fetch → prices_snapshot_2026-08-11.txt (costs 2 API calls)
cd backend && set -a && . ./.env && set +a && ./test.sh        # token-endpoint smoke test
```
No test runner, linter, or package manager is set up yet. When they're added, put the commands here (the plan: pytest for `ingestion/tests`, plus the Next.js lint/test scripts).

## FuelCheck facts the code must respect
- OAuth2 client-credentials: `POST api.onegov.nsw.gov.au/oauth/client_credential/accesstoken`; bearer token lasts **~12h** — fetch once per run, never per request.
- Quota: **2,500 calls/month** free. Daily all-prices run ≈ 30 calls/month. Never fetch per user request.
- Timestamps arrive as **DD/MM/YYYY HH:MM:SS (Australian)** — parse explicitly; never let a generic parser guess MM/DD.
- Responses can mix in non-NSW rows — filter `state = 'NSW'`, log the rest, never crash on unknown station codes (log + skip).
- Required headers per request: `apikey`, `transactionid` (unique per call), `requesttimestamp` (also DD/MM/YYYY HH:MM:SS). The spike hardcodes `transactionid` and backdates `requesttimestamp` by 2 days — neither is production behaviour.
- `strptime` yields a *naive* datetime in NSW local time. Localise it to `Australia/Sydney` (DST-aware) before converting to UTC for `reported_at TIMESTAMPTZ`; never treat it as UTC.
- Raw payload keys: `stations[]` {`code`, `brand`, `name`, `address`, `location`…}; `prices[]` {`stationcode`, `fueltype`, `price`, `lastupdated`}.

## API.md essentials (read the full doc before touching any route)
API.md is the source of truth for both the **endpoints** and the **DB schema** (`stations`, `price_readings`). Migrations must match it. The rules that cut across multiple routes:
- Routes read only from Postgres and never call FuelCheck. No auth; all routes are GET.
- Every error has the shape `{ "error": { "code", "message" } }` with `BAD_REQUEST` / `NOT_FOUND` / `INTERNAL`. Validate `fuel` against the 7 codes (E10, U91, P95, P98, DL, PDL, LPG) and enforce the documented defaults/maxes (`limit`, `radius_km`, `days`).
- Every success response sends `Cache-Control: public, s-maxage=3600, stale-while-revalidate=86400`.
- "Current price" means the latest reading per (station, fuel) where `reported_at` is ≤7 days old.
- History has one point per day (the day's last reading). Gaps stay gaps; never interpolate.
- `reported_at` (the station's claim) drives charts. `fetched_at` (ours) drives freshness.
- The `UNIQUE (station_code, fuel, reported_at)` constraint is what makes ingestion idempotent: upsert on it.
- `/api/cycle/status`: `no_cycle` and `insufficient_data` are normal 200 responses, not errors, and `no_cycle` is the expected state at launch.
- Phase mapping: §1–5 = v1, §6–7 = v1.5, `POST /api/ask` = v2 (do not build).

## Conventions
- TypeScript `strict: true`; Python type hints on all ingestion functions.
- TDD on all hand-written logic: tests first for transform, upsert, cycle detection. Include the trap cases (DD/MM parsing, duplicate reading upsert, price with unknown station).
- Prices stored as `NUMERIC(6,1)` c/L — never floats for money-adjacent values in SQL.
- All API responses match API.md exactly; API.md changes first, code second.
- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`). Push at end of every session — work that exists only on the laptop doesn't exist.

## Phase roadmap & current status

| Phase | Contents | Status |
|---|---|---|
| v0.1 spike | OAuth + live fetch + join proven (10,567 records pulled) | ✅ done |
| **v0.1 finish** | schema migration, public repo, daily cron writing to Neon | **← CURRENT** |
| v1 | API routes per API.md §1–5 + dashboard (cheapest, history chart), deployed on Vercel, public URL | next |
| v1.5 | daily-median endpoint + cycle detection with honest `no_cycle` state | after v1 |
| v2 | RAG ask-box (router → text-to-query / retrieval, Redis semantic cache, eval harness) | sketched only — do not start |

**Definition of done, v0.1:** cron has run unattended ≥3 consecutive days; `SELECT count(*) FROM price_readings` grows daily; repo public with CI green.

## Working agreements for Claude Code sessions
1. Read API.md before implementing any route; the doc is the contract.
2. Propose a plan before multi-file changes ("no code yet").
3. Never touch `ingestion/fetch.py` token logic or `lib/cycle.ts` without being explicitly asked — and then suggest, don't write.
4. Never add dependencies without stating why in one line.
5. Run tests before declaring anything done; show the output.
