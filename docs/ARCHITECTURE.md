# ARCHITECTURE — trade-hedge

The auto-hedging loop: the adjustment engine that keeps a portfolio inside
its risk limits as prices move. Pure Python, stdlib-only, zero UI-framework
imports.

## Where it sits in the logic stack

```
market data (trade-data-*) ──▶ strategies (trade-strategies)
        │
        ▼
research desk (trade-agents: debate ─▶ overfit desk ─▶ PM)
        │
        ▼
risk limits (trade-risk)            ◀── sets CONSTRAINTS: sizes, limits, caps
        │
        ▼
trade-hedge (THIS REPO)             ◀── ADJUSTMENT engine: continuous exposure
        │                               monitor + hedge proposals; keeps the
        │                               portfolio inside the constraints as
        │                               prices move
        ▼
execution (trade-paper)             ◀── EXECUTES: approval queue; the USER is
        │                               the final gate. The loop never places
        ▼                               orders — it only emits proposals.
ledger (trade-paper audit store)
```

Why three separate layers instead of one "risk manager":

- **trade-risk sets constraints.** Position sizes, per-name limits, gross/net
  caps, drawdown limits. These are policy: they say what the box is.
- **trade-hedge is the adjustment engine.** Prices move; the portfolio drifts
  out of the box. The loop measures exposure, proposes the minimum adjustment
  to get back inside, and re-checks every cycle. It says how to stay in the
  box, without ever deciding what the box is or placing an order.
- **trade-paper executes.** Proposals enter its approval queue, where the user
  approves or rejects each one. Execution, fills, and the audit ledger live
  here — never in the loop.

Collapsing adjustment into risk would couple measurement to policy; collapsing
it into execution would let a scheduled loop trade without a human gate. The
separation is the safety story: *measure → propose → approve → execute* are
four different repos.

## Module map

```
src/trade_hedge/
├── __init__.py      # public API: run_cycle, exposures, rules, presets, safety, adapters
├── exposures.py     # compute_exposures: net/gross delta, beta-adjusted, concentration
├── hedges.py        # rules engine: delta_trim_rule, vol_regime_rule, exposure_cap_rule
├── safety.py        # kill-switch: drawdown / stale data / missing prices -> HALT
├── scheduler.py     # run_cycle: safety -> exposures -> proposals; LoopState threading
├── presets.py       # DEFAULT_CONFIG + conservative/balanced/aggressive presets
├── demo.py          # seeded scenarios: drift breach, vol-regime shift, stale data
├── adapters.py      # lazy sibling adapters (trade-paper, trade-data-*, volforecast, factors)
├── licensing.py     # license-key + update-check hooks (suite convention, stubbed)
└── cli.py           # exposures | propose | presets | license | update-check
```

## Design decisions

- **Proposals, never orders.** Every rule emits a plain-dict proposal
  (`action`, `instrument`, `qty`, `reason`, `expected_delta_impact`,
  `rule_id`). Nothing in this repo can reach a broker. `proposals_to_paper_payloads`
  shapes proposals for trade-paper's approval queue, where the user approves.
- **Pure rules.** Each rule is a pure function of `(exposures, config,
  market_state)` — no I/O, no hidden state, fully testable. Rules also return
  diagnostics (`evaluated`, `reason`) so a quiet rule is *explained*, not
  silent.
- **Hysteresis kills churn.** The delta rule acts only outside
  `[target − band, target + band]`, then returns delta to target exactly.
  Without the band, a portfolio sitting on the threshold would emit opposing
  proposals every cycle.
- **Stateless-by-design scheduler.** `run_cycle` is idempotent: identical
  inputs → identical outputs. The only memory is an explicit,
  JSON-serializable `LoopState` the caller threads through (cycle count,
  last proposal signature for dedupe, consecutive halts). No module globals.
- **Kill-switch mirrors trade-paper's guard philosophy.** Drawdown breach,
  stale prices, or missing prices → halted cycle, zero proposals, named
  alerts. Exposures are still computed (informative) but no action is
  proposed.
- **Dry-run is the default.** The CLI computes and reports; `--submit` only
  prints the approval-queue payloads. Submitting still sends nothing anywhere.
- **Lazy siblings.** `adapters.py` imports `trade_paper` / `trade_data_*` /
  `trade_volforecast` / `trade_factors` inside functions with helpful
  pip-install errors (or documented internal fallbacks). trade-hedge imports
  and tests clean with nothing else installed.

## Scaling

- `compute_exposures` is O(positions); rules are O(positions); the vol
  estimator is O(window).
- `run_cycle` is stateless per portfolio (one `LoopState` per portfolio), so
  cycles parallelize across portfolios without signature changes; per-rule
  work can move to a process pool later.
- The expensive inputs (prices, betas, vol history) are *provided* by the
  caller — this repo never fetches. Feed scaling belongs to the data engines.

## Interop

| Sibling | Adapter |
|---|---|
| trade-paper | `positions_from_paper` (ledger → positions); `proposals_to_paper_payloads` (proposals → approval-queue payloads) |
| trade-data-equities / -crypto / -futures / -options | `prices_from_data` (latest prices) |
| trade-volforecast | `vol_from_volforecast` (realized vol; internal estimator fallback) |
| trade-factors | `betas_from_factors` (market betas; 1.0 fallback) |
| trade-risk | same config language (caps, limits); risk sets constraints, this repo adjusts |
| trade-suite | consumes `run_cycle()` results in the operations pipeline |

## Conventions honored

Suite-standard: engine/UI split (there is no UI), stdlib-only, semantic
versioning + CHANGELOG, stubbed license/update hooks, README "The maths"
section (what you learn / why it matters / the maths / honest limitations),
fresh-clone verification before release.
