"""Refresh data/prices.json from official sources.

Currently automated: NERC monthly supplementary tariff orders (grid tariffs for
Bands A-E, the NGN/USD rate and the gas price NERC assumes for power plants).
The order PDFs draw their tables as shapes, not text, so pages are read with
OCR (tesseract). Every value is range-checked, and the weekly workflow opens a
pull request so a person checks the figures before the app uses them.

Fuel pump prices (diesel, petrol, LPG, CNG) are kept by hand: NBS resets
automated connections and NMDPRA does not publish retail prices on its site.

Usage:
    python scripts/update_prices.py [--dry-run] [--summary FILE] [--force]
    python scripts/update_prices.py --listing FILE --pdf-dir DIR   # offline
    python scripts/update_prices.py --ocr-cache DIR                # reuse OCR text
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from genset.prices import PRICES_PATH, grid_key, parse_prices  # noqa: E402

LISTING_URL = "https://nerc.gov.ng/resource-category/myto/"
LISTING_PAGES = 3
DISCOS = {"AEDC", "BEDC", "EEDC", "EKEDP", "IBEDC", "IE", "JED", "KAEDC", "KEDCO", "PHED", "YEDC"}
BANDS = ["A", "B", "C", "D", "E"]
USER_AGENT = "genset-price-updater (+https://github.com/Abdulhafeez-Abdulsalam/Genset)"
TIMEOUT = 90

ORDER_LINK = re.compile(r"https://nerc\.gov\.ng/wp-content/uploads/(\d{4})/(\d{2})/([A-Z]+)_[^\"'\s<>]*?\.pdf")
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


@dataclass(frozen=True)
class OrderLink:
    disco: str
    url: str
    year: int
    month: int
    serial: int  # NERC's running order number at the end of the file name, e.g. _093

    @property
    def sort_key(self) -> tuple[int, int, int]:
        return (self.year, self.month, self.serial)


@dataclass
class OrderResult:
    disco: str
    url: str
    order_no: str = ""
    effective: date | None = None
    period: str = ""
    bands: dict[str, float] | None = None
    naira_per_usd: float | None = None
    gas_usd_mmbtu: float | None = None
    error: str = ""


# ---------- discovery ----------

def discover_orders(html: str) -> dict[str, OrderLink]:
    """Latest order PDF per DisCo from NERC's MYTO listing HTML."""
    latest: dict[str, OrderLink] = {}
    for match in ORDER_LINK.finditer(html):
        year, month, disco = int(match.group(1)), int(match.group(2)), match.group(3)
        if disco not in DISCOS:
            continue
        # Several months' orders can share an upload folder, and file names have
        # typos ("Septmeber"), so rank by the serial number, not the month name.
        serial = re.search(r"_(\d{2,4})\.pdf$", match.group(0))
        link = OrderLink(disco, match.group(0), year, month, int(serial.group(1)) if serial else 0)
        current = latest.get(disco)
        if current is None or link.sort_key > current.sort_key:
            latest[disco] = link
    return latest


# ---------- parsing OCR text ----------

# Comma-grouped numbers first ("1,369.48"), then plain ones ("1369.5"), so a
# plain number is never split into pieces.
NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"


def _last_number(line: str) -> float | None:
    numbers = re.findall(NUMBER, line)
    return float(numbers[-1].replace(",", "")) if numbers else None


def parse_tariff_table(text: str) -> tuple[str, dict[str, float]]:
    """Return (latest period label, {band: Non-MD tariff in ₦/kWh})."""
    bands: dict[str, float] = {}
    period = ""
    for line in text.splitlines():
        if "Tariff Class" in line and not period:
            periods = re.findall(
                r"[A-Z][a-z]{2}\s+\d{4}\s*[-–]\s*[A-Z][a-z]{2}\s+\d{4}"
                r"|[A-Z][a-z]{2}\s*[-–]\s*[A-Z][a-z]{2}\s+\d{4}"
                r"|[A-Z][a-z]{2}\s+\d{4}", line)
            period = re.sub(r"\s+", " ", periods[-1]) if periods else ""
        match = re.match(r"^\s*([A-E])\s*[-–—]?\s*Non\s*-?\s*MD\b(.*)$", line)
        if match and match.group(1) not in bands:
            value = _last_number(match.group(2))
            if value is not None:
                bands[match.group(1)] = value
    return period, bands


def parse_indices(text: str) -> tuple[float | None, float | None]:
    """Return (NGN per USD, gas supply and transport cost in USD/MMBtu) for the latest month."""
    fx = gas = None
    for line in text.splitlines():
        if fx is None and re.match(r"^\s*Exchange Rate\b", line):
            fx = _last_number(line.split("Exchange Rate", 1)[1])
        if gas is None and "Gas Supply and Transportation Cost" in line:
            gas = _last_number(line.split("MMBTU", 1)[-1])
    return fx, gas


def parse_order_number(text: str) -> str:
    match = re.search(r"ORDER\s*/\s*NERC\s*/\s*(\d{4})\s*/\s*(\d{2,4})", text)
    return f"NERC/{match.group(1)}/{match.group(2)}" if match else ""


def parse_effective_date(text: str) -> date | None:
    """Date the order itself takes effect (not dates of earlier orders it cites)."""
    patterns = [
        r"Supplementary\s+Order\s+shall\s+be\s+effective\s+from",
        r"This\s+Order\s+shall\s+take\s+effect\s+on",
    ]
    for lead in patterns:
        match = re.search(lead + r"\s+(\d{1,2})\s*\S*?\s+([A-Za-z]+)\s*,?\s+(\d{4})", text)
        if match and match.group(2).lower() in MONTHS:
            return date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1)))
    return None


def check_values(result: OrderResult) -> str:
    """Return an error message if the parsed values look wrong, else ''."""
    # Some DisCos have no Band E (YEDC's September 2026 order stops at D), so
    # require Band A and an unbroken run of at least four bands from A.
    found = sorted(result.bands or {})
    if len(found) < 4 or found != BANDS[: len(found)]:
        return f"tariff table incomplete (bands found: {', '.join(found) or 'none'})"
    for band, value in result.bands.items():
        if not 1 <= value <= 2000:
            return f"Band {band} tariff {value} outside 1-2000 ₦/kWh"
    if result.bands["A"] < max(result.bands[b] for b in found[1:]):
        return "Band A is not the highest tariff; check the OCR"
    if result.naira_per_usd is not None and not 300 <= result.naira_per_usd <= 10000:
        return f"exchange rate {result.naira_per_usd} outside 300-10000"
    if result.gas_usd_mmbtu is not None and not 0.5 <= result.gas_usd_mmbtu <= 20:
        return f"gas price {result.gas_usd_mmbtu} outside 0.5-20 USD/MMBtu"
    return ""


def parse_order_text(disco: str, url: str, text: str, fallback_date: date) -> OrderResult:
    result = OrderResult(disco=disco, url=url)
    result.period, result.bands = parse_tariff_table(text)
    result.naira_per_usd, result.gas_usd_mmbtu = parse_indices(text)
    result.order_no = parse_order_number(text)
    result.effective = parse_effective_date(text) or fallback_date
    result.error = check_values(result)
    return result


# ---------- OCR ----------

def ocr_pdf(pdf_bytes: bytes) -> str:
    """OCR every page, removing table grid lines first so tesseract reads the cells."""
    import numpy as np
    import pypdfium2 as pdfium
    import pytesseract
    from PIL import Image

    texts = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    for page in pdf:
        ink = np.array(page.render(scale=4).to_pil().convert("L")) < 150
        ink[ink.mean(axis=1) > 0.35, :] = False   # horizontal rules
        ink[:, ink.mean(axis=0) > 0.20] = False   # vertical rules
        image = Image.fromarray(np.where(ink, 0, 255).astype("uint8"))
        texts.append(pytesseract.image_to_string(image, config="--psm 6"))
    return "\n".join(texts)


# ---------- updating prices.json ----------

def order_entries(result: OrderResult, today: date) -> list[dict]:
    source_name = f"NERC order {result.order_no}".strip() if result.order_no else "NERC supplementary order"
    common = {
        "source_name": f"{source_name} ({result.disco})",
        "source_url": result.url,
        "as_of": result.effective.isoformat(),
        "fetched_at": today.isoformat(),
        "method": "nerc_ocr",
        "primary_source": True,
    }
    entries = [
        {
            "key": grid_key(result.disco, band),
            "label": f"Grid tariff, Band {band} (non-MD)",
            "value": value,
            "unit": "₦/kWh",
            "region": f"{result.disco} customers in states NERC still regulates",
            "note": f"Tariff period: {result.period}" if result.period else "",
            **common,
        }
        for band, value in sorted(result.bands.items())
    ]
    return entries


def indices_entries(result: OrderResult, today: date) -> list[dict]:
    common = {
        "region": "National",
        "source_name": f"NERC order {result.order_no} ({result.disco})" if result.order_no else "NERC order",
        "source_url": result.url,
        "as_of": result.effective.isoformat(),
        "fetched_at": today.isoformat(),
        "method": "nerc_ocr",
        "primary_source": True,
    }
    out = []
    if result.naira_per_usd:
        out.append({"key": "naira_per_usd", "label": "Exchange rate used by NERC",
                    "value": result.naira_per_usd, "unit": "₦/US$", **common})
    if result.gas_usd_mmbtu:
        out.append({"key": "pipeline_gas_usd_mmbtu", "label": "Gas supply and transport cost for power plants",
                    "value": result.gas_usd_mmbtu, "unit": "US$/MMBtu",
                    "note": "Price NERC assumes for gas-fired power plants. Commercial buyers usually pay more; "
                            "enter your own contract price if you have one.", **common})
    return out


def merge(existing: list[dict], updates: list[dict]) -> list[dict]:
    by_key = {e["key"]: e for e in existing}
    for entry in updates:
        by_key[entry["key"]] = entry
    return sorted(by_key.values(), key=lambda e: e["key"])


def summarise(results: list[OrderResult], skipped: list[str]) -> str:
    lines = ["## Price update summary", "", "| DisCo | Result | Band A–E (₦/kWh) | Order |", "|---|---|---|---|"]
    for r in sorted(results, key=lambda r: r.disco):
        bands = " / ".join(f"{r.bands[b]:g}" if b in r.bands else "–" for b in BANDS) if r.bands and not r.error else ""
        status = f"Failed: {r.error}" if r.error else f"Updated, effective {r.effective}"
        lines.append(f"| {r.disco} | {status} | {bands} | [PDF]({r.url}) |")
    for disco in skipped:
        lines.append(f"| {disco} | Unchanged (same order as before) | | |")
    lines += ["", "Please compare each changed figure with the linked PDF before merging.",
              "Fuel pump prices (diesel, petrol, LPG, CNG) are not automated; update them by hand in data/prices.json."]
    return "\n".join(lines)


def fetch(url: str) -> bytes:
    import requests

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prices", type=Path, default=PRICES_PATH)
    parser.add_argument("--dry-run", action="store_true", help="show changes without writing prices.json")
    parser.add_argument("--force", action="store_true", help="re-read orders already in prices.json")
    parser.add_argument("--summary", type=Path, help="write a Markdown summary (used as the PR body)")
    parser.add_argument("--listing", type=Path, help="read NERC's listing HTML from a file instead of the web")
    parser.add_argument("--pdf-dir", type=Path, help="read order PDFs from <dir>/<file name> when present, else download")
    parser.add_argument("--ocr-cache", type=Path, help="reuse/save OCR text in this folder (for debugging)")
    args = parser.parse_args(argv)

    today = date.today()
    data = json.loads(args.prices.read_text(encoding="utf-8"))
    existing_urls = {e["key"]: e["source_url"] for e in data["prices"]}

    if args.listing:
        html = args.listing.read_text(encoding="utf-8")
    else:
        html = ""
        for page in range(1, LISTING_PAGES + 1):
            url = LISTING_URL if page == 1 else f"{LISTING_URL}page/{page}/"
            try:
                html += fetch(url).decode("utf-8", errors="replace")
            except Exception as exc:  # one bad page should not stop the run
                print(f"warning: could not read {url}: {exc}", file=sys.stderr)
    orders = discover_orders(html)
    if not orders:
        print("error: no NERC tariff orders found in the listing", file=sys.stderr)
        return 1

    results, skipped, updates = [], [], []
    for disco, link in sorted(orders.items()):
        if not args.force and existing_urls.get(grid_key(disco, "A")) == link.url:
            skipped.append(disco)
            continue
        try:
            cached = args.ocr_cache / (Path(link.url).stem + ".txt") if args.ocr_cache else None
            if cached and cached.exists():
                text = cached.read_text(encoding="utf-8")
            else:
                local = args.pdf_dir / Path(link.url).name if args.pdf_dir else None
                pdf_bytes = local.read_bytes() if local and local.exists() else fetch(link.url)
                text = ocr_pdf(pdf_bytes)
                if cached:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_text(text, encoding="utf-8")
            result = parse_order_text(disco, link.url, text, date(link.year, link.month, 1))
        except Exception as exc:
            result = OrderResult(disco=disco, url=link.url, error=f"{type(exc).__name__}: {exc}")
        results.append(result)
        print(f"{disco}: {result.error or result.bands}", file=sys.stderr)
        if not result.error:
            updates += order_entries(result, today)

    good = [r for r in results if not r.error]
    if good:
        newest = max(good, key=lambda r: (r.effective, r.disco == "IE"))
        updates += indices_entries(newest, today)

    data["prices"] = merge(data["prices"], updates)
    parse_prices(data)  # fail loudly rather than write an invalid file
    data["updated"] = datetime.now().strftime("%Y-%m-%d")

    summary = summarise(results, skipped)
    print(summary)
    if args.summary:
        args.summary.write_text(summary + "\n", encoding="utf-8")
    if not args.dry_run and updates:
        args.prices.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
