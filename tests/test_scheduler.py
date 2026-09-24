"""Tests for scheduler.py: run_cycle idempotency, halts, state threading."""

import json

from trade_hedge.demo import demo_drift_breach, demo_stale_data, demo_vol_regime_shift
from trade_hedge.presets import DEFAULT_CONFIG
from trade_hedge.scheduler import LoopState, run_cycle, state_from_json, state_to_json


def test_run_cycle_produces_proposals_on_drift():
    ps, ms, c = demo_drift_breach(seed=7)
    result = run_cycle(ps, ms, c, LoopState())
    assert result["halted"] is False
    assert len(result["proposals"]) >= 1
    assert "exposures" in result
    assert "diagnostics" in result
    assert result["state_snapshot"]["cycles_run"] == 1


def test_run_cycle_idempotent():
    ps, ms, c = demo_drift_breach(seed=7)
    r1 = run_cycle(ps, ms, c, LoopState())
    r2 = run_cycle(ps, ms, c, LoopState())
    assert r1["proposals"] == r2["proposals"]
    assert r1["exposures"] == r2["exposures"]
    assert r1["alerts"] == r2["alerts"]


def test_run_cycle_stale_data_zero_proposals():
    ps, ms, c = demo_stale_data(seed=7)
    result = run_cycle(ps, ms, c, LoopState())
    assert result["halted"] is True
    assert result["proposals"] == []
    assert result["state_snapshot"]["consecutive_halts"] == 1
    # exposures are still computed (informative), proposals are not
    assert result["exposures"]["n_positions"] == 5


def test_run_cycle_vol_regime():
    ps, ms, c = demo_vol_regime_shift(seed=7)
    result = run_cycle(ps, ms, c, LoopState())
    assert result["halted"] is False
    assert any(p["rule_id"] == "vol_regime" for p in result["proposals"])


def test_loop_state_threading_and_dedupe_signal():
    ps, ms, c = demo_drift_breach(seed=7)
    state = LoopState()
    r1 = run_cycle(ps, ms, c, state)
    assert r1["changed_since_last"] is True  # nothing before
    r2 = run_cycle(ps, ms, c, LoopState(r1["state_snapshot"]))
    assert r2["changed_since_last"] is False  # identical proposals, dedupe signal
    assert r2["state_snapshot"]["cycles_run"] == 2


def test_loop_state_json_roundtrip():
    ps, ms, c = demo_drift_breach(seed=7)
    r = run_cycle(ps, ms, c, LoopState())
    blob = state_to_json(r["state_snapshot"])
    restored = state_from_json(blob)
    assert restored["cycles_run"] == 1
    r2 = run_cycle(ps, ms, c, restored)
    assert r2["changed_since_last"] is False


def test_default_config_is_safe():
    # DEFAULT_CONFIG alone must produce a valid cycle on the drift demo.
    ps, ms, _ = demo_drift_breach(seed=7)
    result = run_cycle(ps, ms, dict(DEFAULT_CONFIG), LoopState())
    assert result["halted"] is False
