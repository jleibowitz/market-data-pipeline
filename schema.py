"""
DDL definitions and schema creation for the stock price database.
All statements use IF NOT EXISTS — safe to call on every run.
"""

import sqlite3

STOCKS_DDL = """
CREATE TABLE IF NOT EXISTS stocks (
    ticker           TEXT NOT NULL PRIMARY KEY,
    company_name     TEXT,
    exchange         TEXT,
    sector           TEXT,
    sub_industry     TEXT,
    index_membership TEXT,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

PRICES_DDL = """
CREATE TABLE IF NOT EXISTS prices (
    ticker    TEXT NOT NULL,
    date      TEXT NOT NULL,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL,
    adj_close REAL,
    volume    INTEGER,
    PRIMARY KEY (ticker, date),
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);
CREATE INDEX IF NOT EXISTS idx_prices_date   ON prices(date);
CREATE INDEX IF NOT EXISTS idx_prices_ticker ON prices(ticker);
"""

LOG_DDL = """
CREATE TABLE IF NOT EXISTS ingestion_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT NOT NULL,
    run_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    rows_inserted INTEGER,
    last_date     TEXT,
    status        TEXT NOT NULL,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_ticker ON ingestion_log(ticker);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes. Idempotent."""
    conn.executescript(STOCKS_DDL + PRICES_DDL + LOG_DDL)
    conn.commit()
