-- Grocery Stocks price history.
-- One row per (date, ticker, store). source is one of:
--   'simulated' — synthetic seed data for charts until real prices flow in
--   'flyer'     — collected automatically from Atlantic Superstore flyers
--   'manual'    — logged by hand

CREATE TABLE IF NOT EXISTS prices (
    date   TEXT NOT NULL,
    ticker TEXT NOT NULL,
    item   TEXT NOT NULL,
    price  REAL NOT NULL,
    unit   TEXT NOT NULL,
    store  TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    note   TEXT,
    PRIMARY KEY (date, ticker, store)
);

CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices (ticker, date);
