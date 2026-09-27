#!/usr/bin/env python3
"""
Daily flyer-price fetcher for Grocery Stocks.

Hits Flipp's public item-search endpoint (the same API flipp.com's own
website uses), matches one product per staple ticker per store, and
upserts today's prices into groceries.db.

Stores: Atlantic Superstore, Sobeys, Costco — all publish flyers on
Flipp for the configured postal region. Costco coverage is sparse
(monthly coupon-book style, bulk packs); missing days are normal.

Why Flipp and not the stores directly: Loblaw's product API blocks
scripted access (HTTP 403 via Akamai). Flipp aggregates the same
flyers and exposes an unauthenticated search endpoint.
Caveat: this is flyer/sale data (weekly cadence), not everyday shelf
prices — the sale prices are the "dips" in the stock-chart analogy.

Matching is heuristic: each ticker has expected package-size hints and
reject hints (e.g. chicken rejects "5 PACK" family packs). The raw
flyer item name is always stored in the note column so matches stay
auditable. Prefer reviewing notes over blindly trusting signals.

Units: the ACTUAL package size is parsed out of each flyer item name
("6 LB", "915/930 G", "1.21kg", "$1/lb" hints in the sale story) and
stored in `unit`, plus a normalized `unit_price` per base unit
(per kg, per 100g, per L, per dozen, per loaf) so prices are comparable
across stores and package sizes. When no size can be determined,
unit_price is NULL and the app falls back to the package price.

Usage: python3 fetch_flyer.py [--db PATH] [--postal CODE]
Idempotent: PRIMARY KEY (date, ticker, store) — reruns skip.
"""

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

STORES = ["Atlantic Superstore", "Sobeys", "Costco"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# Base unit each ticker is normalized to for fair comparison.
BASE_UNIT = {
    "MILK": "L", "EGGS": "dozen", "BREAD": "loaf", "BUTTER": "100g",
    "CHEDDAR": "100g", "CHICKEN": "kg", "BANANA": "kg", "APPLES": "kg",
    "RICE": "kg", "PASTA": "100g", "COFFEE": "100g", "OATS": "kg",
}
BASE_LABEL = {"L": "/L", "dozen": "/dozen", "loaf": "/loaf",
              "100g": "/100g", "kg": "/kg"}

# When a flyer name carries no parseable size, assume the ticker's
# canonical package (only for tickers where that's a safe assumption).
DEFAULTS = {
    "BREAD": (1.0, "loaf"), "CHICKEN": (1.0, "kg"),
    "BANANA": (1.0, "kg"), "APPLES": (1.0, "kg"),
}

# ticker -> search query, required name keywords, unit label, canonical
# item name, package-size hints (preferred), reject hints (skip)
TRACKED = {
    "MILK":    dict(query="2L milk",        keywords=["MILK"],    unit="2L",
                    item="2L 2% Milk", size=["2 L", "2L"], reject=["1 L", "1L", "500 ML"]),
    "EGGS":    dict(query="eggs dozen",     keywords=["EGG"],     unit="dozen",
                    item="Dozen Large Eggs", size=["12", "DOZEN"], reject=["18", "30 PACK"]),
    "BREAD":   dict(query="bread 675g",     keywords=["BREAD"],   unit="loaf",
                    item="675g Whole Wheat Bread", size=["675"], reject=[]),
    "BUTTER":  dict(query="butter 454g",    keywords=["BUTTER"],  unit="454g",
                    item="454g Butter", size=["454"], reject=[]),
    "CHEDDAR": dict(query="cheddar cheese", keywords=["CHEDDAR"], unit="400g",
                    item="400g Cheddar Cheese", size=["400"], reject=[]),
    "CHICKEN": dict(query="chicken breast", keywords=["CHICKEN"], unit="kg",
                    item="Chicken Breast", size=["/KG", "PER KG", "BREAST"],
                    reject=["5 PACK", "FAMILY PACK", "NUGGET", "STRIP"]),
    "BANANA":  dict(query="bananas",        keywords=["BANANA"],  unit="kg",
                    item="Bananas", size=["/KG", "PER KG"], reject=[]),
    "APPLES":  dict(query="apples",         keywords=["APPLE"],   unit="kg",
                    item="Gala Apples", size=["/KG", "PER KG", "GALA"], reject=["JUICE", "RED BULL"]),
    "RICE":    dict(query="rice 2kg",       keywords=["RICE"],    unit="2kg",
                    item="2kg Long Grain Rice", size=["2 KG", "2KG"], reject=["1 KG", "1KG"]),
    "PASTA":   dict(query="pasta 900g",     keywords=["PASTA"],   unit="900g",
                    item="900g Pasta", size=["900"], reject=[]),
    "COFFEE":  dict(query="ground coffee",  keywords=["COFFEE"],  unit="875g",
                    item="875g Ground Coffee", size=["875"],
                    reject=["INSTANT", "K-CUP", "PODS", "250 G", "250G"]),
    "OATS":    dict(query="oats 1kg",       keywords=["OAT"],     unit="1kg",
                    item="1kg Rolled Oats", size=["1 KG", "1KG"], reject=[]),
}


def flipp_search(query, postal):
    url = ("https://backflipp.wishabi.com/flipp/items/search?"
           f"q={urllib.parse.quote(query)}&postal_code={postal}&locale=en")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("items", [])


def match_item(items, spec, store):
    """Best-scoring item for this store, or None if nothing is clean."""
    best, best_score = None, -999
    for it in items:
        if it.get("merchant_name") != store:
            continue
        name = (it.get("name") or "").upper()
        if not all(k in name for k in spec["keywords"]):
            continue
        score = 0
        if any(r in name for r in spec["reject"]):
            score -= 10
        if any(h in name for h in spec["size"]):
            score += 2
        if score > best_score:
            best, best_score = it, score
    if best is None or best_score < 0:
        return None
    return best


def _to_base(qty, from_u, base):
    """Convert qty in from_u ('g','kg','lb','oz','l','ml','ct') to base units."""
    if base == "kg":
        return {"g": qty / 1000, "kg": qty,
                "lb": qty * 0.45359237, "oz": qty * 0.0283495}[from_u]
    if base == "100g":
        return {"g": qty / 100, "kg": qty * 10,
                "lb": qty * 4.5359237, "oz": qty * 0.283495}[from_u]
    if base == "L":
        return {"l": qty, "ml": qty / 1000}[from_u]
    if base == "dozen":
        return {"ct": qty / 12}[from_u]
    if base == "loaf":
        return {"ct": qty}[from_u]
    return None


def parse_size(name, ticker):
    """Extract the actual package size from a flyer item name.

    Returns (qty_in_base_units, label) e.g. (2.7216, "6 lb"), or
    (None, "pack") when no size can be determined. The sale_story is
    worth including in `name` — per-lb/per-kg hints often live there.
    """
    n = f" {name.upper()} "
    base = BASE_UNIT[ticker]

    # gram range: "200 G - 250 G", "915/930 G" -> midpoint
    m = re.search(r"(\d+(?:\.\d+)?)\s*G\s*[/\-–]\s*(\d+(?:\.\d+)?)\s*G\b", n)
    if m:
        q = (float(m.group(1)) + float(m.group(2))) / 2
        if base in ("kg", "100g"):
            return _to_base(q, "g", base), f"{m.group(1)}-{m.group(2)} g"
        return None, f"{m.group(1)}-{m.group(2)} g"
    m = re.search(r"(\d+(?:\.\d+)?)\s*[/\-–]\s*(\d+(?:\.\d+)?)\s*G\b", n)
    if m:
        q = (float(m.group(1)) + float(m.group(2))) / 2
        if base in ("kg", "100g"):
            return _to_base(q, "g", base), f"{m.group(1)}-{m.group(2)} g"
        return None, f"{m.group(1)}-{m.group(2)} g"

    # NOTE: allow an optional "/" before the unit — per-lb/per-kg hints in
    # sale stories look like "$1/lb" or "SAVE $2/kg"
    for pat, from_u in [(r"(\d+(?:\.\d+)?)\s*/?\s*KG\b", "kg"),
                        (r"(\d+(?:\.\d+)?)\s*/?\s*G\b", "g"),
                        (r"(\d+(?:\.\d+)?)\s*/?\s*LB\b", "lb"),
                        (r"(\d+(?:\.\d+)?)\s*/?\s*OZ\b", "oz")]:
        m = re.search(pat, n)
        if m:
            q = float(m.group(1))
            if base not in ("kg", "100g"):
                return None, f"{m.group(1)} {from_u}"
            label = f"{m.group(1)} {from_u}"
            if re.search(r"\d\s*'S\b", n) and from_u == "kg":
                label = f"pack (up to {label})"
            return _to_base(q, from_u, base), label

    if base == "L":
        m = re.search(r"(\d+(?:\.\d+)?)\s*ML\b", n)
        if m:
            return _to_base(float(m.group(1)), "ml", base), f"{m.group(1)} mL"
        m = re.search(r"(?<![A-Z])(\d+(?:\.\d+)?)\s*L(?![A-Z])", n)
        if m:
            return _to_base(float(m.group(1)), "l", base), f"{m.group(1)} L"

    if base in ("dozen", "loaf"):
        if "DOZEN" in n:
            return _to_base(12, "ct", base), "dozen"
        m = re.search(r"(\d+)\s*'S\b", n)
        if m:
            return _to_base(int(m.group(1)), "ct", base), f"{m.group(1)} pack"
        m = re.search(r"\b(\d+)\s*(?:CT|COUNT|PACK)\b", n)
        if m:
            return _to_base(int(m.group(1)), "ct", base), f"{m.group(1)} pack"
        if ticker == "EGGS" and re.search(r"\b12\b", n):
            return _to_base(12, "ct", base), "dozen"

    return None, "pack"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path(__file__).parent / "groceries.db"))
    ap.add_argument("--postal", default="B3Z3E3")  # Upper Tantallon / St. Margarets Bay, NS
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.executescript((Path(__file__).parent / "schema.sql").read_text())
    today = date.today().isoformat()

    added = 0
    for ticker, spec in TRACKED.items():
        try:
            items = flipp_search(spec["query"], args.postal)
        except Exception as e:  # network hiccup -> try next ticker
            print(f"{ticker}: search failed ({e}), skip", file=sys.stderr)
            continue
        for store in STORES:
            it = match_item(items, spec, store)
            if not it or not it.get("current_price"):
                print(f"{ticker} @ {store}: no clean flyer match today")
                continue
            price = float(it["current_price"])
            # actual package size from the flyer name (+ sale story, which
            # often holds the per-lb/per-kg hint). No guessing: when the
            # size can't be determined, unit_price stays NULL.
            qty, label = parse_size(
                f"{it['name']} {it.get('sale_story') or ''}", ticker)
            unit_price = round(price / qty, 4) if qty else None
            valid = f"{(it.get('valid_from') or '')[:10]}→{(it.get('valid_to') or '')[:10]}"
            note = f"flyer: {it['name']} | {valid}"
            if it.get("sale_story"):
                note += f" | {it['sale_story']}"
            cur = con.execute(
                "INSERT OR IGNORE INTO prices"
                " (date, ticker, item, price, unit, unit_price, store, source, note)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'flyer', ?)",
                (today, ticker, spec["item"], price, label, unit_price,
                 store, note),
            )
            if cur.rowcount:
                added += 1
                per = f" ({BASE_LABEL[BASE_UNIT[ticker]]} ${unit_price:.2f})" if unit_price else " (size unknown)"
                print(f"{ticker} @ {store}: ${price} / {label}{per} — {it['name']}")
            else:
                print(f"{ticker} @ {store}: already logged today, skip")
        time.sleep(2)  # be gentle with the endpoint

    con.commit()
    con.close()
    print(f"done: {added} new rows")


if __name__ == "__main__":
    main()
