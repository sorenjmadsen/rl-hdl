"""Checks for the LP resource-allocation optimizer. Skips if ortools is absent."""
import pytest

pytest.importorskip("ortools")

from cologic.optimize import Resource, minimize_power

RES = [
    Resource("pe_slow", power=1.0, area=2.0, throughput=2.0),  # 0.5 mW per MAC/cyc
    Resource("pe_fast", power=4.0, area=3.0, throughput=5.0),  # 0.8 mW per MAC/cyc
]


def test_picks_most_power_efficient_when_area_is_free():
    sol = minimize_power(RES, target_throughput=64.0, area_budget=1000.0)
    assert sol is not None
    assert sol["power_mw"] == pytest.approx(32.0)        # 32 slow PEs
    assert sol["allocation"]["pe_fast"] == pytest.approx(0.0)


def test_tight_area_forces_denser_pe_and_raises_power():
    sol = minimize_power(RES, target_throughput=64.0, area_budget=50.0)
    assert sol is not None and sol["power_mw"] > 32.0


def test_infeasible_target_returns_none():
    assert minimize_power(RES, target_throughput=1e9, area_budget=10.0) is None
