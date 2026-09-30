"""Keyless public data sources: Yahoo Finance chart API (primary), Stooq (fallback), FRED CSV."""
import csv
import io
import json
import time
import urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _get(url, retries=3, timeout=30):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # network errors, 429s, etc.
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GET {url} failed: {last}")


def parse_yahoo_chart(text):
    data = json.loads(text)
    result = data["chart"]["result"][0]
    stamps = result.get("timestamp") or []
    ind = result["indicators"]
    closes = (ind.get("adjclose") or [{}])[0].get("adjclose") or ind["quote"][0]["close"]
    out = []
    for ts, c in zip(stamps, closes):
        if c is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if out and out[-1][0] == day:
            out[-1] = (day, float(c))
        else:
            out.append((day, float(c)))
    return out


def fetch_yahoo(symbol, rng="10y"):
    url = (f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?range={rng}&interval=1d&includeAdjustedClose=true&events=div%2Csplits")
    return parse_yahoo_chart(_get(url))


def parse_stooq_csv(text):
    rows = csv.DictReader(io.StringIO(text))
    out = []
    for r in rows:
        try:
            out.append((r["Date"], float(r["Close"])))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def fetch_stooq(symbol):
    return parse_stooq_csv(_get(f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"))


def fetch_prices(symbol):
    """Daily closes as [(YYYY-MM-DD, close)], oldest first. Tries Yahoo then Stooq."""
    errors = []
    for fn in (fetch_yahoo, fetch_stooq):
        try:
            series = fn(symbol)
            if len(series) > 260:
                return series[-2600:]
            errors.append(f"{fn.__name__}: only {len(series)} rows")
        except Exception as exc:
            errors.append(f"{fn.__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def parse_fred_csv(text):
    reader = csv.reader(io.StringIO(text))
    next(reader, None)  # header: observation_date/DATE, SERIES_ID
    out = []
    for row in reader:
        if len(row) < 2 or row[1] in ("", "."):
            continue
        try:
            out.append((row[0], float(row[1])))
        except ValueError:
            continue
    return out


def fetch_fred(series_id, start="2010-01-01"):
    return parse_fred_csv(_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"))
