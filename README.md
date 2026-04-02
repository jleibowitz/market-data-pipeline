# market-data-pipeline

SQLite database and ingestion pipeline for historical stock price data from Yahoo Finance.

Covers the S&P 500, S&P 400, S&P 600, and NASDAQ 100 (~1,500 tickers). Supports full
history downloads and incremental daily updates.

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
python pipeline.py --db market_data.db
```

### Quick test with specific tickers

```bash
python pipeline.py --db test.db --tickers AAPL MSFT NVDA AMZN
```

### Incremental update (fetch only new data since last run)

```bash
python pipeline.py --db market_data.db --no-scrape
```

### Re-download everything from scratch

```bash
python pipeline.py --db market_data.db --full-refresh
```

### Pipeline flags

| Flag | Description |
|---|---|
| `--db PATH` | SQLite file path (default: `market_data.db`) |
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
sqlite3 market_data.db

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

All available in the standard data science environment. No additional installs required.
