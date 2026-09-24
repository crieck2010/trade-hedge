# METHODOLOGY — trade-hedge

Formulas, estimators, and honest limitations.

## Exposure measurement

Positions are `(symbol, signed qty)`; prices are the latest available. Dollar
value `vᵢ = qtyᵢ · pxᵢ`. Net delta `Δ = Σ vᵢ`; beta-adjusted `Δ_β = Σ vᵢ · βᵢ`
with per-symbol betas from config (default 1.0) or `betas_from_factors`. Gross
exposure `G = Σ |vᵢ|`. Fractions divide by account equity `E` from config;
when equity is missing or zero, fractions are `None` — never invented.

Concentration uses gross market-value weights `wᵢ = |vᵢ| / G`:

- Herfindahl `H = Σ wᵢ²` (`1` = single name, `1/N` = N equal names)
- top-N share `= Σ` of the N largest weights (N configurable, default 5)

## Hedge rules

**Delta trim (rule `delta_trim`).** Target beta-adjusted delta fraction `t`
(default 0), hysteresis band `b` (default 0.02 of equity). If
`|δ_β − t| ≤ b`: silence (no churn). Otherwise the dollar excess is
`X = (δ_β − t) · E` and the proposal quantity is

    qty = −X / (px_hedge · β_hedge)

i.e. the hedge ratio `h = −Δ_portfolio / Δ_hedge`, so post-hedge delta lands
on target. The hedge instrument defaults to `"SPY"` — mapping it to a real
tradable instrument is user config, not this repo's job. Its beta is assumed
1.0 unless `hedge_instrument_beta` is set. Quantity is rounded to 4 decimals.

**Vol regime (rule `vol_regime`).** Trailing realized vol from
`market_state["portfolio_returns"]`:

    σ̂ = stdev(returns over last `vol_realized_window` bars) · √252

(sample stdev, n−1). If `use_volforecast` is set and trade-volforecast is
installed, its estimator is used instead (internal fallback otherwise). When
`σ̂ > σ_target · vol_act_threshold`, propose scaling gross exposure by
`f = min(1, σ_target / σ̂)`. Missing return history → rule unevaluated
(`evaluated: false`), never a crash.

**Exposure caps (rule `exposure_cap`).** Gross breach: `G/E > gross_cap`;
net breach: `|N|/E > net_cap`. Required cut `C = (frac − cap) · E`. Trim
ordering `highest_beta_first` (default): highest `|β|`, then largest `|vᵢ|`,
emitting per-symbol `reduce` proposals until covered; or `pro_rata`:
distribute `C` proportionally across all positions. Trim quantities oppose the
position (`qty` has the opposite sign of the holding).

## Kill-switch

Halt (zero proposals, named alerts) when any of:

1. drawdown `1 − E/peak` exceeds `max_drawdown` (default 0.10);
2. `market_state["as_of"]` is older than `max_stale_minutes` (default 60), or
   unparseable/missing;
3. any position symbol lacks a price.

The drawdown check is `>` (at-limit does not halt). Timestamps accept ISO
strings or epoch seconds (UTC assumed when naive).

## The loop

`run_cycle(portfolio_state, market_state, config, loop_state)`:

1. `safety_check` → if halted: exposures + alerts + zero proposals.
2. `compute_exposures`.
3. `propose_hedges` → proposals + per-rule diagnostics.
4. Thread `LoopState`: `cycles_run`, `consecutive_halts`, last proposal
   signature (sha256 of sorted rule/instrument/qty/action tuples). Same inputs
   → same outputs (idempotent); `changed_since_last` tells a scheduler whether
   the proposal set differs from the previous cycle.

## Honest limitations

- The hedge instrument is a **proxy**: basis risk means the hedge mis-covers
  exactly when correlations break — when you most want it to work.
- Vol targeting **lags regime shifts** by construction (it must observe the
  bad returns first); the window length trades responsiveness for noise.
- Betas are **backward-looking** estimates; `1.0` fallbacks are honest but
  crude.
- The delta math assumes **linear instruments** (shares/ETFs). Options Greeks
  are not modeled — see trade-data-options.
- The kill-switch trusts your **clock and feed**: garbage timestamps in,
  garbage safety out. Stale *correct-looking* prices pass the freshness check
  and the loop will rebalance on them — monitor your feed independently.
- Hysteresis bands, caps, targets, and trim modes are **user policy**, not
  discoveries. The loop keeps you inside *your* box; it does not tell you what
  the box should be.
- `scale_exposure` and `reduce` proposals are **advisory quantities**: slippage,
  spreads, and lot sizes are execution concerns (trade-paper), not modeled here.
- The seeded demos are Gaussian-ish and stationary; real portfolios drift,
  gap, and correlate in ways the demo does not.
