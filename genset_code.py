import streamlit as st

st.title("Mini-Grid Project Financial Model")
load_factor = 0.8
days_monthly = 30.4

avg_load = st.number_input('Enter the average load (kW):', min_value=0.0, value=100.0)
peak_load = st.number_input('Enter the peak load (kW):', min_value=0.0, value=150.0)
operating_hrs = st.number_input('Enter the genset running hours (hrs):', min_value=0.0, value=8.0)
ppa_lifetime = st.number_input('Enter the number of PPA years (years):', min_value=1, value=10)

daily_energy_kwh = peak_load * load_factor * operating_hrs

fuel_type = st.selectbox("Select fuel type:", ["diesel", "gas"])
fuel_consumption_rates = {
    "diesel": 0.3,  # liters per kWh
    "gas": 0.2     # kg per kWh
}
consumption_rate = fuel_consumption_rates[fuel_type]
gen_cost = st.number_input(f"Enter total cost of {fuel_type} generator (₦):", min_value=0.0)
logistics_cost = st.number_input(f"Enter monthly logistics cost (₦):", min_value=0.0)
om_monthly_cost = st.number_input(f"Enter monthly operation & maintenance cost (₦):", min_value=0.0)
installation_cost = st.number_input(f"Enter installation cost (₦):", min_value=0.0)
fuel_price = st.number_input(f"Enter {fuel_type} price per unit (₦):", min_value=0.0)
fuel_escalation_rate = st.number_input(f"Enter annual escalation rate (%)", min_value=0.0) / 100

daily_fuel_consumption = daily_energy_kwh * consumption_rate
monthly_fuel_consumption = daily_fuel_consumption * days_monthly
annual_fuel_consumption = daily_fuel_consumption * 365
capex = gen_cost + installation_cost
annual_opex_fixed = (om_monthly_cost + logistics_cost) * 12
annual_fuel_costs = []
for year in range(1, ppa_lifetime + 1):
    price = fuel_price * ((1 + fuel_escalation_rate) ** (year - 1))
    cost = price * annual_fuel_consumption
    annual_fuel_costs.append(cost)
total_fuel_cost = sum(annual_fuel_costs)

total_cost_over_ppa_years = capex + (annual_opex_fixed * ppa_lifetime) + total_fuel_cost
total_kwh = daily_energy_kwh * 365 * ppa_lifetime
tariff = total_cost_over_ppa_years / total_kwh if total_kwh > 0 else 0

unit = "liters" if fuel_type == "diesel" else "kg"
st.subheader("Results")
st.write(f"**Daily Fuel Consumption**: {daily_fuel_consumption:.2f} {unit}")
st.write(f"**Monthly Fuel Consumption**: {monthly_fuel_consumption:.2f} {unit}")
st.write(f"**Annual Fuel Consumption**: {annual_fuel_consumption:.2f} {unit}")

st.write(f"**Your Estimated Tariff (including escalation)**: ₦{tariff:,.2f} per kWh")

st.subheader("Escalated Annual Fuel Costs")
for i, cost in enumerate(annual_fuel_costs, 1):
    st.write(f"Year {i}: ₦{cost:,.2f}")
st.write(f"**Total Escalated Fuel Cost Over {ppa_lifetime} Years**: ₦{total_fuel_cost:,.2f}")
