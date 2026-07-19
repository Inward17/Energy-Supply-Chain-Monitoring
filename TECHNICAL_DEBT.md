# Technical Debt Register

This register tracks known production and demo risks that are intentionally
outside the scope of the news-balancing change.

## P0: Remove external API calls from HTTP request paths

Status: partially remediated on 2026-07-14.

The documented Shadow Cache guarantee is currently violated by these paths:

- POST /api/orchestrator/war-room synchronously calls Gemini through
  generate_emergency_brief().

The dashboard GET paths were remediated: Brent and BOAT rolling statistics now
read only from the local market_prices cache, and canonical SDI snapshots are
computed by the background worker and persisted for the timeline.

Risk: network latency, rate limits, or provider outages can delay or fail a
dashboard request during a live demonstration.

Target remediation:

1. Generate War Room briefs asynchronously and cache them by scenario inputs,
   or return deterministic local guidance while a brief is pending.
2. Preserve last-known-good brief values and explicit degradation metadata.

Acceptance criteria: with outbound network access disabled, all dashboard GET
endpoints and War Room simulation return within the local response-time budget
without exposing provider errors.

## P1: Restore strict TypeScript health

Status: confirmed on 2026-07-13.

next.config.mjs currently sets typescript.ignoreBuildErrors to true.
Running tsc --noEmit reports errors in:

- components/energy/tabs/market-pulse.tsx
- components/energy/tabs/reroute-matrix.tsx
- components/energy/tabs/risk-intelligence.tsx
- components/energy/tabs/war-room.tsx
- tests/e2e/smoke.spec.ts

Target remediation: fix all strict errors, remove ignoreBuildErrors, and add
type checking to continuous integration.

Acceptance criteria: both tsc --noEmit and next build pass without suppressing
type errors.

## Operational note: Sentinel Gemini usage

The live worker calls process_unprocessed_batch(batch_size=10) once per
scheduled cycle. Sentinel builds one prompt containing those ten headlines and
performs one Gemini generate_content call; it does not internally split the
batch into two five-headline calls. Historical backtests and War Room briefings
have separate Gemini usage and should be budgeted independently.

## Operational note: Backtest Vessel Density Exclusion

Historical backtest runs (via `run_backtest.py`) structurally exclude the vessel 
density term (`delta_d_vessel`) because historical AIS ingestion data is unavailable
for dates prior to system deployment. To avoid diluting the historical index with 
a neutral/dead weight, the backtest recalculates the SDI by proportionally 
redistributing the vessel weight (`w2`) across the remaining three signals 
(geopolitical risk, price, and freight). The historical index is therefore a true
3-signal composite, while the live system uses a 4-signal composite.
