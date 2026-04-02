"""
Database connection factory and low-level data access helpers.
"""

import sqlite3


def get_connection(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def upsert_stocks(conn: sqlite3.Connection, rows: list[dict]) -> None:
    sql = """
        INSERT OR REPLACE INTO stocks
            (ticker, company_name, exchange, sector, sub_industry, index_membership,
             updated_at)
        VALUES (:ticker, :company_name, :exchange, :sector, :sub_industry,
                :index_membership, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    """
    with conn:
        conn.executemany(sql, rows)


def upsert_prices(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """
    Insert or replace price rows.
    Each row: (ticker, date, open, high, low, close, adj_close, volume)
    Returns the number of rows processed.
    """
    sql = """
        INSERT OR REPLACE INTO prices
            (ticker, date, open, high, low, close, adj_close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    with conn:
        conn.executemany(sql, rows)
    return len(rows)


def get_last_dates(conn: sqlite3.Connection, tickers: list[str]) -> dict[str, str]:
    """Return {ticker: 'YYYY-MM-DD'} for tickers that have price rows."""
    if not tickers:
        return {}
    placeholders = ",".join("?" * len(tickers))
    sql = f"""
        SELECT ticker, MAX(date) AS last_date
        FROM prices
        WHERE ticker IN ({placeholders})
        GROUP BY ticker
    """
    rows = conn.execute(sql, tickers).fetchall()
    return {r["ticker"]: r["last_date"] for r in rows}


def log_run(
    conn: sqlite3.Connection,
    ticker: str,
    rows_inserted: int,
    last_date: str | None,
    status: str,
    error_message: str | None = None,
) -> None:
    sql = """
        INSERT INTO ingestion_log
            (ticker, rows_inserted, last_date, status, error_message)
        VALUES (?, ?, ?, ?, ?)
    """
    with conn:
        conn.execute(sql, (ticker, rows_inserted, last_date, status, error_message))


def checkpoint(conn: sqlite3.Connection) -> None:
    """Truncate the WAL file after a successful run to keep the DB file compact."""
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
