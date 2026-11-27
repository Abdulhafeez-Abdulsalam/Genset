import pytest

from genset import fuels as F


@pytest.fixture(scope="module")
def data():
    return F.load_fuel_data()


def test_five_fuels_with_expected_units(data):
    assert {k: f.unit for k, f in data.fuels.items()} == {
        "diesel": "L", "petrol": "L", "lpg": "kg", "cng": "scm", "pipeline_gas": "scm",
    }
    for fuel in data.fuels.values():
        assert fuel.source, f"{fuel.key} needs a source"
        assert 0 < fuel.full_load_efficiency < 0.6


def test_diesel_curve_reproduces_homer_example(data):
    """HOMER manual: a 50 kW generator uses 8.48 L/hr at 25 kW and 15.3 L/hr at 50 kW."""
    d = data.fuels["diesel"]
    a, b = F.fuel_curve(d.energy_mj_per_unit, d.full_load_efficiency, data.no_load_fraction)
    assert a == pytest.approx(0.033, abs=0.001)
    assert b == pytest.approx(0.273, abs=0.001)
    assert F.hourly_fuel(a, b, 50, 25) == pytest.approx(8.48, abs=0.05)
    assert F.hourly_fuel(a, b, 50, 50) == pytest.approx(15.3, abs=0.05)


def test_full_load_diesel_rate_close_to_old_fixed_rate(data):
    d = data.fuels["diesel"]
    assert F.full_load_rate(d.energy_mj_per_unit, d.full_load_efficiency) == pytest.approx(0.306, abs=0.002)


def test_output_is_capped_at_rating():
    assert F.hourly_fuel(0.03, 0.27, 50, 80) == F.hourly_fuel(0.03, 0.27, 50, 50)


def test_part_load_uses_more_fuel_per_kwh(data):
    d = data.fuels["diesel"]
    common = dict(kva=62.5, hours=1, energy_mj_per_unit=d.energy_mj_per_unit,
                  efficiency=d.full_load_efficiency, no_load_fraction=data.no_load_fraction)
    full = F.daily_fuel_estimate(avg_load_kw=50, **common) / 50
    quarter = F.daily_fuel_estimate(avg_load_kw=12.5, **common) / 12.5
    assert quarter > full * 1.2


def test_rated_kw():
    assert F.rated_kw(200) == 160


def test_daily_fuel_from_purchases():
    assert F.daily_fuel_from_purchases(70, "week", False, 0) == 10
    assert F.daily_fuel_from_purchases(30, "day", False, 0) == 30
    assert F.daily_fuel_from_purchases(17_300, "day", True, 1730) == pytest.approx(10)
    assert F.daily_fuel_from_purchases(1000, "day", True, 0) == 0


def test_gas_price_conversion():
    assert F.usd_per_mmbtu_to_naira_per_scm(3.39, 1369.5, 0.0354) == pytest.approx(164.35, abs=0.01)
