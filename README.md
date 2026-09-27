# 📈 Grocery Stocks

Track staple grocery prices like stocks: daily movers, moving averages,
30-day highs/lows, buy-the-dip signals, and a basket index that treats
your whole grocery list like a portfolio.

**Live app:** https://grocery-stocks-wjwa8wlszt9bnm6acpjpxq.streamlit.app/

## How it works — no Google, no keys

- Prices live in **`groceries.db`** (SQLite), committed right here in the repo.
- A GitHub Actions workflow (`.github/workflows/daily-fetch.yml`) runs every
  morning, fetches flyer prices for 12 staples across **Atlantic Superstore,
  Sobeys, and Costco** via Flipp's public search endpoint, and commits the
  updated DB.
- Streamlit Cloud redeploys on every push, so the app always reads fresh data.
- No service accounts, no API keys, no secrets to manage.

## Files

| File | What it is |
|---|---|
| `app.py` | The Streamlit dashboard (reads `groceries.db`) |
| `groceries.db` | The price history (SQLite) |
| `schema.sql` | Table definition |
| `seed_db.py` | Rebuilds the DB from `sample_data.csv` |
| `fetch_flyer.py` | Daily flyer-price fetcher (used by Actions) |
| `sample_data.csv` | Original seed data (kept for reference) |

## The data

- **Stores:** Atlantic Superstore, Sobeys, Costco. **Source:** weekly
  flyer/sale prices — these are the "dips", not everyday shelf prices.
- The DB is seeded with **simulated** data so the charts work from day one;
  the app says so honestly until real flyer prices flow in.
- Flyer matching is heuristic (see `fetch_flyer.py`): each ticker has
  package-size hints and reject hints, and the raw flyer item name is always
  stored in the `note` column so matches stay auditable.
- Costco coverage is sparse (monthly coupon-book style, bulk packs); gaps are
  normal. Bulk packs may differ in size from the ticker's canonical unit —
  check the `note` column before trusting a signal.

## Run it locally

```bash
python3 seed_db.py          # rebuild groceries.db from the seed CSV
python3 fetch_flyer.py      # fetch today's flyer prices into the DB
streamlit run app.py
```

## Log a price by hand

The deployed app can't persist writes, so manual entries go through Muse
in chat — he'll add them with a commit.
