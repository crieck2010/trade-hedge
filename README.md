> [!IMPORTANT]
> **Consolidated into [TradeSuite](https://github.com/crieck2010/trade-suite)**  
> This engine has been consolidated into the unified [TradeSuite monorepo](https://github.com/crieck2010/trade-suite). Active development, bug fixes, releases, and unified testing now live in `trade-suite`. This repository is preserved as an archive.

# trade-hedge

The auto-hedging loop for the [trade-suite](https://github.com/crieck2010/trade-suite) — the adjustment engine that keeps a portfolio inside its risk limits as prices move. Pure-Python, stdlib-only, no NumPy, no pandas.

What it does:

- **Exposure measurement** — net delta (raw and beta-adjusted), gross/net exposure as fractions of equity, concentration (Herfindahl index, top-N share)
- **Delta trim with hysteresis** — proposes an offsetting hedge when beta-adjusted net delta leaves the no-trade band; the band kills churn
- **Vol-regime hedging** — trailing realized vol (internal estimator, or trade-volforecast when installed) above tolerance → propose a gross-exposure scale-down
- **Exposure caps** — gross/net cap breaches → per-symbol trim proposals, highest-beta-first or pro-rata
- **Kill-switch** — drawdown breach, stale market data, or missing prices → cycle halts, zero proposals
- **Scheduled loop** — `run_cycle()` is idempotent and stateless-by-design (explicit serializable `LoopState` threaded through), built for 3×-daily or every-N-minutes runs
- **Suite adapters (all lazy)** — positions from trade-paper, prices from trade-data-\*, vol from trade-volforecast, betas from trade-factors; proposals shaped as trade-paper approval-queue payloads

Where it sits: `trade-risk` sets **constraints** (sizes, limits) → `trade-hedge` is the **adjustment engine** (keeps the portfolio inside those constraints as prices move) → `trade-paper` **executes** (approval queue, user is the final gate). The loop never places orders itself — it emits hedge *proposals*.

Research/backtesting/paper-trading only — never live trading, never personalized investment advice.

## Install

```bash
pip install git+https://github.com/crieck2010/trade-hedge.git
```

Requires Python 3.10+. No third-party dependencies.

## Quick start

```bash
# one hedge-loop cycle on the seeded drift demo (dry-run by default)
trade-hedge propose --demo drift

# the vol-regime demo and the kill-switch demo
trade-hedge propose --demo vol
trade-hedge propose --demo stale

# just the exposures
trade-hedge exposures --demo drift --format json

# see what --submit would send to trade-paper's approval queue (still nothing leaves this machine)
trade-hedge propose --demo drift --submit

# presets and config overrides
trade-hedge presets
trade-hedge propose --demo drift --preset conservative --set max_drawdown=0.05
```

```python
from trade_hedge import run_cycle, LoopState
from trade_hedge.demo import demo_drift_breach
from trade_hedge.presets import DEFAULT_CONFIG

portfolio_state, market_state, config = demo_drift_breach(seed=7)
result = run_cycle(portfolio_state, market_state, dict(DEFAULT_CONFIG), LoopState())
print("halted:", result["halted"])
for p in result["proposals"]:
    print(p["rule_id"], p["action"], p["instrument"], p["qty"])
```

## CLI

```
trade-hedge exposures    --demo drift|vol|stale | --positions SYM=QTY... --prices SYM=PX...
trade-hedge propose      same inputs [--preset conservative|balanced|aggressive]
                         [--set KEY=VALUE ...] [--submit]
trade-hedge presets
trade-hedge license | trade-hedge update-check
```

Common options: `--seed 7`, `--equity 100000`, `--format table|json|csv`.

**Dry-run is the default.** `propose` computes and reports; nothing is emitted anywhere. `--submit` prints the trade-paper approval-queue payloads (still local — the queue, and the user, decide what happens next). Paper-trading only.

## The maths

**What you learn.** Whether your portfolio is drifting out of its risk box — and exactly what to do about it. The loop measures beta-adjusted net delta, gross/net exposure, and concentration; then three rule families propose hedges: delta trims that push net delta back to target, vol-target scale-downs when realized volatility runs hot, and cap trims when gross or net exposure breaches limits. A kill-switch halts everything on drawdown, stale data, or missing prices. You get proposals with reasons and expected impacts — never orders.

**Why it matters.** A portfolio that starts inside its risk limits does not stay there: winners grow, losers shrink, correlations shift, and volatility regimes change. Rebalancing by hand is slow and emotional; rebalancing by a naive rule churns you to death in fees. The hysteresis band is the middle path — act only when the deviation is real, then act exactly enough to return to target. Vol targeting is the same idea in risk units: hold a constant *amount of risk*, not a constant amount of dollars.

**The maths.**

- *Beta-adjusted net delta:* `Δ = Σ qtyᵢ · pxᵢ · βᵢ`, expressed as a fraction of equity `δ = Δ / E`. The hedge ratio is `h = −Δ_portfolio / Δ_hedge`: to remove `X` dollars of delta with an instrument whose one share moves `$px` per `$1` (times its beta), sell/buy `qty = −X / (px · β_hedge)` shares. This repo assumes linear instruments (shares/ETFs); see limitations.
- *Hysteresis:* with target `t` and band `b`, propose only when `|δ − t| > b`. Inside `[t−b, t+b]` the loop is deliberately silent — no churn. The proposal then returns delta exactly to target, not just to the band edge.
- *Vol targeting:* trailing realized vol `σ̂ = stdev(returns over window) · √252`. When `σ̂ > σ_target · threshold`, propose scaling gross exposure by `f = min(1, σ_target / σ̂)` — hold constant risk, not constant dollars.
- *Cap trims:* required cut `C = (exposure_frac − cap) · E`; allocate across symbols highest-|β|-first (then largest |value|), or pro-rata when configured.
- *Herfindahl concentration:* `H = Σ wᵢ²` with `wᵢ = |valueᵢ| / gross`; `H = 1` is a single name, `H = 1/N` is N equal names.

**Honest limitations.** The hedge instrument is a proxy, never the portfolio itself — basis risk means the hedge can under- or over-cover when correlations break, which is exactly when you most want it to work. Vol targeting lags regime shifts by construction (it needs the bad returns to *see* the bad returns). Beta estimates are backward-looking. The delta math assumes linear instruments — options Greeks are not modeled here (that is trade-data-options' job). The kill-switch needs a trustworthy clock and a fresh feed; garbage timestamps in, garbage safety out. Thresholds (bands, caps, targets) are user config, not discoveries — the loop keeps you inside *your* box, it does not tell you what the box should be.

## Interop

| Sibling | Adapter |
|---|---|
| trade-paper | `positions_from_paper` — positions from the ledger/audit store; `proposals_to_paper_payloads` — proposals shaped as approval-queue payloads (user is the final gate) |
| trade-data-equities / -crypto / -futures / -options | `prices_from_data` — latest prices via the engine of record |
| trade-volforecast | `vol_from_volforecast` — realized-vol estimator when installed; internal estimator otherwise |
| trade-factors | `betas_from_factors` — market betas when installed; 1.0 fallback otherwise |
| trade-risk | consumes the same config language (caps, limits); trade-hedge is the adjustment engine to trade-risk's constraints |
| trade-suite | consumes `run_cycle()` results in the operations pipeline |

All sibling imports are lazy — trade-hedge imports and tests clean with nothing else installed.

## Docs

- `docs/ARCHITECTURE.md` — stack placement, module map, and why hedging is separate from risk
- `docs/METHODOLOGY.md` — formulas, estimators, and honest limitations
- `examples/hedge_example.py` — drift breach, vol-regime shift, and kill-switch end to end

## License

MIT. See `LICENSE`.
