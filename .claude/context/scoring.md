# Scoring model

**SDI** = 100 × (w1·P_risk + w2·ΔD_vessel + w3·ΔP_price + w4·ΔP_freight)
weights 0.50 / 0.25 / 0.10 / 0.15 (`SDI_W1..W4`, `src/utils/metrics.py`).

Bands (`constants.SDI_BANDS`, returned as `sdi_band`):
LOW <30 · MODERATE <50 · ELEVATED <65 · SEVERE <80 · CRITICAL.

- **P_risk**: max (not sum) of decayed event contributions. Half-life by
  `disruption_type`. Indirect chokepoint exposure ×0.5; producer reached only via
  a transit chokepoint ×0.7. `directly_affected_chokepoints` NULL = legacy row →
  full severity; `[]` = indirect.
- **ΔD_vessel**: tanker share per region per hourly bucket vs median of history
  (self-calibrated). Gates: ≥12 typed vessels, ≥15% type coverage, ≥6 baseline
  buckets, ≤3 h stale, ≥3 regions. Else falls back / reports `ais_status`.
- **ΔP**: Brent z-score vs 30-day mean/σ; **ΔF**: BOAT ETF stress.
- Confidence band applies only to the geopolitical component.
- Backtests use a 3-signal composite (vessel weight redistributed); live does not.

Sentinel returns `{"events":[...]}` → list; types normalised to a fixed set,
severity/confidence clamped, text truncated. Backtest takes the max-severity
event per day (`run_backtest.pick_day_event`).

**Data health** (frontend `feedHealth`): AIS ok/partial/down; news stale >24 h;
market stale >3 calendar days; Gemini configured. Missing vessel term is shown
as "no data", never as 0.
