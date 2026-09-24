"""trade-hedge end to end: drift breach, vol-regime shift, kill-switch.

Run from the repo root:
    PYTHONPATH=src python3 examples/hedge_example.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

from trade_hedge import run_cycle, LoopState
from trade_hedge.adapters import proposals_to_paper_payloads
from trade_hedge.demo import (
    demo_drift_breach,
    demo_stale_data,
    demo_vol_regime_shift,
)
from trade_hedge.presets import DEFAULT_CONFIG


def show(title: str, ps: dict, ms: dict, config: dict, state: LoopState) -> LoopState:
    result = run_cycle(ps, ms, config, state)
    print(f"\n=== {title} ===")
    e = result["exposures"]
    print(f"halted={result['halted']}  "
          f"net delta (beta-adj)={e['net_delta_frac_beta_adj']:+.2%} of equity  "
          f"gross={e['gross_frac']:.2%}  HHI={e['herfindahl']:.3f}")
    for a in result["alerts"]:
        print(f"  ALERT: {a}")
    for p in result["proposals"]:
        print(f"  [{p['rule_id']}] {p['action']} {p.get('instrument') or ''} "
              f"qty={p.get('qty')} :: {p['reason'][:90]}")
    if not result["proposals"]:
        print("  (no proposals)")
    return LoopState(result["state_snapshot"])


def main() -> None:
    state = LoopState()
    ps, ms, config = demo_drift_breach(seed=7)
    state = show("1. tech drifts long — delta + gross-cap breach", ps, ms,
                 config, state)

    # What the payloads look like for trade-paper's approval queue.
    result = run_cycle(ps, ms, config, LoopState())
    payloads = proposals_to_paper_payloads(result["proposals"], run_id="demo-1")
    print(f"\n  -> {len(payloads)} approval-queue payload(s); "
          f"requires_user_approval={payloads[0]['requires_user_approval'] if payloads else '-'}")

    ps, ms, config = demo_vol_regime_shift(seed=7)
    state = show("2. calm turns turbulent — vol-regime scale-down", ps, ms,
                 config, state)

    ps, ms, config = demo_stale_data(seed=7)
    show("3. prices 3h old — kill-switch fires", ps, ms,
         config, state)
    print("\nDone. The loop proposes; trade-paper (and the user) disposes.")


if __name__ == "__main__":
    main()
