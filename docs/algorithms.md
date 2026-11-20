# Algorithms and calculations

How MERIDIAN turns raw feeds into the numbers on screen. Every value below is
taken from the code; the file that owns it is named so this page can be
checked against it. If a constant here disagrees with the code, the code wins
and this page is stale.

> This replaces `Energy_Supply_Chain_Algorithm_Calculation_Guide.docx`, a July
> 2026 snapshot that predates the current SDI weights, the routing fixes and
> the SPR model changes.

---

## 1. Supply Disruption Index (SDI)

`src/utils/metrics.py · supply_disruption_index()`, `src/agents/modeler_agent.py · compute_current_sdi()`

```text
SDI = 100 × (0.50·P_risk + 0.25·ΔD_vessel + 0.10·ΔP_price + 0.15·ΔP_freight)
```

Weights are `SDI_W1..SDI_W4` (env-overridable, must sum to 1.0). Geopolitical
risk carries half the index because it is the leading indicator; price and
freight are lagging, derived signals.

| Term | Meaning | Source |
|---|---|---|
| `P_risk` | Worst decayed event risk (see §2) | Sentinel events in `risk_events` |
| `ΔD_vessel` | Drop in tanker share vs a self-calibrated regional baseline, 0–1 | AIS `vessel_telemetry` |
| `ΔP_price` | Brent z-score vs 30-day mean, clipped at ±`MARKET_Z_CLIP_SIGMAS` (4.5), mapped to 0–1 | `market_prices` (BZ=F) |
| `ΔP_freight` | Same for BOAT, the Breakwave dry-bulk shipping ETF used as a freight proxy | `market_prices` (BOAT) |

**Bands** (`constants.SDI_BANDS`, returned as `sdi_band`): LOW < 30 ≤ MODERATE
< 50 ≤ ELEVATED < 65 ≤ SEVERE < 80 ≤ CRITICAL. The UI colours the headline
from the band, never from a local threshold.

**Confidence band.** Uncertainty applies only to the geopolitical component:

```text
margin = (P_risk × 0.50 × 100) × (1 − confidence)
band   = [max(0, SDI − margin), min(100, SDI + margin)]
```

`confidence` is the driving event's model confidence (0.5 if missing).

**Missing data is not disruption.** When AIS fails its quality gates (§3) the
vessel term is reported as unavailable (`ais_status`) and shown as "no data",
never as 0. Live SDI does not redistribute its weight, so a missing vessel term
caps the index; backtests do redistribute it (3-signal composite, §7).

---

## 2. Event risk and decay

`src/agents/modeler_agent.py · _decayed_risk()`, shared by the Modeler and the Fixer.

```text
decayed = 0.05 + (min(raw, 0.95) − 0.05) × 0.5^(age_days / half_life)
```

- Baseline `MODELER_BASELINE_RISK` = 0.05; a decayed event never falls below it.
- `age_days` from the article fetch time (`source_fetched_at`, else `created_at`).
- Half-life by disruption type (`RISK_EVENT_HALF_LIFE_DAYS_BY_TYPE`, env-overridable):

| Type | Half-life (days) |
|---|---|
| accident | 7 |
| military_conflict, piracy | 10 |
| weather, protest, unknown, default | 14 |
| producer_supply_shock | 30 |
| sanctions, embargo | 45 |

**Aggregation is `max`, not sum.** A chokepoint's or producer's risk is its
single worst decayed event, so two moderate events never add up to a severe
one, and exactly one event explains each score (the drill-down drawer names it).

**Exposure discounts** (chokepoint matrix): an event that only indirectly
involves a chokepoint counts × 0.5; a producer reached only through a transit
chokepoint counts × 0.7. `directly_affected_chokepoints = NULL` marks a legacy
row and counts at full severity.

---

## 3. Vessel density

`src/agents/modeler_agent.py`, `src/ingestion/ais_streamer.py`

- **Measure:** tanker share (`tankers / typed vessels`) per region per hourly
  bucket. A share is invariant to AIS type coverage and to the snapshot window;
  a raw count moves with both.
- **Baseline:** the median of the same region's own recent buckets, from the
  same query, so partial coverage biases both sides equally.
- **Quality gates** before the term is used: ≥ 12 typed vessels, ≥ 15 % type
  coverage, ≥ 6 baseline buckets, data ≤ 3 h old, ≥ 3 regions.
- **Collection:** a 600 s (`AIS_SNAPSHOT_SECONDS`) WebSocket window per run,
  longer than the ~360 s Type-5 broadcast period that carries ship type. A
  handshake rejected with HTTP 429 retries after 30 / 90 / 180 s.
- **Trade-off:** a uniform collapse of *all* traffic leaves the share
  unchanged. This detects tankers rerouting while other shipping continues, not
  a total port shutdown.

---

## 4. Sentinel (news → events)

`src/agents/sentinel_agent.py`

- One Gemini call per cycle scores a batch of up to 10 unprocessed headlines
  (`process_unprocessed_batch(batch_size=10)`), balanced across categories.
- Headlines are truncated, stripped of delimiter-like text and marked as
  untrusted data in the prompt.
- Model: `GEMINI_MODEL` (default `gemini-flash-latest`). On a 503 the call is
  retried once on `GEMINI_FALLBACK_MODEL` (default `gemini-flash-lite-latest`).
  On a 429 the next key in `GEMINI_API_KEYS` is tried.
- The reply is `{"events": [...]}`; each event is validated: types normalised to
  a fixed set, severity and confidence clamped to 0–1, chokepoints filtered to
  the canonical registry, text truncated.
- **Provenance.** Each event keeps only the headlines the model cites in
  `headline_indices`. If those are missing or invalid, the whole batch is
  attached and `sources_verified = FALSE`; the UI then labels the links
  "Batch context", not evidence.
- A batch Gemini answers with no relevant events is marked processed. A failed
  call leaves it for the next cycle.
- **Corroboration.** A severity of 0.7 or more (`CORROBORATION_SEVERITY`) rests
  on one model reading of scraped headlines, so it needs model-cited headlines
  from at least 2 distinct sites (`CORROBORATION_MIN_SOURCES`). Otherwise the
  severity is capped at 0.6 (`UNCORROBORATED_SEVERITY_CAP`), the event is
  stored with `corroborated = FALSE`, the reasoning records the model's
  original score, and the event drawer says so. Batch-context sources never
  count. Below the threshold the event is not assessed (`NULL`).

---

## 5. Reroute (Fixer)

`src/agents/fixer_agent.py · find_alternatives()`

1. **Destination.** Dropdown labels like `Rotterdam (Netherlands)` are reduced
   to the graph name. An unknown refinery is a 422, never a silent fallback.
2. **Candidates.** Neo4j export terminals that export a compatible grade and
   whose seeded `SHIPS_THROUGH` edges avoid the blocked chokepoint. With Neo4j
   down, the same rows are built from the seed data (with coordinates).
   A grade substitutes for the requested one within ±4 °API and ±1.0 %
   sulphur. Blends of two grades are considered at 10–90 % weights with linear
   API interpolation and the same ±1.0 % sulphur tolerance.
3. **Lead time** (`_route_lead_time`). The graph only knows each terminal's
   route *to India*; the route to another refinery can differ. So whenever
   `searoute` can restrict the blocked passage (Suez, Bab-el-Mandeb, Turkish
   Straits, Gibraltar, Panama, Hormuz), the restricted route *is* the route:

   ```text
   lead_time_days = restricted_sea_km / 1.852 / (13 kn × 24)        → route_basis "verified"
   ```

   Malacca and the Cape of Good Hope cannot be restricted, so the
   unrestricted route's geometry is checked against a box around the passage:
   a route that stays out of it is `verified`. Everything else is `unverified`
   (unrestricted route + static detour): a route crossing an unrestrictable
   passage, no path around the blockade (searoute reports length 0/inf rather
   than failing — treated as no route, never a 0-day voyage), or an engine
   error. No coordinates → the port's India baseline (if shipping to India) or
   an 8,000 NM fallback, labelled `estimated`.
4. **Landed cost.**

   ```text
   effective_rate  = 65,000 USD/day × (1 + (freight_index − 0.5) × FREIGHT_RATE_SENSITIVITY)
   freight_premium = effective_rate × voyage_days / 2,000,000 bbl
   landed_cost     = Brent + freight_premium
   ```

5. **Supplier risk.** The country's worst matching event, decayed exactly as in
   §2 (`severity × confidence`), floor 0.05, cap 0.95.
6. **Composite score** (0–1, higher is better):

   ```text
   0.35·(1 − cost/(1.5×Brent)) + 0.25·(1 − lead/45 d) + 0.25·(1 − risk) + 0.15·(1 − congestion)
   ```

7. **Ranking.** `cost` (cheapest landed), `speed` (fastest arrival) or
   `balanced` (composite), then a stable re-sort puts `verified` rows first.
   Only a verified row can be `recommended`; with none, nothing is recommended
   and the diagnostic is `no_verified_route`. The War Room uses the
   recommended row's lead time for SPR, so an unverified estimate never
   becomes an arrival date.
8. **Exclusions.** A blend row ("Iran + Iraq") is dropped if *any* leg's
   country is excluded (case- and whitespace-insensitive).
9. **Sanctions.** Rows whose country (or any blend leg) is in
   `SANCTIONED_SOURCE_COUNTRIES` carry `sanctioned: true` and a badge. They are
   labelled, not filtered; exclusions remain the user's choice. A country list
   is not sanctions screening.

---

## 6. SPR burn-down

`src/agents/spr_agent.py · calculate_spr_impact()`

**Capacity** is derived from the three ISPRL Phase I sites (MMT × 7.33 bbl/t):

| Site | MMT | Million bbl |
|---|---|---|
| Visakhapatnam | 1.33 | 9.75 |
| Mangaluru | 1.50 | 11.00 |
| Padur | 2.50 | 18.32 |
| **Total** | 5.33 | **39.1** |

**Shortfall** = India consumption (5.4 mb/d) × the blocked chokepoint's import
share. Every chokepoint has an explicit share (Hormuz 0.40, Suez 0.15,
Bab-el-Mandeb 0.12, Gibraltar 0.08 — an estimate, Malacca 0.05, Cape 0.02,
Turkish Straits 0.01, Panama 0.00). Unknown chokepoints are rejected; there is
no default share.

**No action:** `survival = 39.1 / shortfall`, `gap = max(0, lead_time − survival)`.

**Demand levers** (defaults 15 % run-rate cut, 8 % industrial priority, 10 %
transport rationing, each a share of total demand) ramp linearly to full
effect over 3 / 7 / 14 days:

```text
draw(day) = max(0, shortfall − Σ saving_i × min(1, (day+1) / ramp_i))
```

Survival with levers is the day the reserve runs dry under that ramping draw.
A **pessimistic** case repeats it with levers at 50 % effectiveness.

**Burn-down series.** Before arrival the reserve drains by the draw; on the
arrival day the draw and refill are split by the fractional lead time; after
arrival it refills at `replenish_share` × shortfall (default 0.5, a request
field). The result returns an `assumptions` list the UI shows beside it:
full initial fill, ramp days, possible lever overlap, the pessimistic case,
single-day arrival and the refill rate.

**Macro:** GDP loss = gap days × 0.035 %/day (≈ USD 37 bn per 1 % of a 3.7 tn
economy); inflation = gap days × 0.07 %/day. Scenario coefficients, not a
macro model.

---

## 7. Backtests

`run_backtest.py`

Historical runs replay archived headlines day by day and take the
maximum-severity event per day (`pick_day_event`). Historical AIS does not
exist, so the vessel weight is redistributed proportionally across the other
three signals: backtests are a 3-signal composite, the live index is 4-signal.
Days without headlines currently score about 25 instead of carrying the last
value forward (see `TECHNICAL_DEBT.md`).

Lead time = Brent breakout date − first SDI alert date. It is `null` (not 0)
when either observation is missing, with `missing_observations` naming which;
0 means both happened on the same day.
