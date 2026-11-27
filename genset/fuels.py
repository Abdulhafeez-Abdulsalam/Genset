"""Fuel definitions and generator fuel-use maths."""

import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MJ_PER_KWH = 3.6


@dataclass(frozen=True)
class Fuel:
    key: str
    name: str
    unit: str
    unit_long: str
    energy_mj_per_unit: float
    full_load_efficiency: float
    approximate: bool
    source: str
    source_url: str


@dataclass(frozen=True)
class FuelData:
    fuels: dict[str, Fuel]
    no_load_fraction: float
    power_factor: float
    mmbtu_per_scm: float


def load_fuel_data(path: Path = DATA_DIR / "fuels.json") -> FuelData:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    fuels = {
        key: Fuel(
            key=key,
            name=f["name"],
            unit=f["unit"],
            unit_long=f["unit_long"],
            energy_mj_per_unit=float(f["energy_mj_per_unit"]),
            full_load_efficiency=float(f["full_load_efficiency"]),
            approximate=bool(f["approximate"]),
            source=f["source"],
            source_url=f.get("source_url", ""),
        )
        for key, f in raw["fuels"].items()
    }
    return FuelData(
        fuels=fuels,
        no_load_fraction=float(raw["no_load_fraction"]),
        power_factor=float(raw["power_factor"]),
        mmbtu_per_scm=float(raw["mmbtu_per_scm"]),
    )


def rated_kw(kva: float, power_factor: float = 0.8) -> float:
    """Generator real-power rating from its kVA rating."""
    return kva * power_factor


def full_load_rate(energy_mj_per_unit: float, efficiency: float) -> float:
    """Fuel per kWh at full load, in the fuel's unit."""
    return MJ_PER_KWH / (efficiency * energy_mj_per_unit)


def fuel_curve(energy_mj_per_unit: float, efficiency: float, no_load_fraction: float) -> tuple[float, float]:
    """Return (a, b): fuel per hour = a x rated kW + b x output kW."""
    total = full_load_rate(energy_mj_per_unit, efficiency)
    return no_load_fraction * total, (1 - no_load_fraction) * total


def hourly_fuel(a: float, b: float, rated: float, output_kw: float) -> float:
    """Fuel burned per running hour. Output above the rating is capped at the rating."""
    return a * rated + b * min(max(output_kw, 0.0), rated)


def daily_fuel_estimate(
    *,
    kva: float,
    avg_load_kw: float,
    hours: float,
    energy_mj_per_unit: float,
    efficiency: float,
    no_load_fraction: float,
    power_factor: float = 0.8,
) -> float:
    """Daily fuel use estimated from generator size and average load."""
    rated = rated_kw(kva, power_factor)
    a, b = fuel_curve(energy_mj_per_unit, efficiency, no_load_fraction)
    return hourly_fuel(a, b, rated, avg_load_kw) * hours


def daily_fuel_from_purchases(amount: float, per: str, in_naira: bool, price: float) -> float:
    """Daily fuel use from what the user buys. `per` is 'day' or 'week'."""
    if in_naira and price <= 0:
        return 0.0
    units = amount / price if in_naira else amount
    return units / 7 if per == "week" else units


def usd_per_mmbtu_to_naira_per_scm(usd_per_mmbtu: float, naira_per_usd: float, mmbtu_per_scm: float) -> float:
    return usd_per_mmbtu * naira_per_usd * mmbtu_per_scm
