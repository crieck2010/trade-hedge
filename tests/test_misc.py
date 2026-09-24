"""Tests for adapters.py (fail-soft with no siblings installed),
demo determinism, presets, and the CLI."""

import json
import subprocess
import sys

import pytest

from trade_hedge.adapters import (
    betas_from_factors,
    positions_from_paper,
    prices_from_data,
    proposals_to_paper_payloads,
    vol_from_volforecast,
)
from trade_hedge.demo import demo_drift_breach, demo_stale_data, demo_vol_regime_shift
from trade_hedge.presets import DEFAULT_CONFIG, PRESETS, describe_presets
from trade_hedge.scheduler import run_cycle, LoopState


# --- adapters: fail-soft ------------------------------------------------------

def test_positions_from_paper_raises_helpful_error():
    with pytest.raises(RuntimeError, match="trade-paper"):
        positions_from_paper()


def test_prices_from_data_raises_helpful_error():
    with pytest.raises(RuntimeError, match="trade-data-equities"):
        prices_from_data(["AAPL"])


def test_prices_from_data_bad_provider():
    with pytest.raises(ValueError, match="unknown provider"):
        prices_from_data(["AAPL"], provider="nope")


def test_vol_from_volforecast_falls_back_internally():
    import random
    rng = random.Random(11)
    rets = [rng.gauss(0.0, 0.02) for _ in range(100)]
    v = vol_from_volforecast(rets)
    assert v is not None and v > 0.2  # ~32% ann


def test_vol_from_volforecast_none_on_short():
    assert vol_from_volforecast([0.01]) is None


def test_betas_from_factors_falls_back_to_ones():
    betas = betas_from_factors(["AAPL", "MSFT"])
    assert betas == {"AAPL": 1.0, "MSFT": 1.0}


def test_proposals_to_paper_payloads_shape():
    proposals = [{"action": "hedge_delta", "instrument": "SPY", "qty": -10.0,
                  "reason": "r", "expected_delta_impact": -5000.0,
                  "rule_id": "delta_trim", "details": {}}]
    payloads = proposals_to_paper_payloads(proposals, run_id="abc")
    assert payloads[0]["kind"] == "hedge_proposal"
    assert payloads[0]["requires_user_approval"] is True
    assert payloads[0]["source"] == "trade-hedge"
    assert payloads[0]["run_id"] == "abc"


# --- demo determinism ----------------------------------------------------------

def test_demos_deterministic():
    a = demo_drift_breach(seed=7)
    b = demo_drift_breach(seed=7)
    assert a[0] == b[0]
    assert a[1]["prices"] == b[1]["prices"]  # as_of is wall-clock by design
    assert a[2] == b[2]
    c = demo_vol_regime_shift(seed=7)
    d = demo_vol_regime_shift(seed=7)
    assert c[1]["portfolio_returns"] == d[1]["portfolio_returns"]
    s1 = demo_stale_data(seed=7)
    s2 = demo_stale_data(seed=7)
    # stale demos differ only by wall-clock timestamp; prices are deterministic
    assert s1[1]["prices"] == s2[1]["prices"]


def test_presets_structure():
    assert set(PRESETS) == {"conservative", "balanced", "aggressive"}
    assert PRESETS["balanced"] == DEFAULT_CONFIG
    assert PRESETS["conservative"]["gross_cap"] < PRESETS["aggressive"]["gross_cap"]
    rows = describe_presets()
    assert {r["name"] for r in rows} == set(PRESETS)


# --- CLI -----------------------------------------------------------------------

def run_cli(*argv):
    import os
    env = dict(os.environ)
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [sys.executable, "-m", "trade_hedge.cli", *argv],
        capture_output=True, text=True, cwd=".", env=env,
    )


def test_cli_propose_dry_run(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    r = run_cli("propose", "--demo", "drift", "--seed", "7")
    assert r.returncode == 0, r.stderr
    assert "DRY RUN" in r.stdout
    assert "delta_trim" in r.stdout


def test_cli_propose_submit():
    r = run_cli("propose", "--demo", "drift", "--seed", "7", "--submit",
                "--format", "json")
    assert r.returncode == 0, r.stderr
    payloads = json.loads(r.stdout[r.stdout.index("["):])
    assert payloads[0]["kind"] == "hedge_proposal"
    assert payloads[0]["requires_user_approval"] is True


def test_cli_stale_demo_halts():
    r = run_cli("propose", "--demo", "stale", "--seed", "7")
    assert r.returncode == 0, r.stderr
    assert "halted: True" in r.stdout
    assert "proposals: 0" in r.stdout


def test_cli_exposures_json():
    r = run_cli("exposures", "--demo", "drift", "--seed", "7", "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["exposures"]["n_positions"] == 5


def test_cli_presets():
    r = run_cli("presets")
    assert r.returncode == 0, r.stderr
    assert "conservative" in r.stdout


def test_cli_license():
    r = run_cli("license")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["valid"] is True
