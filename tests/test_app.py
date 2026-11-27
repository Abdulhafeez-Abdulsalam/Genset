"""Run the Streamlit app headlessly for every fuel and fuel-use mode."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "genset_code.py")
FUELS = ["Diesel (AGO)", "Petrol (PMS)", "LPG (cooking gas)", "CNG (compressed natural gas)", "Pipeline natural gas"]
MODES = ["Estimate from generator size and load", "I know how much fuel I buy", "Fixed amount per kWh"]


def run_app():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception, at.exception
    return at


def metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


def naira_value(text):
    return float(text.replace("₦", "").replace("/kWh", "").replace(",", "").strip())


@pytest.mark.parametrize("fuel", FUELS)
@pytest.mark.parametrize("mode", MODES)
def test_every_fuel_and_mode_runs(fuel, mode):
    at = run_app()
    next(s for s in at.selectbox if s.label == "Fuel").select(fuel).run()
    next(r for r in at.radio if r.label == "How should fuel use be worked out?").set_value(mode).run()
    if mode == "I know how much fuel I buy":
        next(n for n in at.number_input if n.label == "Amount bought").set_value(50.0).run()
    assert not at.exception, at.exception
    tariff = naira_value(metric(at, "Break-even tariff over 10 years"))
    fuel_per_kwh = naira_value(metric(at, "Fuel cost per kWh (year 1)"))
    assert tariff > 0
    assert tariff == pytest.approx(fuel_per_kwh, rel=1e-6)  # other costs are ₦0 by default


def test_diesel_estimate_is_sensible():
    at = run_app()
    # 100 kW average for 8 h on a 200 kVA (160 kW) diesel generator
    fuel_per_day = float(metric(at, "Fuel use per day (L)").replace(",", ""))
    assert 230 < fuel_per_day < 300
    assert metric(at, "Energy delivered per day") == "800 kWh"


def test_warnings_for_bad_inputs():
    at = run_app()
    next(n for n in at.number_input if n.label == "Average load (kW)").set_value(200.0).run()
    next(n for n in at.number_input if n.label.startswith("Generator size")).set_value(100.0).run()
    texts = " ".join(w.value for w in at.warning)
    assert "Average load is higher than peak load" in texts
    assert "more than a 100 kVA generator can supply" in texts
