"""Tests for scripts/update_prices.py, using saved copies of NERC's pages."""

import importlib.util
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
IE_URL = "https://nerc.gov.ng/wp-content/uploads/2026/09/IE_HOLDCO_YSS_September_2026_093.pdf"

spec = importlib.util.spec_from_file_location("update_prices", ROOT / "scripts" / "update_prices.py")
up = importlib.util.module_from_spec(spec)
spec.loader.exec_module(up)


@pytest.fixture(scope="module")
def ie_text():
    """OCR text of NERC's September 2026 order for Ikeja Electric (Order NERC/2026/093)."""
    return (FIXTURES / "nerc_ie_2026_09_ocr.txt").read_text(encoding="utf-8")


def test_discover_picks_latest_order_per_disco():
    orders = up.discover_orders((FIXTURES / "nerc_myto_listing.html").read_text(encoding="utf-8"))
    assert set(orders) == up.DISCOS
    # August (_080) and September (_093) orders share the 2026/09 folder
    assert orders["IE"].url == IE_URL
    assert orders["KEDCO"].url.endswith("KEDCO_HOLDCO_YSS_Septmeber_2026_096.pdf")
    assert all(o.serial >= 88 for o in orders.values())


def test_parse_ie_order(ie_text):
    result = up.parse_order_text("IE", IE_URL, ie_text, date(2026, 9, 1))
    assert result.error == ""
    assert result.bands == {"A": 209.50, "B": 62.48, "C": 45.80, "D": 31.24, "E": 31.24}
    assert result.period == "Aug 2024 - Sep 2026"
    assert result.naira_per_usd == 1369.5
    assert result.gas_usd_mmbtu == 3.39
    assert result.order_no == "NERC/2026/093"
    assert result.effective == date(2026, 9, 1)


@pytest.mark.parametrize("line,expected", [
    ("Exchange Rate §/S 1,379 1,389 1369.5", 1369.5),
    ("Exchange Rate N/$ 1,379 | 1,389 | 1,369.48", 1369.48),
    ("A - Non-MD 225.00 206.80 | 209.50", 209.5),
])
def test_last_number_keeps_whole_numbers(line, expected):
    assert up._last_number(line) == expected


def test_effective_date_ignores_dates_of_earlier_orders():
    text = ("MYTO-2024 effective from 1st January 2024.\n"
            "This Supplementary Order shall be effective from 1st September 2026.")
    assert up.parse_effective_date(text) == date(2026, 9, 1)
    assert up.parse_effective_date("This Order shall take effect on 1st August 2026 and") == date(2026, 8, 1)
    assert up.parse_effective_date("no date here") is None


@pytest.mark.parametrize("bands,fx,message", [
    ({"A": 209.5, "B": 62.48, "C": 45.8}, None, "incomplete"),
    ({"B": 62.48, "C": 45.8, "D": 31.24, "E": 31.24}, None, "incomplete"),
    ({"A": 209.5, "B": 62.48, "C": 45.8, "D": 31.24, "E": 5000}, None, "outside"),
    ({"A": 20.95, "B": 62.48, "C": 45.8, "D": 31.24, "E": 31.24}, None, "Band A is not the highest"),
    ({"A": 209.5, "B": 62.48, "C": 45.8, "D": 31.24, "E": 31.24}, 9.5, "exchange rate"),
])
def test_bad_values_are_rejected(bands, fx, message):
    result = up.OrderResult(disco="IE", url=IE_URL, bands=bands, naira_per_usd=fx)
    assert message in up.check_values(result)


def test_disco_without_band_e_is_accepted():
    """YEDC's September 2026 order has Bands A-D only."""
    result = up.OrderResult(disco="YEDC", url=IE_URL, bands={"A": 209.5, "B": 63.33, "C": 52.51, "D": 50.01})
    assert up.check_values(result) == ""


def test_offline_run_updates_prices_file(tmp_path, ie_text):
    """Full run with the saved listing and OCR text: no network, no tesseract."""
    prices = tmp_path / "prices.json"
    shutil.copy(ROOT / "data" / "prices.json", prices)
    data = json.loads(prices.read_text(encoding="utf-8"))
    data["prices"] = [e for e in data["prices"] if e["method"] == "manual"]
    prices.write_text(json.dumps(data), encoding="utf-8")

    cache = tmp_path / "ocr"
    cache.mkdir()
    listing = tmp_path / "listing.html"
    listing.write_text(f'<a href="{IE_URL}">IE</a>', encoding="utf-8")
    (cache / "IE_HOLDCO_YSS_September_2026_093.txt").write_text(ie_text, encoding="utf-8")
    summary = tmp_path / "summary.md"

    assert up.main(["--prices", str(prices), "--listing", str(listing),
                    "--ocr-cache", str(cache), "--summary", str(summary)]) == 0

    written = {e["key"]: e for e in json.loads(prices.read_text(encoding="utf-8"))["prices"]}
    assert written["grid:IE:A"]["value"] == 209.5
    assert written["grid:IE:A"]["as_of"] == "2026-09-01"
    assert written["naira_per_usd"]["value"] == 1369.5
    assert written["pipeline_gas_usd_mmbtu"]["value"] == 3.39
    assert "diesel" in written  # manual entries are kept
    assert "Updated, effective 2026-09-01" in summary.read_text(encoding="utf-8")

    # A second run sees the same order and changes nothing
    before = prices.read_text(encoding="utf-8")
    assert up.main(["--prices", str(prices), "--listing", str(listing), "--ocr-cache", str(cache)]) == 0
    assert prices.read_text(encoding="utf-8") == before
