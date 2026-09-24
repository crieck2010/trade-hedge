"""Tests for exposures.py."""

from trade_hedge.exposures import compute_exposures
from trade_hedge.presets import DEFAULT_CONFIG

POSITIONS = [
    {"symbol": "AAPL", "qty": 100.0},
    {"symbol": "MSFT", "qty": -50.0},
]
PRICES = {"AAPL": 200.0, "MSFT": 400.0}


def cfg(**kw):
    c = dict(DEFAULT_CONFIG)
    c.update(kw)
    return c


def test_net_delta_dollars():
    e = compute_exposures(POSITIONS, PRICES, cfg(equity=100_000.0))
    # 100*200 - 50*400 = 0
    assert e["net_delta_dollars"] == 0.0


def test_beta_adjustment():
    e = compute_exposures(POSITIONS, PRICES,
                          cfg(equity=100_000.0, betas={"AAPL": 1.5, "MSFT": 0.5}))
    # 100*200*1.5 - 50*400*0.5 = 30000 - 10000 = 20000
    assert e["net_delta_dollars_beta_adj"] == 20_000.0
    assert e["net_delta_frac_beta_adj"] == 0.2


def test_beta_default_one():
    e = compute_exposures(POSITIONS, PRICES, cfg(equity=100_000.0))
    assert e["per_symbol"]["AAPL"]["beta"] == 1.0
    assert e["net_delta_dollars_beta_adj"] == e["net_delta_dollars"]


def test_gross_and_fractions():
    e = compute_exposures(POSITIONS, PRICES, cfg(equity=100_000.0))
    assert e["gross_dollars"] == 40_000.0
    assert e["gross_frac"] == 0.4
    assert e["net_frac"] == 0.0


def test_fractions_none_without_equity():
    e = compute_exposures(POSITIONS, PRICES, cfg(equity=None))
    assert e["gross_frac"] is None
    assert e["net_delta_frac_beta_adj"] is None
    # dollar exposures still work
    assert e["gross_dollars"] == 40_000.0


def test_herfindahl_concentration():
    # Single-name portfolio: HHI = 1.0, top-1 share = 1.0
    e = compute_exposures([{"symbol": "AAPL", "qty": 10.0}],
                          {"AAPL": 200.0}, cfg(equity=10_000.0))
    assert e["herfindahl"] == 1.0
    assert e["top_n_share"] == 1.0


def test_herfindahl_diversified():
    pos = [{"symbol": f"S{i}", "qty": 10.0} for i in range(4)]
    px = {f"S{i}": 100.0 for i in range(4)}
    e = compute_exposures(pos, px, cfg(equity=10_000.0))
    # four equal weights -> HHI = 4 * 0.25^2 = 0.25
    assert abs(e["herfindahl"] - 0.25) < 1e-12
    assert abs(e["top_n_share"] - 1.0) < 1e-12  # top-5 of 4 names


def test_missing_price_raises_naming_symbol():
    try:
        compute_exposures(POSITIONS, {"AAPL": 200.0}, cfg())
    except KeyError as exc:
        assert "MSFT" in str(exc)
    else:
        raise AssertionError("expected KeyError")
