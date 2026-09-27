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

Usage: python3 fetch_flyer.py [--db PATH] [--postal CODE]
Idempotent: PRIMARY KEY (date, ticker, store) — reruns skip.
"""

import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

STORES = ["Atlantic Superstore", "Sobeys", "Costco"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

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
            valid = f"{(it.get('valid_from') or '')[:10]}→{(it.get('valid_to') or '')[:10]}"
            note = f"flyer: {it['name']} | {valid}"
            if it.get("sale_story"):
                note += f" | {it['sale_story']}"
            cur = con.execute(
                "INSERT OR IGNORE INTO prices"
                " (date, ticker, item, price, unit, store, source, note)"
                " VALUES (?, ?, ?, ?, ?, ?, 'flyer', ?)",
                (today, ticker, spec["item"], float(it["current_price"]),
                 spec["unit"], store, note),
            )
            if cur.rowcount:
                added += 1
                print(f"{ticker} @ {store}: ${it['current_price']} — {it['name']}")
            else:
                print(f"{ticker} @ {store}: already logged today, skip")
        time.sleep(2)  # be gentle with the endpoint

    con.commit()
    con.close()
    print(f"done: {added} new rows")


if __name__ == "__main__":
    main()
