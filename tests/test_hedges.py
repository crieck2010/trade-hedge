"""Tests for hedges.py: delta trim, vol regime, exposure caps."""

import datetime

from trade_hedge.demo import demo_drift_breach
from trade_hedge.exposures import compute_exposures
from trade_hedge.hedges import (
    delta_trim_rule,
    exposure_cap_rule,
    propose_hedges,
    trailing_realized_vol,
    vol_regime_rule,
)
from trade_hedge.presets import DEFAULT_CONFIG


def cfg(**kw):
    c = dict(DEFAULT_CONFIG)
    c.update(kw)
    return c


def exposures_for(positions, prices, **kw):
    return compute_exposures(positions, prices, cfg(**kw))


def market_state(**kw):
    base = {"prices": {}, "as_of": "2026-09-24T12:00:00Z"}
    base.update(kw)
    return base


# --- delta trim -------------------------------------------------------------

def test_delta_trim_breach_emits_proposal():
    # 100% long SPY vs target 0: delta frac = 1.0, band 0.02 -> breach
    e = exposures_for([{"symbol": "SPY", "qty": 200.0}], {"SPY": 500.0},
                      equity=100_000.0)
    proposals, diag = delta_trim_rule(e, cfg())
    assert len(proposals) == 1
    p = proposals[0]
    assert p["rule_id"] == "delta_trim"
    assert p["instrument"] == "SPY"
    # excess = 1.0 * 100k = 100k; qty = -100k/500 = -200
    assert p["qty"] == -200.0
    assert p["expected_delta_impact"] == -100_000.0
    assert "hysteresis" in p["reason"]


def test_delta_trim_no_churn_inside_band():
    e = exposures_for([{"symbol": "SPY", "qty": 2.0}], {"SPY": 500.0},
                      equity=100_000.0)
    # delta frac = 1000/100000 = 0.01 < band 0.02
    proposals, diag = delta_trim_rule(e, cfg())
    assert proposals == []
    assert "band" in diag["reason"]


def test_delta_trim_boundary_exact_band_is_quiet():
    e = exposures_for([{"symbol": "SPY", "qty": 4.0}], {"SPY": 500.0},
                      equity=100_000.0)
    # delta frac = 0.02 == band -> not a breach (<=)
    proposals, _ = delta_trim_rule(e, cfg())
    assert proposals == []


def test_delta_trim_targets_nonzero_target():
    # target 0.10 long, portfolio at 0.30 -> trim only the excess 0.20
    e = exposures_for([{"symbol": "SPY", "qty": 60.0}], {"SPY": 500.0},
                      equity=100_000.0)
    proposals, _ = delta_trim_rule(e, cfg(delta_target=0.10))
    assert len(proposals) == 1
    assert proposals[0]["qty"] == -40.0  # -0.20 * 100k / 500


def test_delta_trim_missing_hedge_price_is_quiet():
    e = exposures_for([{"symbol": "AAA", "qty": 200.0}], {"AAA": 500.0},
                      equity=100_000.0)
    proposals, diag = delta_trim_rule(e, cfg(hedge_instrument="SPY"))
    assert proposals == []
    assert "SPY" in diag["reason"]


def test_demo_drift_breach_trips_delta_rule():
    ps, ms, c = demo_drift_breach(seed=7)
    e = compute_exposures(ps["positions"], ms["prices"], c)
    assert abs(e["net_delta_frac_beta_adj"]) > c["hysteresis_band"]
    proposals, _ = delta_trim_rule(e, c)
    assert len(proposals) == 1


# --- vol regime --------------------------------------------------------------

def test_vol_regime_scale_down():
    import random
    rng = random.Random(3)
    rets = [rng.gauss(0.0, 0.03) for _ in range(126)]  # ~47% ann vol
    e = exposures_for([{"symbol": "SPY", "qty": 100.0}], {"SPY": 500.0},
                      equity=100_000.0)
    proposals, diag = vol_regime_rule(e, cfg(vol_target=0.15),
                                      market_state(portfolio_returns=rets))
    assert len(proposals) == 1
    p = proposals[0]
    assert p["action"] == "scale_exposure"
    assert 0 < p["details"]["scale"] < 1.0
    assert abs(p["details"]["scale"] - 0.15 / diag["realized_vol"]) < 1e-9


def test_vol_regime_quiet_when_calm():
    import random
    rng = random.Random(3)
    rets = [rng.gauss(0.0, 0.005) for _ in range(126)]  # ~8% ann vol
    e = exposures_for([{"symbol": "SPY", "qty": 100.0}], {"SPY": 500.0},
                      equity=100_000.0)
    proposals, diag = vol_regime_rule(e, cfg(vol_target=0.15),
                                      market_state(portfolio_returns=rets))
    assert proposals == []


def test_vol_regime_missing_history_unevaluated():
    e = exposures_for([{"symbol": "SPY", "qty": 100.0}], {"SPY": 500.0},
                      equity=100_000.0)
    proposals, diag = vol_regime_rule(e, cfg(), market_state())
    assert proposals == []
    assert diag["evaluated"] is False


def test_trailing_realized_vol_none_on_short():
    assert trailing_realized_vol([0.01]) is None
    assert trailing_realized_vol([]) is None


# --- exposure caps ------------------------------------------------------------

def test_gross_cap_trim_highest_beta_first():
    e = exposures_for(
        [{"symbol": "HIGH", "qty": 100.0}, {"symbol": "LOW", "qty": 100.0}],
        {"HIGH": 500.0, "LOW": 500.0},
        equity=100_000.0, betas={"HIGH": 2.0, "LOW": 0.5})
    # gross = 100k = 1.0 of equity; cap 0.5 -> cut $50k
    proposals, diag = exposure_cap_rule(e, cfg(gross_cap=0.5))
    assert len(proposals) == 1
    assert proposals[0]["instrument"] == "HIGH"
    assert proposals[0]["qty"] == -100.0  # full HIGH position trimmed
    assert proposals[0]["action"] == "reduce"


def test_gross_cap_pro_rata():
    e = exposures_for(
        [{"symbol": "A", "qty": 100.0}, {"symbol": "B", "qty": 100.0}],
        {"A": 500.0, "B": 500.0}, equity=100_000.0)
    proposals, _ = exposure_cap_rule(e, cfg(gross_cap=0.5, cap_trim_mode="pro_rata"))
    assert len(proposals) == 2
    assert {p["instrument"] for p in proposals} == {"A", "B"}
    assert all(p["qty"] == -50.0 for p in proposals)


def test_net_cap_breach():
    e = exposures_for([{"symbol": "SPY", "qty": 300.0}], {"SPY": 500.0},
                      equity=100_000.0)
    # net = 1.5 of equity; cap 1.0 -> breach
    proposals, _ = exposure_cap_rule(e, cfg(net_cap=1.0))
    assert len(proposals) == 1
    assert proposals[0]["details"]["which"] == "net"


def test_caps_quiet_when_within():
    e = exposures_for([{"symbol": "SPY", "qty": 100.0}], {"SPY": 500.0},
                      equity=100_000.0)
    proposals, _ = exposure_cap_rule(e, cfg())
    assert proposals == []


def test_propose_hedges_runs_all_rules():
    ps, ms, c = demo_drift_breach(seed=7)
    e = compute_exposures(ps["positions"], ms["prices"], c)
    proposals, diagnostics = propose_hedges(e, c, ms)
    assert set(diagnostics) == {"delta_trim", "exposure_cap", "vol_regime"}
    assert any(p["rule_id"] == "delta_trim" for p in proposals)
