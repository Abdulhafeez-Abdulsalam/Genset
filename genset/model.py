"""Energy, cost and tariff calculations. No Streamlit code here."""

from dataclasses import dataclass, field

DAYS_PER_MONTH = 30.4
DAYS_PER_YEAR = 365


def daily_energy_kwh(avg_load_kw: float, operating_hours: float) -> float:
    """Energy delivered per day: average load sustained over the running hours."""
    return avg_load_kw * operating_hours


def load_factor(avg_load_kw: float, peak_load_kw: float) -> float:
    """Average load divided by peak load (0 when peak is 0)."""
    return avg_load_kw / peak_load_kw if peak_load_kw > 0 else 0.0


def escalated_annual_costs(first_year_cost: float, escalation: float, years: int) -> list[float]:
    """Cost for each year, rising by `escalation` (0.10 = 10%) per year, compounded."""
    return [first_year_cost * (1 + escalation) ** (year - 1) for year in range(1, years + 1)]


@dataclass
class ProjectResult:
    daily_energy_kwh: float
    daily_fuel: float
    capex: float
    annual_fixed_cost: float
    annual_fuel_costs: list[float] = field(default_factory=list)

    @property
    def years(self) -> int:
        return len(self.annual_fuel_costs)

    @property
    def total_fuel_cost(self) -> float:
        return sum(self.annual_fuel_costs)

    @property
    def total_cost(self) -> float:
        return self.capex + self.annual_fixed_cost * self.years + self.total_fuel_cost

    @property
    def total_kwh(self) -> float:
        return self.daily_energy_kwh * DAYS_PER_YEAR * self.years

    @property
    def tariff(self) -> float:
        """Flat break-even tariff in ₦/kWh over the whole term."""
        return self.total_cost / self.total_kwh if self.total_kwh > 0 else 0.0

    @property
    def first_year_fuel_cost_per_kwh(self) -> float:
        annual_kwh = self.daily_energy_kwh * DAYS_PER_YEAR
        return self.annual_fuel_costs[0] / annual_kwh if annual_kwh > 0 and self.annual_fuel_costs else 0.0


def project_result(
    *,
    daily_energy: float,
    daily_fuel: float,
    fuel_price: float,
    fuel_escalation: float,
    years: int,
    generator_cost: float,
    installation_cost: float,
    monthly_om: float,
    monthly_logistics: float,
) -> ProjectResult:
    """Break-even costs over the term. Fuel use is in the fuel's own unit (L, kg or scm)."""
    first_year_fuel_cost = daily_fuel * DAYS_PER_YEAR * fuel_price
    return ProjectResult(
        daily_energy_kwh=daily_energy,
        daily_fuel=daily_fuel,
        capex=generator_cost + installation_cost,
        annual_fixed_cost=(monthly_om + monthly_logistics) * 12,
        annual_fuel_costs=escalated_annual_costs(first_year_fuel_cost, fuel_escalation, years),
    )
