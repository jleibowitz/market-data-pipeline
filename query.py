#!/usr/bin/env python3
"""
CLI inspection tool for the stock price database.

Usage examples:
    python inspect.py --summary
    python inspect.py --ticker AAPL
    python inspect.py --ticker AAPL --tail 20
    python inspect.py --sector Technology
    python inspect.py --missing
    python inspect.py --log AAPL
"""

import argparse
import sys

import db


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Inspect the stock price database")
    p.add_argument("--db", default="market_data.db", metavar="PATH",
                   help="SQLite database file (default: market_data.db)")
    p.add_argument("--summary", action="store_true",
                   help="Print row counts and date range")
    p.add_argument("--ticker", metavar="TICKER",
                   help="Show recent prices for a ticker")
    p.add_argument("--tail", type=int, default=10, metavar="N",
                   help="Number of rows to show with --ticker (default: 10)")
    p.add_argument("--sector", metavar="SECTOR",
                   help="List all tickers in a GICS sector")
    p.add_argument("--missing", action="store_true",
                   help="List tickers in stocks table with no price data")
    p.add_argument("--log", metavar="TICKER",
                   help="Show ingestion log entries for a ticker")
    return p.parse_args()


def _print_table(rows, headers: list[str]) -> None:
    if not rows:
        print("  (no results)")
        return
    col_widths = [len(h) for h in headers]
    data = [list(map(str, row)) for row in rows]
    for row in data:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
    sep = "  " + "  ".join("-" * w for w in col_widths)
    print(fmt.format(*headers))
    print(sep)
    for row in data:
        print(fmt.format(*row))


def cmd_summary(conn) -> None:
    n_stocks = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    n_prices = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    n_tickers = conn.execute("SELECT COUNT(DISTINCT ticker) FROM prices").fetchone()[0]
    row = conn.execute("SELECT MIN(date), MAX(date) FROM prices").fetchone()
    min_date, max_date = row[0] or "—", row[1] or "—"
    n_log = conn.execute("SELECT COUNT(*) FROM ingestion_log").fetchone()[0]

    print(f"Database summary")
    print(f"  Stocks (metadata)  : {n_stocks:,}")
    print(f"  Price rows         : {n_prices:,}")
    print(f"  Tickers with prices: {n_tickers:,}")
    print(f"  Date range         : {min_date} → {max_date}")
    print(f"  Ingestion log rows : {n_log:,}")

    # Status breakdown from most recent log run per ticker
    status_rows = conn.execute("""
        SELECT status, COUNT(*) AS cnt
        FROM (
            SELECT ticker, status,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY run_at DESC) AS rn
            FROM ingestion_log
        )
        WHERE rn = 1
        GROUP BY status
        ORDER BY cnt DESC
    """).fetchall()
    if status_rows:
        print("\n  Last-run status breakdown:")
        for r in status_rows:
            print(f"    {r[0]:<10}: {r[1]:,}")


def cmd_ticker(conn, ticker: str, tail: int) -> None:
    ticker = ticker.upper().replace(".", "-")
    rows = conn.execute("""
        SELECT date, open, high, low, close, volume
        FROM prices
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT ?
    """, (ticker, tail)).fetchall()

    if not rows:
        print(f"No price data found for {ticker}.")
        return

    # Get metadata
    meta = conn.execute(
        "SELECT company_name, sector, index_membership FROM stocks WHERE ticker = ?",
        (ticker,)
    ).fetchone()
    if meta:
        print(f"{ticker} — {meta['company_name'] or 'N/A'}")
        print(f"  Sector: {meta['sector'] or 'N/A'} | Indices: {meta['index_membership'] or 'N/A'}")

    print(f"\nMost recent {len(rows)} trading days:")
    _print_table(
        [(r["date"], f"{r['open']:.2f}" if r["open"] else "—",
          f"{r['high']:.2f}" if r["high"] else "—",
          f"{r['low']:.2f}" if r["low"] else "—",
          f"{r['close']:.2f}" if r["close"] else "—",
          f"{r['volume']:,}" if r["volume"] else "—")
         for r in rows],
        ["Date", "Open", "High", "Low", "Close", "Volume"],
    )


def cmd_sector(conn, sector: str) -> None:
    rows = conn.execute("""
        SELECT s.ticker, s.company_name, s.sub_industry,
               COALESCE(MAX(p.date), '—') AS last_price_date,
               COUNT(p.date) AS price_rows
        FROM stocks s
        LEFT JOIN prices p ON s.ticker = p.ticker
        WHERE s.sector LIKE ?
        GROUP BY s.ticker
        ORDER BY s.ticker
    """, (f"%{sector}%",)).fetchall()

    if not rows:
        print(f"No tickers found for sector matching '{sector}'.")
        return

    print(f"Tickers in sector matching '{sector}' ({len(rows)} found):")
    _print_table(
        [(r["ticker"], r["company_name"] or "—", r["sub_industry"] or "—",
          r["last_price_date"], str(r["price_rows"]))
         for r in rows],
        ["Ticker", "Company", "Sub-Industry", "Last Price", "Rows"],
    )


def cmd_missing(conn) -> None:
    rows = conn.execute("""
        SELECT s.ticker, s.company_name, s.index_membership
        FROM stocks s
        LEFT JOIN prices p ON s.ticker = p.ticker
        WHERE p.ticker IS NULL
        ORDER BY s.ticker
    """).fetchall()

    if not rows:
        print("No missing tickers — all stocks have price data.")
        return

    print(f"{len(rows)} tickers with no price data:")
    _print_table(
        [(r["ticker"], r["company_name"] or "—", r["index_membership"] or "—")
         for r in rows],
        ["Ticker", "Company", "Indices"],
    )


def cmd_log(conn, ticker: str) -> None:
    ticker = ticker.upper().replace(".", "-")
    rows = conn.execute("""
        SELECT run_at, status, rows_inserted, last_date, error_message
        FROM ingestion_log
        WHERE ticker = ?
        ORDER BY run_at DESC
        LIMIT 20
    """, (ticker,)).fetchall()

    if not rows:
        print(f"No ingestion log entries for {ticker}.")
        return

    print(f"Ingestion log for {ticker} (most recent 20):")
    _print_table(
        [(r["run_at"], r["status"], str(r["rows_inserted"] or 0),
          r["last_date"] or "—", r["error_message"] or "")
         for r in rows],
        ["Run At", "Status", "Rows", "Last Date", "Error"],
    )


def main() -> None:
    args = parse_args()

    try:
        conn = db.get_connection(args.db)
    except Exception as e:
        print(f"ERROR: could not open database '{args.db}': {e}", file=sys.stderr)
        sys.exit(1)

    ran_any = False
    if args.summary:
        cmd_summary(conn)
        ran_any = True
    if args.ticker:
        cmd_ticker(conn, args.ticker, args.tail)
        ran_any = True
    if args.sector:
        cmd_sector(conn, args.sector)
        ran_any = True
    if args.missing:
        cmd_missing(conn)
        ran_any = True
    if args.log:
        cmd_log(conn, args.log)
        ran_any = True

    if not ran_any:
        print("No command specified. Use --help for usage.")

    conn.close()


if __name__ == "__main__":
    main()
