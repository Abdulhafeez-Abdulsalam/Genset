import pytest

from genset import model as M


def sample_result(daily_fuel=240.0):
    return M.project_result(
        daily_energy=M.daily_energy_kwh(100, 8),
        daily_fuel=daily_fuel,
        fuel_price=1200,
        fuel_escalation=0.10,
        years=10,
        generator_cost=15_000_000,
        installation_cost=2_000_000,
        monthly_om=300_000,
        monthly_logistics=200_000,
    )


def test_daily_energy_uses_average_load():
    assert M.daily_energy_kwh(100, 8) == 800


def test_load_factor():
    assert M.load_factor(100, 150) == pytest.approx(2 / 3)
    assert M.load_factor(100, 0) == 0


def test_escalated_costs_compound():
    assert M.escalated_annual_costs(100, 0.1, 3) == pytest.approx([100, 110, 121])


def test_regression_matches_earlier_sample_run():
    """Same inputs as the earlier app run: diesel at a fixed 0.3 L/kWh gave ₦600.12/kWh."""
    r = sample_result(daily_fuel=800 * 0.3)
    assert r.capex == 17_000_000
    assert r.annual_fixed_cost == 6_000_000
    assert r.annual_fuel_costs[0] == pytest.approx(105_120_000)
    assert r.annual_fuel_costs[-1] == pytest.approx(247_867_461.28, abs=0.01)
    assert r.total_fuel_cost == pytest.approx(1_675_342_074.06, abs=0.01)
    assert r.tariff == pytest.approx(600.12, abs=0.005)
    assert r.first_year_fuel_cost_per_kwh == pytest.approx(360)


def test_zero_energy_gives_zero_tariff():
    r = M.project_result(daily_energy=0, daily_fuel=0, fuel_price=1000, fuel_escalation=0, years=5,
                         generator_cost=1, installation_cost=0, monthly_om=0, monthly_logistics=0)
    assert r.tariff == 0
    assert r.first_year_fuel_cost_per_kwh == 0
