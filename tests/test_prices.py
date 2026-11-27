import copy
import json
from datetime import date

import pytest

from genset.prices import PRICES_PATH, grid_tariffs, load_prices, parse_prices

GOOD = {
    "key": "diesel", "label": "Diesel", "value": 1700, "unit": "₦/L", "region": "National",
    "source_name": "Test", "source_url": "https://example.org", "as_of": "2026-11-01",
    "fetched_at": "2026-11-02", "method": "manual", "primary_source": False,
}


def test_repository_prices_file_is_valid():
    prices = load_prices()
    for key in ("diesel", "petrol", "lpg", "cng"):
        assert key in prices
    raw = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    assert len(raw["prices"]) == len(prices)


def test_parse_valid_entry():
    entry = parse_prices({"prices": [GOOD]})["diesel"]
    assert entry.value == 1700
    assert entry.as_of == date(2026, 11, 1)


@pytest.mark.parametrize("field,value,message", [
    ("value", -5, "positive"),
    ("as_of", "1 Nov 2026", "YYYY-MM-DD"),
    ("method", "guess", "method"),
    ("primary_source", "yes", "true or false"),
])
def test_invalid_entries_are_rejected(field, value, message):
    bad = {**GOOD, field: value}
    with pytest.raises(ValueError, match=message):
        parse_prices({"prices": [bad]})


def test_missing_field_and_duplicate_rejected():
    missing = {k: v for k, v in GOOD.items() if k != "source_url"}
    with pytest.raises(ValueError, match="missing source_url"):
        parse_prices({"prices": [missing]})
    with pytest.raises(ValueError, match="duplicate"):
        parse_prices({"prices": [GOOD, copy.deepcopy(GOOD)]})


def test_staleness():
    entry = parse_prices({"prices": [GOOD]})["diesel"]
    assert entry.age_days(date(2026, 12, 31)) == 60
    assert not entry.is_stale(date(2026, 12, 31))
    assert entry.is_stale(date(2027, 1, 1))


def test_grid_tariffs_grouped_by_disco_and_band():
    rows = [{**GOOD, "key": f"grid:{d}:{b}", "unit": "₦/kWh", "method": "nerc_ocr", "primary_source": True}
            for d in ("IE", "AEDC") for b in ("A", "B")]
    grid = grid_tariffs(parse_prices({"prices": rows}))
    assert list(grid) == ["AEDC", "IE"]
    assert set(grid["IE"]) == {"A", "B"}
