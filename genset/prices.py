"""Load and check the reference prices in data/prices.json."""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PRICES_PATH = DATA_DIR / "prices.json"
STALE_AFTER_DAYS = 60

REQUIRED_FIELDS = {
    "key", "label", "value", "unit", "region", "source_name", "source_url",
    "as_of", "fetched_at", "method", "primary_source",
}
METHODS = {"manual", "nerc_ocr"}


@dataclass(frozen=True)
class PriceEntry:
    key: str
    label: str
    value: float
    unit: str
    region: str
    source_name: str
    source_url: str
    as_of: date
    fetched_at: date
    method: str
    primary_source: bool
    note: str = ""

    def age_days(self, today: date | None = None) -> int:
        return ((today or date.today()) - self.as_of).days

    def is_stale(self, today: date | None = None, max_days: int = STALE_AFTER_DAYS) -> bool:
        return self.age_days(today) > max_days


def validate_entry(raw: dict) -> list[str]:
    """Return a list of problems with one raw price entry (empty when valid)."""
    problems = []
    name = raw.get("key", "<no key>")
    missing = REQUIRED_FIELDS - raw.keys()
    if missing:
        problems.append(f"{name}: missing {', '.join(sorted(missing))}")
        return problems
    if not isinstance(raw["value"], (int, float)) or raw["value"] <= 0:
        problems.append(f"{name}: value must be a positive number")
    for field_name in ("as_of", "fetched_at"):
        try:
            date.fromisoformat(raw[field_name])
        except (TypeError, ValueError):
            problems.append(f"{name}: {field_name} must be a YYYY-MM-DD date")
    if raw["method"] not in METHODS:
        problems.append(f"{name}: method must be one of {sorted(METHODS)}")
    if not isinstance(raw["primary_source"], bool):
        problems.append(f"{name}: primary_source must be true or false")
    return problems


def parse_prices(data: dict) -> dict[str, PriceEntry]:
    entries = data.get("prices")
    if not isinstance(entries, list):
        raise ValueError("prices.json must hold a 'prices' list")
    problems, seen, result = [], set(), {}
    for raw in entries:
        entry_problems = validate_entry(raw)
        if raw.get("key") in seen:
            entry_problems.append(f"{raw['key']}: duplicate key")
        seen.add(raw.get("key"))
        problems += entry_problems
        if not entry_problems:
            result[raw["key"]] = PriceEntry(
                key=raw["key"],
                label=raw["label"],
                value=float(raw["value"]),
                unit=raw["unit"],
                region=raw["region"],
                source_name=raw["source_name"],
                source_url=raw["source_url"],
                as_of=date.fromisoformat(raw["as_of"]),
                fetched_at=date.fromisoformat(raw["fetched_at"]),
                method=raw["method"],
                primary_source=raw["primary_source"],
                note=raw.get("note", ""),
            )
    if problems:
        raise ValueError("Invalid prices.json:\n" + "\n".join(problems))
    return result


def load_prices(path: Path = PRICES_PATH) -> dict[str, PriceEntry]:
    return parse_prices(json.loads(Path(path).read_text(encoding="utf-8")))


def grid_key(disco: str, band: str) -> str:
    return f"grid:{disco}:{band}"


def grid_tariffs(prices: dict[str, PriceEntry]) -> dict[str, dict[str, PriceEntry]]:
    """Grid tariffs grouped as {DisCo: {band: entry}}."""
    out: dict[str, dict[str, PriceEntry]] = {}
    for key, entry in prices.items():
        if key.startswith("grid:"):
            _, disco, band = key.split(":")
            out.setdefault(disco, {})[band] = entry
    return dict(sorted(out.items()))
