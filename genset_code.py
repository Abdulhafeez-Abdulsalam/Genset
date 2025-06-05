import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# Page title
st.title("Mini-Grid Project Financial Model")

# Constants
gen_maxloading = 0.75
load_factor = 0.8
power_factor = 0.8
days_monthly = 30.4

# User Inputs
avg_load = st.number_input('Enter the average load (kW):', min_value=0.0, value=100.0)
peak_load = st.number_input('Enter the peak load (kW):', min_value=0.0, value=150.0)
operating_hrs = st.number_input('Enter the genset running hours (hrs):', min_value=0.0, value=8.0)
ppa_lifetime = st.number_input('Enter the number of PPA years (years):', min_value=1, value=10)

# Calculate daily energy output
daily_energy_kwh = peak_load * load_factor * operating_hrs

# Fuel selection
fuel_type = st.selectbox("Select fuel type:", ["diesel", "gas"])
fuel_consumption_rates = {
    "diesel": 0.3,  # liters per kWh
    "gas": 0.2     # kg per kWh
}
consumption_rate = fuel_consumption_rates[fuel_type]

# CAPEX & OPEX inputs
gen_cost = st.number_input(f"Enter total cost of {fuel_type} generator (₦):", min_value=0.0)
logistics_cost = st.number_input(f"Enter monthly logistics cost (₦):", min_value=0.0)
om_monthly_cost = st.number_input(f"Enter monthly operation & maintenance cost (₦):", min_value=0.0)
installation_cost = st.number_input(f"Enter installation cost (₦):", min_value=0.0)

# Fuel price and escalation
fuel_price = st.number_input(f"Enter {fuel_type} price per unit (₦):", min_value=0.0)
fuel_escalation_rate = st.number_input(f"Enter annual escalation rate (%)", min_value=0.0) / 100

# Calculations
daily_fuel_consumption = daily_energy_kwh * consumption_rate
monthly_fuel_consumption = daily_fuel_consumption * days_monthly
annual_fuel_consumption = daily_fuel_consumption * 365

daily_fuel_cost = daily_fuel_consumption * fuel_price
monthly_fuel_cost = daily_fuel_cost * days_monthly
annual_fuel_cost = daily_fuel_cost * 365

capex = gen_cost + installation_cost + logistics_cost
monthly_opex = monthly_fuel_cost + om_monthly_cost
total_cost_over_ppa_years = capex + (monthly_opex * 12 * ppa_lifetime)

tariff = total_cost_over_ppa_years / (daily_energy_kwh * 365 * ppa_lifetime)

unit = "liters" if fuel_type == "diesel" else "kg"

# Output Results
st.subheader("Results")
st.write(f"**Daily Fuel Consumption**: {daily_fuel_consumption:.2f} {unit}")
st.write(f"**Monthly Fuel Consumption**: {monthly_fuel_consumption:.2f} {unit}")
st.write(f"**Annual Fuel Consumption**: {annual_fuel_consumption:.2f} {unit}")

st.write(f"**Daily Fuel Cost**: ₦{daily_fuel_cost:,.2f}")
st.write(f"**Monthly Fuel Cost**: ₦{monthly_fuel_cost:,.2f}")
st.write(f"**Annual Fuel Cost**: ₦{annual_fuel_cost:,.2f}")
st.write(f"**Your Estimated Tariff**: ₦{tariff:,.2f} per kWh")

# Escalated fuel prices and plotting
annual_prices = []
for year in range(1, ppa_lifetime + 1):
    price = fuel_price * ((1 + fuel_escalation_rate) ** (year - 1))
    annual_prices.append(price)

total_fuel_cost = sum(annual_prices)

st.subheader("Annual Fuel Price Escalation")
for i, price in enumerate(annual_prices, 1):
    st.write(f"Year {i}: ₦{price:.2f}")
st.write(f"**Total Fuel Price Over {ppa_lifetime} Years**: ₦{total_fuel_cost:,.2f}")

# Plot
fig, ax = plt.subplots()
ax.plot(range(1, ppa_lifetime + 1), annual_prices, marker='o', linestyle='-', color='blue')
ax.set_title(f"Annual {fuel_type.capitalize()} Price Over {ppa_lifetime} Years")
ax.set_xlabel("Year")
ax.set_ylabel("Fuel Price (₦)")
ax.grid(True)
st.pyplot(fig)
