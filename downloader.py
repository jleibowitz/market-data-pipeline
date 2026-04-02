"""
Yahoo Finance download helpers.

Downloads daily OHLCV data via yfinance and transforms from wide (Date × Ticker)
to long format suitable for direct insertion into the prices table.
"""

from datetime import datetime, timedelta
from typing import Generator

import pandas as pd
import yfinance as yf

CHUNK_SIZE = 250
OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]


def download_chunk(
    tickers: list[str], start: str | None = None
) -> tuple[pd.DataFrame, str | None]:
    """
    Download OHLCV for a list of tickers.

    Args:
        tickers: list of ticker symbols (always passed as a list, even for one ticker)
        start:   'YYYY-MM-DD' start date, or None for full history (period='max')

    Returns:
        (long_df, error_str) — long_df has columns [Date, Ticker, Open, High, Low, Close, Volume]
        with Date as 'YYYY-MM-DD' strings. Returns (empty DataFrame, error_str) on failure.
    """
    date_kwargs: dict = {}
    if start:
        date_kwargs["start"] = start
    else:
        date_kwargs["period"] = "max"

    try:
        raw = yf.download(
            tickers,
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            multi_level_index=True,
            **date_kwargs,
        )
    except Exception as e:
        return pd.DataFrame(), str(e)

    if raw is None or raw.empty:
        return pd.DataFrame(), None

    # Strip timezone and normalize to midnight
    raw.index = raw.index.tz_localize(None).normalize()

    # Wide → long: stack the Ticker level (level 0) to get rows per (Date, Ticker)
    try:
        long = raw.stack(level=0, future_stack=True).reset_index()
    except Exception as e:
        return pd.DataFrame(), f"stack failed: {e}"

    long.columns.name = None

    # After stack(level=0), the ticker column comes out as 'Ticker' (from the
    # MultiIndex level name set by yfinance) or as 'level_1' depending on version.
    if "Ticker" not in long.columns and "level_1" in long.columns:
        long = long.rename(columns={"level_1": "Ticker"})
    elif "Price" in long.columns:
        # Some yfinance versions name the level 'Price'
        long = long.rename(columns={"Price": "Ticker"})

    # Keep only expected columns
    keep = ["Date", "Ticker"] + [c for c in OHLCV_COLS if c in long.columns]
    long = long[keep].copy()

    # Drop rows with no close price
    long = long.dropna(subset=["Close"])

    if long.empty:
        return pd.DataFrame(), None

    # Normalize Date column to YYYY-MM-DD strings
    long["Date"] = pd.to_datetime(long["Date"]).dt.strftime("%Y-%m-%d")

    return long, None


def _chunk_start(chunk: list[str], last_dates: dict[str, str]) -> str | None:
    """
    Return the day after the earliest last_date in this chunk, or None if
    any ticker in the chunk has no stored history (needs full download).
    """
    dates = [last_dates[t] for t in chunk if t in last_dates]
    if len(dates) < len(chunk):
        return None  # at least one ticker needs full history
    earliest = min(dates)
    next_day = datetime.strptime(earliest, "%Y-%m-%d") + timedelta(days=1)
    return next_day.strftime("%Y-%m-%d")


def download_all(
    tickers: list[str], last_dates: dict[str, str]
) -> Generator[tuple[pd.DataFrame, list[str], str | None], None, None]:
    """
    Download OHLCV for all tickers in chunks of CHUNK_SIZE.

    Yields (long_df, chunk_tickers, error_str) for each chunk.
    long_df may be empty if no data was returned (check error_str for failures).
    """
    n_chunks = (len(tickers) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[i : i + CHUNK_SIZE]
        chunk_num = i // CHUNK_SIZE + 1
        start = _chunk_start(chunk, last_dates)

        print(
            f"  Chunk {chunk_num}/{n_chunks}: {len(chunk)} tickers"
            + (f" from {start}" if start else " (full history)"),
            flush=True,
        )

        df, error = download_chunk(chunk, start=start)
        yield df, chunk, error
