# 📈 Grocery Stocks

Staple grocery prices, evaluated like stocks: daily movers, 7/30-day moving
averages, 30-day highs and lows, buy-the-dip signals, and a basket index
that treats your whole grocery list like a portfolio.

## How it works

- **Google Sheet = the price history.** One row per ticker per day:
  `Date | Ticker | Item | Price | Unit | Store | Notes`.
- **Daily tracker** appends today's Atlantic Superstore prices automatically.
- **Streamlit = the terminal.** Market overview, ticker charts, basket index.
- Prices can also be logged by hand with the **✏️ Log a price** form.

## Signals

| Signal | Meaning |
|--------|---------|
| 🟢 BUY — 30-day low | Cheapest it's been in a month — stock up |
| 🟢 BUY THE DIP | More than 3% below its 7-day average |
| 🔴 30-day high | Most expensive in a month — wait if you can |
| ➖ HOLD | Nothing special going on |

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Without Google credentials configured, the app shows the demo data from `sample_data.csv`.

## Deploy (Streamlit Community Cloud)

1. Push this folder to a public GitHub repo.
2. On share.streamlit.io → New app → pick the repo, main file `app.py`.
3. In the app's **Secrets**, add:
   ```toml
   sheet_id = "YOUR_SHEET_ID"

   [gcp_service_account]
   # paste the service-account JSON key fields here
   ```
   The Google Sheet must be shared with the service account's email
   (Editor if you want the in-app logging form to work).
4. Deploy — no code changes needed.
