"""
Scrape index constituent tickers and GICS metadata from Wikipedia.

Sources:
  S&P 500   — https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
  S&P 400   — https://en.wikipedia.org/wiki/List_of_S%26P_400_companies
  S&P 600   — https://en.wikipedia.org/wiki/List_of_S%26P_600_companies
  NASDAQ 100 — https://en.wikipedia.org/wiki/Nasdaq-100

Returns a DataFrame with columns:
  ticker, company_name, sector, sub_industry, index_membership
"""

import io
import re

import pandas as pd
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; market-data-pipeline/1.0)"}

SOURCES = [
    {
        "name": "S&P 500",
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "table": 0,
        "sym": "Symbol",
        "sec": "Security",
        "gics_sector": "GICS Sector",
        "gics_sub": "GICS Sub-Industry",
    },
    {
        "name": "S&P 400",
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "table": 0,
        "sym": "Symbol",
        "sec": "Security",
        "gics_sector": "GICS Sector",
        "gics_sub": "GICS Sub-Industry",
    },
    {
        "name": "S&P 600",
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
        "table": 0,
        "sym": "Symbol",
        "sec": "Security",
        "gics_sector": "GICS Sector",
        "gics_sub": "GICS Sub-Industry",
    },
    {
        "name": "NASDAQ 100",
        "url": "https://en.wikipedia.org/wiki/Nasdaq-100",
        "table": 5,
        "sym": "Ticker",
        "sec": "Company",
        "gics_sector": None,
        "gics_sub": None,
    },
]

_TICKER_RE = re.compile(r"^[A-Z]{1,6}(-[A-Z])?$")


def _scrape_source(src: dict) -> pd.DataFrame | None:
    try:
        resp = requests.get(src["url"], headers=HEADERS, timeout=30)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        if src["table"] >= len(tables):
            print(f"  WARNING {src['name']}: expected table index {src['table']}, "
                  f"only {len(tables)} tables found — skipping")
            return None
        tbl = tables[src["table"]]
    except Exception as e:
        print(f"  WARNING {src['name']}: {e}")
        return None

    out = pd.DataFrame()
    out["ticker"] = (
        tbl[src["sym"]].astype(str).str.strip().str.replace(".", "-", regex=False)
    )
    out["company_name"] = tbl[src["sec"]].astype(str).str.strip()
    out["sector"] = (
        tbl[src["gics_sector"]].astype(str).str.strip()
        if src["gics_sector"]
        else ""
    )
    out["sub_industry"] = (
        tbl[src["gics_sub"]].astype(str).str.strip()
        if src["gics_sub"]
        else ""
    )
    out["_source"] = src["name"]

    valid = out["ticker"].str.match(_TICKER_RE.pattern, na=False)
    out = out[valid].drop_duplicates("ticker").reset_index(drop=True)
    print(f"  {src['name']:12s}: {len(out):4d} tickers")
    return out


def scrape_all_sources() -> pd.DataFrame:
    """
    Scrape all index sources and return a deduplicated DataFrame.

    Deduplication: first-occurrence wins (S&P 500 > S&P 400 > S&P 600 > NASDAQ 100),
    so GICS metadata comes from the highest-priority index that lists the ticker.
    A separate `index_membership` column records all indices the ticker appears in.
    """
    print("Scraping index constituents from Wikipedia ...")
    frames = [_scrape_source(s) for s in SOURCES]
    frames = [f for f in frames if f is not None]

    if not frames:
        raise RuntimeError("Failed to scrape any index source.")

    combined = pd.concat(frames, ignore_index=True)

    # Build index_membership before dedup (ticker may appear in multiple sources)
    membership = (
        combined.groupby("ticker")["_source"]
        .apply(lambda s: ",".join(s.tolist()))
        .reset_index()
        .rename(columns={"_source": "index_membership"})
    )

    # First-occurrence-wins dedup for GICS metadata
    deduped = combined.drop_duplicates("ticker", keep="first").reset_index(drop=True)
    deduped = deduped.merge(membership, on="ticker", how="left")
    deduped = deduped.drop(columns=["_source"])

    # Fill missing sector/sub_industry with empty string rather than NaN
    deduped["sector"] = deduped["sector"].fillna("").replace("nan", "")
    deduped["sub_industry"] = deduped["sub_industry"].fillna("").replace("nan", "")

    # exchange is not available from Wikipedia — leave as empty string
    deduped["exchange"] = ""

    print(f"\nTotal unique tickers: {len(deduped)}")
    return deduped[["ticker", "company_name", "exchange", "sector", "sub_industry", "index_membership"]]
