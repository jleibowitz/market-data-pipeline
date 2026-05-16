# market-data-pipeline

SQLite database and ingestion pipeline for historical stock price data from Yahoo Finance.

Covers the S&P 500, S&P 400, S&P 600, and NASDAQ 100 (~1,500 tickers). Supports full
history downloads and incremental daily updates.

## Database location

The default database path is `~/market_data.db` (your home directory). **Do not store the
database inside a cloud-synced folder such as OneDrive or Dropbox.**

Two reasons this matters for this codebase specifically:

- **WAL mode** — SQLite's WAL journal creates two extra files (`market_data.db-wal`,
  `market_data.db-shm`). Cloud sync tools that touch these mid-write can corrupt the
  database or produce sync conflicts.
- **Size and write frequency** — a full run (~1,500 tickers) writes millions of rows.
  Syncing a multi-GB file on every pipeline run wastes bandwidth and slows ingestion.

The source files (`.py`) are fine in OneDrive; only the generated database needs to live
outside it. On WSL2 the default path resolves to `/home/<user>/market_data.db`, which is
inside the WSL virtual disk and never synced.

## Schema

Three tables:

- **`stocks`** — ticker metadata (company name, GICS sector/sub-industry, index membership)
- **`prices`** — daily OHLCV with composite primary key `(ticker, date)`; `close` and `adj_close` are both split- and dividend-adjusted (`auto_adjust=True`)
- **`ingestion_log`** — per-ticker audit trail of every pipeline run

## Files

| File | Description |
|---|---|
| `schema.py` | DDL constants and `create_schema()` |
| `db.py` | Connection factory, upsert helpers, ingestion logging |
| `scraper.py` | Wikipedia scraper for index constituents and GICS metadata |
| `downloader.py` | yfinance chunked download and wide→long transform |
| `pipeline.py` | Main ingestion entry point |
| `query.py` | CLI inspection tool |

## Usage

### Full run (scrape Wikipedia + download all ~1,500 tickers)

```bash
python pipeline.py           # uses ~/market_data.db by default
```

### Quick test with specific tickers

```bash
python pipeline.py --tickers AAPL MSFT NVDA AMZN
```

### Incremental update (fetch only new data since last run)

```bash
python pipeline.py --no-scrape
```

### Re-download everything from scratch

```bash
python pipeline.py --full-refresh
```

### Pipeline flags

| Flag | Description |
|---|---|
| `--db PATH` | SQLite file path (default: `~/market_data.db`) |
| `--tickers T [T ...]` | Download only these tickers |
| `--no-scrape` | Skip Wikipedia scrape; use tickers already in the `stocks` table |
| `--full-refresh` | Ignore stored last dates; redownload complete history |

## Inspecting the database

```bash
# Row counts, ticker count, date range
python query.py --summary

# Recent prices for a ticker
python query.py --ticker AAPL
python query.py --ticker AAPL --tail 30

# All tickers in a sector
python query.py --sector Technology

# Tickers with no price data
python query.py --missing

# Ingestion history for a ticker
python query.py --log AAPL
```

All `query.py` commands accept `--db PATH` to point at a non-default database file.

## Direct SQL

```bash
sqlite3 ~/market_data.db

-- Summary
SELECT COUNT(DISTINCT ticker) AS tickers, COUNT(*) AS rows,
       MIN(date) AS earliest, MAX(date) AS latest
FROM prices;

-- Latest price for each ticker
SELECT ticker, date, close
FROM prices
WHERE date = (SELECT MAX(date) FROM prices)
ORDER BY ticker;

-- Tickers in a sector
SELECT ticker, company_name FROM stocks WHERE sector = 'Information Technology';
```

## Dependencies

- `yfinance`
- `pandas`
- `requests`

### Setup (WSL2 / Ubuntu)

On Ubuntu 24.04+, pip installs are blocked system-wide (PEP 668). Create a virtual
environment outside OneDrive so the installed packages aren't subject to cloud sync:

```bash
python3 -m venv ~/.venv-market
~/.venv-market/bin/pip install pandas yfinance requests
```

Then run scripts with:

```bash
~/.venv-market/bin/python pipeline.py --tickers AAPL MSFT NVDA AMZN
```

Or activate the environment for the session:

```bash
source ~/.venv-market/bin/activate
python pipeline.py --tickers AAPL MSFT NVDA AMZN
```
