#!/usr/bin/env python3
"""
Stock price ingestion pipeline.

Usage:
    # Full run: scrape Wikipedia, download all tickers, store in SQLite
    python pipeline.py --db market_data.db

    # Quick test with specific tickers (skips Wikipedia scrape)
    python pipeline.py --db test.db --no-scrape --tickers AAPL MSFT NVDA

    # Re-download everything from scratch
    python pipeline.py --db market_data.db --full-refresh

    # Update prices only (skip re-scraping metadata)
    python pipeline.py --db market_data.db --no-scrape
"""

import argparse
import os
import sys
import time

import db
import downloader
import schema
import scraper


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stock price ingestion pipeline")
    p.add_argument(
        "--db",
        default="~/market_data.db",
        metavar="PATH",
        help="SQLite database file (default: ~/market_data.db)",
    )
    p.add_argument(
        "--tickers",
        nargs="+",
        metavar="TICKER",
        help="Download only these tickers (implies --no-scrape unless combined)",
    )
    p.add_argument(
        "--full-refresh",
        action="store_true",
        help="Ignore stored last dates and redownload full history for all tickers",
    )
    p.add_argument(
        "--no-scrape",
        action="store_true",
        help="Skip Wikipedia scrape; use tickers already in the stocks table",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    args.db = os.path.expanduser(args.db)
    t0 = time.time()

    # ── 1. Connect and create schema ─────────────────────────────────────────
    print(f"Opening database: {args.db}")
    conn = db.get_connection(args.db)
    schema.create_schema(conn)

    # ── 2. Determine ticker universe ─────────────────────────────────────────
    if args.tickers:
        # Explicit ticker list: insert placeholder rows in stocks table so the
        # FK constraint on prices is satisfied.
        tickers = [t.strip().upper().replace(".", "-") for t in args.tickers]
        stub_rows = [
            {
                "ticker": t,
                "company_name": None,
                "exchange": None,
                "sector": None,
                "sub_industry": None,
                "index_membership": "manual",
            }
            for t in tickers
        ]
        db.upsert_stocks(conn, stub_rows)
        print(f"Using {len(tickers)} explicitly provided ticker(s).")

    elif not args.no_scrape:
        universe_df = scraper.scrape_all_sources()
        rows = universe_df.to_dict("records")
        db.upsert_stocks(conn, rows)
        tickers = universe_df["ticker"].tolist()
        print(f"Universe: {len(tickers)} tickers upserted into stocks table.")

    else:
        # --no-scrape: use whatever is already in the stocks table
        result = conn.execute("SELECT ticker FROM stocks ORDER BY ticker").fetchall()
        tickers = [r["ticker"] for r in result]
        if not tickers:
            print("ERROR: --no-scrape specified but stocks table is empty. "
                  "Run without --no-scrape first.", file=sys.stderr)
            sys.exit(1)
        print(f"Using {len(tickers)} tickers from existing stocks table.")

    # ── 3. Incremental start dates ───────────────────────────────────────────
    if args.full_refresh:
        last_dates: dict[str, str] = {}
        print("Full refresh: re-downloading complete history for all tickers.")
    else:
        last_dates = db.get_last_dates(conn, tickers)
        up_to_date = sum(1 for t in tickers if t in last_dates)
        print(f"{up_to_date}/{len(tickers)} tickers have existing price data.")

    # ── 4. Download and store ────────────────────────────────────────────────
    print(f"\nDownloading price data ...")
    total_rows = 0
    ok_count = 0
    error_count = 0
    no_data_count = 0

    for chunk_df, chunk_tickers, error in downloader.download_all(tickers, last_dates):
        if error:
            error_count += len(chunk_tickers)
            for t in chunk_tickers:
                db.log_run(conn, t, 0, None, "error", error)
            print(f"    ERROR in chunk: {error}")
            continue

        if chunk_df.empty:
            no_data_count += len(chunk_tickers)
            for t in chunk_tickers:
                db.log_run(conn, t, 0, None, "no_data")
            continue

        # Build DB rows: (ticker, date, open, high, low, close, adj_close, volume)
        # close == adj_close because auto_adjust=True
        price_rows = []
        for r in chunk_df.itertuples(index=False):
            volume = int(r.Volume) if hasattr(r, "Volume") and r.Volume == r.Volume else None
            price_rows.append((
                r.Ticker, r.Date,
                r.Open if r.Open == r.Open else None,
                r.High if r.High == r.High else None,
                r.Low  if r.Low  == r.Low  else None,
                r.Close,
                r.Close,   # adj_close mirrors close (auto_adjust=True)
                volume,
            ))

        n = db.upsert_prices(conn, price_rows)
        total_rows += n

        # Per-ticker log
        ticker_set = set(chunk_tickers)
        for t in chunk_tickers:
            t_rows = chunk_df[chunk_df["Ticker"] == t]
            if t_rows.empty:
                no_data_count += 1
                db.log_run(conn, t, 0, None, "no_data")
            else:
                ok_count += 1
                last = t_rows["Date"].max()
                db.log_run(conn, t, len(t_rows), last, "ok")

    # ── 5. Checkpoint WAL and print summary ──────────────────────────────────
    db.checkpoint(conn)
    conn.close()

    elapsed = time.time() - t0
    print(f"\n{'─' * 50}")
    print(f"Done in {elapsed:.1f}s")
    print(f"  Tickers processed : {len(tickers)}")
    print(f"  OK                : {ok_count}")
    print(f"  No data           : {no_data_count}")
    print(f"  Errors            : {error_count}")
    print(f"  Price rows stored : {total_rows:,}")
    print(f"  Database          : {args.db}")


if __name__ == "__main__":
    main()
