# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-24

### Added
- `exposures`: net delta (raw + beta-adjusted), gross/net exposure as
  fractions of equity, Herfindahl concentration, top-N share; fractions are
  `None` (never invented) without an equity base.
- `hedges`: pure-function rules engine — `delta_trim_rule` (hysteresis band,
  hedge ratio h = −Δ_portfolio/Δ_hedge), `vol_regime_rule` (trailing realized
  vol vs target → scale-down factor), `exposure_cap_rule` (gross/net caps →
  per-symbol trims, highest-beta-first or pro-rata); every rule returns
  proposals plus diagnostics explaining quiet rules.
- `safety`: kill-switch on drawdown breach, stale market data, or missing
  prices — halted cycles emit alerts and zero proposals.
- `scheduler`: `run_cycle()` — idempotent, stateless-by-design with an
  explicit serializable `LoopState` (dedupe signature, cycle/halt counters);
  designed for scheduled runs, parallelizable across portfolios.
- `presets`: `conservative`/`balanced`/`aggressive` hedge configs.
- `demo`: seeded drift-breach, vol-regime-shift, and stale-data scenarios.
- `adapters`: lazy sibling adapters — positions from trade-paper, prices from
  trade-data-*, vol from trade-volforecast (internal fallback), betas from
  trade-factors (1.0 fallback); proposals shaped as trade-paper
  approval-queue payloads (user is the final gate).
- CLI: `exposures`, `propose` (dry-run default; `--submit` prints approval
  payloads), `presets`, `license`, `update-check` with table/JSON/CSV output.
- Docs: README with "The maths", `docs/ARCHITECTURE.md` (stack placement:
  risk sets constraints → hedge adjusts → paper executes),
  `docs/METHODOLOGY.md`, `examples/hedge_example.py`.
- 52 tests, all passing.
