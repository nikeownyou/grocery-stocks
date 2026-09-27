#!/usr/bin/env python3
"""Build groceries.db from schema.sql + sample_data.csv (seed = simulated)."""
import csv
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB = HERE / "groceries.db"

if DB.exists():
    DB.unlink()

con = sqlite3.connect(DB)
con.executescript((HERE / "schema.sql").read_text())

with open(HERE / "sample_data.csv", newline="") as f:
    rows = list(csv.DictReader(f))

con.executemany(
    "INSERT INTO prices (date, ticker, item, price, unit, store, source, note)"
    " VALUES (:Date, :Ticker, :Item, :Price, :Unit, :Store, 'simulated', :Notes)",
    rows,
)
con.commit()

n = con.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
print(f"seeded {n} rows into {DB}")
con.close()
