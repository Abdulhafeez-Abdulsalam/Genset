"""Streamlit UI for the generator power cost calculator. All maths lives in genset/."""

import streamlit as st

from genset import fuels as F
from genset import model as M
from genset.prices import PriceEntry, grid_tariffs, load_prices

BAND_HOURS = {"A": 20, "B": 16, "C": 12, "D": 8, "E": 4}  # minimum supply hours a day, per NERC orders

st.set_page_config(page_title="Generator Power Cost", page_icon="⚡")


@st.cache_data
def reference_data():
    return F.load_fuel_data(), load_prices()


fuel_data, prices = reference_data()


def naira(value: float, decimals: int = 0) -> str:
    return f"₦{value:,.{decimals}f}"


def show_source(entry: PriceEntry) -> None:
    """Caption under an input that starts from a reference price."""
    st.caption(
        f"Starts at {entry.value:,.2f} {entry.unit}: {entry.label}, {entry.region}. "
        f"As of {entry.as_of:%d %b %Y}, [{entry.source_name}]({entry.source_url})."
        + (f" {entry.note}" if entry.note else "")
    )
    if not entry.primary_source:
        st.caption("Unconfirmed: from news reports, not an official source. Use the price you actually pay.")
    if entry.is_stale():
        if entry.method == "nerc_ocr":
            st.warning(f"This comes from the latest NERC order found, which took effect {entry.age_days()} days ago. "
                       "Check your bill in case the tariff has changed since.")
        else:
            st.warning(f"This reference price is {entry.age_days()} days old. Check the current price before relying on it.")


st.title("Generator Power Cost Calculator")
st.write(
    "Work out what generator power costs per kWh, the flat tariff that recovers every cost "
    "over a contract term, and how that compares with grid electricity."
)

# ---------- 1. Demand ----------
st.header("1. Electricity demand")
avg_load = st.number_input("Average load (kW)", min_value=0.0, value=100.0,
                           help="The typical power drawn while the generator runs.")
peak_load = st.number_input("Peak load (kW)", min_value=0.0, value=150.0,
                            help="The highest power drawn at any moment.")
operating_hrs = st.number_input("Generator running hours per day", min_value=0.0, max_value=24.0, value=8.0)
years = st.number_input("Years to plan for (for example, the power purchase agreement term)",
                        min_value=1, max_value=40, value=10)
if avg_load > peak_load:
    st.warning("Average load is higher than peak load. Check your inputs.")

daily_energy = M.daily_energy_kwh(avg_load, operating_hrs)

# ---------- 2. Generator and fuel ----------
st.header("2. Generator and fuel")
fuel_key = st.selectbox("Fuel", list(fuel_data.fuels), format_func=lambda k: fuel_data.fuels[k].name)
fuel = fuel_data.fuels[fuel_key]
unit = fuel.unit

kva = st.number_input("Generator size (kVA, from the nameplate)", min_value=0.0, value=200.0, step=5.0)
rated = F.rated_kw(kva, fuel_data.power_factor)
if kva > 0 and peak_load > rated:
    st.warning(
        f"Peak load ({peak_load:,.0f} kW) is more than a {kva:,.0f} kVA generator can supply "
        f"(about {rated:,.0f} kW at a {fuel_data.power_factor} power factor)."
    )

# Fuel price
if fuel_key == "pipeline_gas":
    gas_unit = st.radio("Gas price is quoted in", ["US$ per MMBtu", "₦ per scm"], horizontal=True)
    if gas_unit == "US$ per MMBtu":
        gas_ref, fx_ref = prices.get("pipeline_gas_usd_mmbtu"), prices.get("naira_per_usd")
        usd = st.number_input("Gas price (US$ per MMBtu)", min_value=0.0, step=0.1,
                              value=gas_ref.value if gas_ref else 3.0)
        if gas_ref:
            show_source(gas_ref)
        fx = st.number_input("Exchange rate (₦ per US$)", min_value=0.0, step=10.0,
                             value=fx_ref.value if fx_ref else 1400.0)
        if fx_ref:
            show_source(fx_ref)
        fuel_price = F.usd_per_mmbtu_to_naira_per_scm(usd, fx, fuel_data.mmbtu_per_scm)
        st.caption(f"That is {naira(fuel_price, 2)} per scm, using {fuel_data.mmbtu_per_scm} MMBtu per scm (approximate).")
    else:
        fuel_price = st.number_input("Gas price (₦ per scm)", min_value=0.0, value=0.0, step=10.0)
else:
    ref = prices.get(fuel_key)
    fuel_price = st.number_input(f"{fuel.name} price (₦ per {unit})", min_value=0.0, step=10.0,
                                 value=ref.value if ref else 0.0, key=f"price_{fuel_key}")
    if ref:
        show_source(ref)
fuel_escalation = st.number_input("Expected yearly rise in fuel price (%)", min_value=0.0, value=0.0) / 100

# Fuel use
mode = st.radio(
    "How should fuel use be worked out?",
    ["Estimate from generator size and load", "I know how much fuel I buy", "Fixed amount per kWh"],
)
if mode == "Estimate from generator size and load":
    with st.expander("Fuel-use assumptions" + (" (approximate)" if fuel.approximate else "")):
        efficiency = st.number_input("Full-load efficiency (%)", min_value=1.0, max_value=60.0,
                                     value=fuel.full_load_efficiency * 100, key=f"eff_{fuel_key}") / 100
        energy = st.number_input(f"Energy content (MJ per {unit})", min_value=1.0,
                                 value=fuel.energy_mj_per_unit, key=f"mj_{fuel_key}")
        st.caption(f"Source: {fuel.source}" + (f" ([link]({fuel.source_url}))" if fuel.source_url else ""))
        st.caption("Replace these with your generator's spec sheet figures if you have them.")
    if kva <= 0:
        st.error("Enter the generator size to estimate fuel use.")
    daily_fuel = F.daily_fuel_estimate(
        kva=kva, avg_load_kw=avg_load, hours=operating_hrs, energy_mj_per_unit=energy,
        efficiency=efficiency, no_load_fraction=fuel_data.no_load_fraction, power_factor=fuel_data.power_factor,
    )
elif mode == "I know how much fuel I buy":
    col1, col2, col3 = st.columns(3)
    in_naira = col3.radio("Measured in", [fuel.unit_long, "naira (₦)"]) == "naira (₦)"
    amount = col1.number_input("Amount bought", min_value=0.0, value=0.0, step=10.0)
    per = col2.radio("Per", ["day", "week"])
    daily_fuel = F.daily_fuel_from_purchases(amount, per, in_naira, fuel_price)
else:
    default_rate = F.full_load_rate(fuel.energy_mj_per_unit, fuel.full_load_efficiency)
    rate = st.number_input(f"Fuel per kWh ({unit})", min_value=0.0, value=round(default_rate, 3),
                           step=0.01, format="%.3f", key=f"rate_{fuel_key}")
    daily_fuel = daily_energy * rate

# ---------- 3. Costs ----------
st.header("3. Other costs")
gen_cost = st.number_input("Generator purchase cost (₦)", min_value=0.0, step=100000.0)
installation_cost = st.number_input("Installation cost (₦)", min_value=0.0, step=100000.0)
logistics_cost = st.number_input("Monthly fuel delivery and logistics cost (₦)", min_value=0.0, step=10000.0)
om_monthly_cost = st.number_input("Monthly servicing and maintenance cost (₦)", min_value=0.0, step=10000.0)
if gen_cost + installation_cost + logistics_cost + om_monthly_cost == 0:
    st.info("Other costs are all ₦0, so the results below cover fuel only.")

result = M.project_result(
    daily_energy=daily_energy, daily_fuel=daily_fuel, fuel_price=fuel_price,
    fuel_escalation=fuel_escalation, years=int(years), generator_cost=gen_cost,
    installation_cost=installation_cost, monthly_om=om_monthly_cost, monthly_logistics=logistics_cost,
)

# ---------- Results ----------
st.header("Results")
col1, col2, col3 = st.columns(3)
col1.metric("Energy delivered per day", f"{daily_energy:,.0f} kWh")
col2.metric("Load factor (average ÷ peak)", f"{M.load_factor(avg_load, peak_load):.0%}")
col3.metric(f"Fuel use per day ({unit})", f"{daily_fuel:,.1f}")

col1, col2 = st.columns(2)
col1.metric("Fuel cost per kWh (year 1)", naira(result.first_year_fuel_cost_per_kwh, 2))
col2.metric(f"Break-even tariff over {result.years} years", naira(result.tariff, 2) + " /kWh")

st.markdown(
    f"**Fuel use:** {daily_fuel:,.1f} {unit} a day, {daily_fuel * M.DAYS_PER_MONTH:,.0f} {unit} a month, "
    f"{daily_fuel * M.DAYS_PER_YEAR:,.0f} {unit} a year.  \n"
    f"**Total cost over {result.years} years:** {naira(result.total_cost)} "
    f"(upfront {naira(result.capex)}, fixed running costs {naira(result.annual_fixed_cost * result.years)}, "
    f"fuel {naira(result.total_fuel_cost)})."
)

# Grid comparison
st.subheader("Compared with grid electricity")
grid = grid_tariffs(prices)
if grid:
    discos = list(grid)
    col1, col2 = st.columns(2)
    disco = col1.selectbox("Your electricity distribution company (DisCo)", discos,
                           index=discos.index("IE") if "IE" in discos else 0)
    bands = sorted(grid[disco])
    band = col2.selectbox("Your tariff band", bands,
                          format_func=lambda b: f"Band {b} (at least {BAND_HOURS[b]} hours a day)")
    entry = grid[disco][band]
    grid_price = st.number_input("Grid tariff to compare with (₦/kWh)", min_value=0.0,
                                 value=entry.value, key=f"grid_{disco}_{band}")
    show_source(entry)
    st.caption("Some states now set their own electricity tariffs. If yours does, use the rate on your bill or prepaid receipt.")
    if grid_price > 0 and result.tariff > 0:
        monthly_kwh = daily_energy * M.DAYS_PER_MONTH
        st.markdown(
            f"Generator power costs **{naira(result.tariff, 2)}/kWh** over the term, "
            f"**{result.tariff / grid_price:.1f} times** the grid tariff of {naira(grid_price, 2)}/kWh. "
            f"For {monthly_kwh:,.0f} kWh a month, grid power would cost about **{naira(monthly_kwh * grid_price)}** a month, "
            f"against an average of **{naira(monthly_kwh * result.tariff)}** a month from the generator."
        )
        st.caption("This assumes the grid supplies the same hours. In practice grid supply depends on your feeder.")
else:
    st.caption("No grid tariffs are loaded yet.")

with st.expander(f"Fuel cost by year ({fuel_escalation:.0%} yearly rise)"):
    st.table({"Year": [str(y) for y in range(1, result.years + 1)],
              "Fuel cost": [naira(c) for c in result.annual_fuel_costs]})
