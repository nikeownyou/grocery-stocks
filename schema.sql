-- Grocery Stocks price history.
-- One row per (date, ticker, store). source is one of:
--   'simulated' — synthetic seed data for charts until real prices flow in
--   'flyer'     — collected automatically from Atlantic Superstore flyers
--   'manual'    — logged by hand

CREATE TABLE IF NOT EXISTS prices (
    date       TEXT NOT NULL,
    ticker     TEXT NOT NULL,
    item       TEXT NOT NULL,
    price      REAL NOT NULL,   -- package price in CAD
    unit       TEXT NOT NULL,   -- ACTUAL package size, e.g. "6 lb", "1.21 kg"
    unit_price REAL,            -- price per base unit (per kg, per 100g, per L,
                               -- per dozen, per loaf); NULL when size unknown
    store      TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'manual',
    note       TEXT,
    PRIMARY KEY (date, ticker, store)
);

CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices (ticker, date);
