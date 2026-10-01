# PumpCycle — Backend API Documentation

**Version:** v1 (covers phases v0.1 → v1.5)
**Base URL:** `/api` (Next.js API routes, same origin as the dashboard)
**Format:** JSON. All prices are **cents per litre (c/L)** as decimal numbers. All timestamps are **ISO-8601 UTC**.
**Auth:** none — all endpoints are public and read-only. FuelCheck credentials live server-side in the ingestion Lambda only and are never exposed here.
**Golden rule:** this API never calls FuelCheck at request time — it serves only from PostgreSQL.

---

## Conventions

### Fuel type codes (as stored, from FuelCheck)
| Code | Meaning |
|------|---------|
| E10  | Ethanol 94 |
| U91  | Unleaded 91 |
| P95  | Premium 95 |
| P98  | Premium 98 |
| DL   | Diesel |
| PDL  | Premium Diesel |
| LPG  | LPG |

### Error shape (all endpoints)
```json
{ "error": { "code": "BAD_REQUEST", "message": "fuel must be one of E10, U91, P95, P98, DL, PDL, LPG" } }
```
| HTTP | code | When |
|------|------|------|
| 400 | BAD_REQUEST | invalid/missing query param |
| 404 | NOT_FOUND | unknown station code |
| 500 | INTERNAL | unexpected server error |

### Caching
Responses set `Cache-Control: public, s-maxage=3600, stale-while-revalidate=86400` — data changes ~once daily, so cache hard. (This is why Redis is NOT needed in v1.)

---

## Endpoints

### 1. `GET /api/meta`
Data freshness + coverage. Dashboard header calls this on load.

**Response 200**
```json
{
  "last_fetched_at": "2026-09-10T04:30:12Z",
  "stations": 2517,
  "readings": 3184220,
  "oldest_reading": "2026-08-13T00:00:00Z"
}
```

---

### 2. `GET /api/stations`
List/search stations.

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `q` | string | no | substring match on name/address (case-insensitive) |
| `postcode` | string | no | exact match on address postcode |
| `lat`,`lng` | number | no | must be given together; enables radius search (haversine) |
| `radius_km` | number | no | default 5, max 25; only with lat/lng |
| `limit` | int | no | default 50, max 200 |

**Response 200**
```json
{
  "stations": [
    {
      "code": "2051",
      "brand": "United",
      "name": "United Petroleum Wilberforce",
      "address": "539 Wilberforce Rd, WILBERFORCE NSW 2756",
      "lat": -33.563205,
      "lng": 150.8372818,
      "distance_km": 3.2
    }
  ]
}
```
`distance_km` only when lat/lng given. Sort: by distance when lat/lng given, else by name.

---

### 3. `GET /api/stations/{code}`
One station + its **latest** price per fuel type.

**Response 200**
```json
{
  "station": { "code": "2051", "brand": "United", "name": "United Petroleum Wilberforce",
               "address": "539 Wilberforce Rd, WILBERFORCE NSW 2756", "lat": -33.563205, "lng": 150.8372818 },
  "current_prices": [
    { "fuel": "E10", "price": 193.9, "reported_at": "2026-09-09T22:20:00Z" },
    { "fuel": "P98", "price": 237.5, "reported_at": "2026-09-09T22:20:00Z" }
  ]
}
```
**404** if code unknown.

---

### 4. `GET /api/prices/cheapest`
Cheapest current prices for one fuel type — the dashboard's headline widget.

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `fuel` | string | **yes** | one fuel code |
| `lat`,`lng`,`radius_km` | | no | as in /api/stations |
| `postcode` | string | no | alternative to lat/lng |
| `limit` | int | no | default 10, max 50 |

**Response 200**
```json
{
  "fuel": "E10",
  "as_of": "2026-09-10T04:30:12Z",
  "results": [
    { "station": { "code": "1733", "brand": "Speedway", "name": "Speedway West Ryde", "lat": -33.81027, "lng": 151.094204 },
      "price": 181.9, "reported_at": "2026-09-09T20:11:00Z", "distance_km": 1.9 }
  ]
}
```
"Current price" = most recent reading per (station, fuel). Readings older than **7 days** are excluded as stale.

---

### 5. `GET /api/prices/history`
Time series for one station + fuel — powers the station price chart.

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `station` | string | **yes** | station code |
| `fuel` | string | **yes** | fuel code |
| `days` | int | no | default 30, max 365 |

**Response 200**
```json
{
  "station_code": "1733",
  "fuel": "E10",
  "points": [
    { "date": "2026-08-13", "price": 187.9 },
    { "date": "2026-08-14", "price": 187.9 }
  ]
}
```
One point per day (last reading that day). Gaps = no report that day; the chart renders gaps, never interpolates.

---

### 6. `GET /api/trends/median`
Citywide daily median for one fuel — the cycle chart's backbone.

**Params:** `fuel` (required), `days` (default 90, max 365).

**Response 200**
```json
{
  "fuel": "E10",
  "points": [ { "date": "2026-08-13", "median": 191.4, "stations_reporting": 1890 } ]
}
```

---

### 7. `GET /api/cycle/status`   *(v1.5)*
Cycle-detection verdict for one fuel type.

**Params:** `fuel` (required).

**Response 200 — cycling regime**
```json
{
  "fuel": "E10",
  "regime": "cycling",
  "days_since_restoration": 18,
  "avg_cycle_length_days": 34,
  "phase": "falling",
  "advice": "wait",
  "confidence": "medium",
  "explanation": "Last citywide price jump detected 18 days ago; prices have fallen 9.2 c/L since. Typical cycle ~34 days.",
  "computed_at": "2026-09-10T04:35:00Z"
}
```

**Response 200 — no-cycle regime (a first-class state, not an error)**
```json
{
  "fuel": "E10",
  "regime": "no_cycle",
  "advice": "no_signal",
  "explanation": "No clear restoration events detected in the last 120 days. Cycle guidance is withheld rather than guessed.",
  "computed_at": "2026-09-10T04:35:00Z"
}
```
`regime`: `cycling | no_cycle | insufficient_data`. `advice`: `fill_now | wait | neutral | no_signal`.
**Design rule: the detector reports the absence of a signal honestly — it never fabricates a prediction.** (ACCC notes Sydney cycles have mostly been absent since Feb 2026 — no_cycle is the expected launch state.)

---

## Database schema (source of truth)

```sql
CREATE TABLE stations (
  code        TEXT PRIMARY KEY,          -- FuelCheck station code
  brand       TEXT NOT NULL,
  name        TEXT NOT NULL,
  address     TEXT NOT NULL,
  lat         DOUBLE PRECISION NOT NULL,
  lng         DOUBLE PRECISION NOT NULL,
  state       TEXT NOT NULL DEFAULT 'NSW',
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE price_readings (
  id           BIGSERIAL PRIMARY KEY,
  station_code TEXT NOT NULL REFERENCES stations(code),
  fuel         TEXT NOT NULL,
  price_cpl    NUMERIC(6,1) NOT NULL,     -- cents per litre
  reported_at  TIMESTAMPTZ NOT NULL,      -- station's own report time (parse FuelCheck's DD/MM/YYYY!)
  fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (station_code, fuel, reported_at)  -- idempotent ingestion: re-runs upsert, never duplicate
);

CREATE INDEX idx_readings_lookup ON price_readings (fuel, station_code, reported_at DESC);
CREATE INDEX idx_readings_date   ON price_readings (fuel, reported_at DESC);
```

Two timestamps by design: `reported_at` is the station's claim (drives all charts); `fetched_at` is ours (drives freshness/staleness logic).

## Out of scope for this spec (v2 — sketch only)
`POST /api/ask` — the RAG ask-box: router → text-to-query over Postgres (numeric questions) / retrieval (descriptive), Redis semantic cache, eval harness. Specced when v1.5 ships. Do not build yet.
