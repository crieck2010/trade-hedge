"""Tests for safety.py kill-switch logic."""

import datetime

from trade_hedge.presets import DEFAULT_CONFIG
from trade_hedge.safety import safety_check

NOW = datetime.datetime(2026, 9, 24, 12, 0, tzinfo=datetime.timezone.utc)


def cfg(**kw):
    c = dict(DEFAULT_CONFIG)
    c.update(kw)
    return c


def healthy_portfolio(**kw):
    base = {"positions": [{"symbol": "SPY", "qty": 100.0}],
            "equity": 100_000.0, "peak_equity": 105_000.0}
    base.update(kw)
    return base


def fresh_market(**kw):
    base = {"prices": {"SPY": 500.0}, "as_of": NOW.isoformat()}
    base.update(kw)
    return base


def test_healthy_state_not_halted():
    r = safety_check(healthy_portfolio(), fresh_market(), cfg(), now=NOW)
    assert r["halted"] is False
    assert r["alerts"] == []
    assert abs(r["drawdown"] - (1 - 100_000 / 105_000)) < 1e-12


def test_drawdown_breach_halts():
    p = healthy_portfolio(equity=85_000.0, peak_equity=100_000.0)  # 15% dd
    r = safety_check(p, fresh_market(), cfg(max_drawdown=0.10), now=NOW)
    assert r["halted"] is True
    assert any("drawdown" in a for a in r["alerts"])


def test_drawdown_at_limit_does_not_halt():
    p = healthy_portfolio(equity=90_000.0, peak_equity=100_000.0)  # exactly 10%
    r = safety_check(p, fresh_market(), cfg(max_drawdown=0.10), now=NOW)
    assert r["halted"] is False


def test_stale_data_halts():
    old = (NOW - datetime.timedelta(hours=3)).isoformat()
    r = safety_check(healthy_portfolio(), fresh_market(as_of=old), cfg(), now=NOW)
    assert r["halted"] is True
    assert any("old" in a for a in r["alerts"])
    assert r["stale_minutes"] > 170


def test_missing_timestamp_halts():
    m = fresh_market()
    del m["as_of"]
    r = safety_check(healthy_portfolio(), m, cfg(), now=NOW)
    assert r["halted"] is True


def test_missing_price_halts_naming_symbol():
    p = {"positions": [{"symbol": "SPY", "qty": 100.0},
                       {"symbol": "XYZ", "qty": 10.0}],
         "equity": 100_000.0, "peak_equity": 100_000.0}
    r = safety_check(p, fresh_market(), cfg(), now=NOW)
    assert r["halted"] is True
    assert any("XYZ" in a for a in r["alerts"])


def test_epoch_timestamp_accepted():
    m = fresh_market(as_of=NOW.timestamp())
    r = safety_check(healthy_portfolio(), m, cfg(), now=NOW)
    assert r["halted"] is False
