# Genset

A Streamlit app that estimates the electricity tariff (₦/kWh) a diesel- or
gas-generator mini-grid must charge to recover its costs over a power purchase
agreement (PPA) term.

## Run it

You need Python 3.11 or later.

```bash
pip install -r requirements.txt
streamlit run genset_code.py
```

The app opens at http://localhost:8501.

In GitHub Codespaces or a VS Code Dev Container, the app installs its
dependencies and starts automatically (see `.devcontainer/devcontainer.json`).

## Inputs

| Input | Unit |
|---|---|
| Average load | kW |
| Peak load | kW |
| Generator running hours per day | hours |
| PPA term | years |
| Fuel type | diesel or gas |
| Generator cost | ₦ |
| Installation cost | ₦ |
| Monthly logistics cost | ₦ |
| Monthly operation and maintenance cost | ₦ |
| Fuel price | ₦ per litre (diesel) or per kg (gas) |
| Annual fuel price escalation | % |

## How it calculates the tariff

1. **Daily energy** = average load × running hours.
2. **Load factor** = average load ÷ peak load (shown for reference).
3. **Fuel use** = daily energy × fuel rate: 0.3 L/kWh for diesel, 0.2 kg/kWh
   for gas. Monthly use assumes 30.4 days; annual use assumes 365 days.
4. **CAPEX** = generator cost + installation cost.
5. **Fixed running cost** = (O&M + logistics) × 12, for each year of the PPA.
6. **Fuel cost** for year *n* = fuel price × (1 + escalation)^(n − 1) × annual
   fuel use.
7. **Tariff** = (CAPEX + total fixed running cost + total fuel cost) ÷ total
   kWh over the PPA term.

## Outputs

- Daily energy delivered and load factor
- Daily, monthly and annual fuel consumption
- Estimated tariff in ₦/kWh
- Fuel cost for each year, and the total over the PPA term

## Limitations

- The tariff covers costs only. It has no discounting, financing cost, profit
  margin or tax.
- Generator replacement or overhaul during the PPA term is not included.
- Fuel rates are fixed and do not change with how heavily the generator is
  loaded.
