# Genset

A Streamlit app that works out what generator power costs per kWh in Nigeria.
It shows the flat tariff (₦/kWh) that recovers every cost over a contract term,
and compares that with the grid tariff for your DisCo and band. It supports
diesel, petrol, LPG, CNG and pipeline natural gas.

## Run it

You need Python 3.11 or later.

```bash
pip install -r requirements.txt
streamlit run genset_code.py
```

The app opens at http://localhost:8501.

In GitHub Codespaces or a VS Code Dev Container, the app installs its
dependencies and starts automatically (see `.devcontainer/devcontainer.json`).

## Project layout

| Path | What it holds |
|---|---|
| `genset_code.py` | The Streamlit interface only |
| `genset/model.py` | Energy, cost and tariff maths |
| `genset/fuels.py` | Fuel definitions and generator fuel-use maths |
| `genset/prices.py` | Loads and checks `data/prices.json` |
| `data/fuels.json` | Fuel energy content, efficiency and sources |
| `data/prices.json` | Reference prices with source and date for each |
| `scripts/update_prices.py` | Reads new NERC tariff orders into `data/prices.json` |
| `.github/workflows/update-prices.yml` | Runs the update weekly and opens a pull request |
| `tests/` | pytest tests |

## Fuels

| Fuel | Unit |
|---|---|
| Diesel (AGO) | litres |
| Petrol (PMS) | litres |
| LPG (cooking gas) | kg |
| CNG | standard cubic metres (scm) |
| Pipeline natural gas | scm, or US$/MMBtu with an exchange rate |

## How fuel use is worked out

Pick one of three ways:

1. **Estimate from generator size and load.** Fuel per hour = a × rated kW +
   b × output kW, where rated kW = kVA × 0.8. A generator burns fuel even at
   no load, so it uses more fuel per kWh when lightly loaded.
   - Diesel values reproduce the worked example in the HOMER manual: a 50 kW
     generator using 8.48 L/hr at 25 kW and 15.3 L/hr at full load.
   - Petrol, LPG and gas values come from each fuel's energy content and a
     typical engine efficiency. They are approximate, and the app lets you edit
     them; use your generator's spec sheet if you have it.
2. **I know how much fuel I buy.** Enter what you buy per day or week, in the
   fuel's unit or in naira. This is the most accurate option.
3. **Fixed amount per kWh.** One rate for every kWh, as in the original model.

## How the tariff is calculated

1. **Daily energy** = average load × running hours.
2. **Fuel cost** for year *n* = daily fuel × 365 × price × (1 + yearly rise)^(n − 1).
3. **Upfront cost** = generator cost + installation cost.
4. **Fixed running cost** = (servicing + logistics) × 12, for each year.
5. **Tariff** = (upfront + all fixed running costs + all fuel costs) ÷ total kWh
   over the term.

## Reference prices

Every price field starts from `data/prices.json` and shows its source and date.
Users can always type their own price. The app warns when a price is more than
60 days old.

| Price | How it is kept current |
|---|---|
| Grid tariffs, Bands A–E for each DisCo | Automatic: NERC monthly supplementary orders |
| Gas price for power plants (US$/MMBtu) and ₦/US$ rate | Automatic: the same NERC orders |
| Diesel, petrol, LPG and CNG retail prices | By hand: edit `data/prices.json` |

NERC's order PDFs draw their tables as shapes, not text, so the script reads
them with OCR (tesseract). It checks every value against expected ranges and
skips any order that fails. Fuel retail prices are manual for now: the NBS
website refuses automated connections, and NMDPRA does not publish retail prices
on its website.

NERC sets tariffs only for states that do not yet regulate their own electricity
market. Customers in other states should enter the rate on their bill.

### Weekly update

`.github/workflows/update-prices.yml` runs every Monday (or by hand from the
Actions tab). It opens or updates a pull request named "Update reference prices
from NERC orders", with a table of what changed and links to each PDF. Check the
figures against the PDFs before merging. For the workflow to open pull requests,
enable **Settings → Actions → General → Allow GitHub Actions to create and
approve pull requests**.

To run the update yourself:

```bash
sudo apt-get install tesseract-ocr
pip install -r requirements-dev.txt
python scripts/update_prices.py --dry-run
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Limitations

- The tariff covers costs only: no discounting, financing cost, profit margin or
  tax.
- Generator overhauls and replacement, downtime, and demand growth are not
  included.
- Grid comparison assumes the grid supplies the same hours as the generator.
