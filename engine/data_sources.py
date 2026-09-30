"""Market data sources.

Prices: yfinance bulk download (primary, keyless) -> Tiingo (if TIINGO_API_KEY) -> Yahoo chart API -> Stooq.
Macro:  FRED API (if FRED_API_KEY, recommended) -> FRED graph CSV (keyless, often blocked from cloud IPs).
A host that keeps failing is skipped for the rest of the run so a blocked source fails fast.
"""
import csv
import io
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


_host_failures = {}
_host_lock = threading.Lock()
HOST_FAILURE_LIMIT = 4


def _redact(url):
    parts = urllib.parse.urlsplit(url)
    q = [(k, "***" if k in ("api_key", "token") else v) for k, v in urllib.parse.parse_qsl(parts.query)]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q)))


def _get(url, retries=3, timeout=30, headers=None):
    host = urllib.parse.urlsplit(url).netloc
    last = None
    for attempt in range(retries):
        with _host_lock:
            if _host_failures.get(host, 0) >= HOST_FAILURE_LIMIT:
                raise RuntimeError(f"GET {_redact(url)} skipped: {host} is blocking or down this run ({last or 'repeated failures'})")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                with _host_lock:
                    _host_failures[host] = 0
                return resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # network errors, 429s, etc.
            last = exc
            with _host_lock:
                _host_failures[host] = _host_failures.get(host, 0) + 1
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"GET {_redact(url)} failed: {last}")


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


def parse_tiingo(text):
    out = []
    for row in json.loads(text):
        c = row.get("adjClose") if row.get("adjClose") is not None else row.get("close")
        if c is not None and row.get("date"):
            out.append((row["date"][:10], float(c)))
    return out


def fetch_tiingo(symbol):
    key = os.environ.get("TIINGO_API_KEY")
    if not key:
        raise RuntimeError("TIINGO_API_KEY not set")
    start = (date.today() - timedelta(days=365 * 10 + 10)).isoformat()
    url = f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices?startDate={start}&token={key}"
    return parse_tiingo(_get(url, retries=2, headers={"Content-Type": "application/json"}))


def frame_to_series(frame, symbols):
    """yfinance.download(group_by='ticker', auto_adjust=True) DataFrame -> {symbol: [(date, close)]}."""
    out = {}
    cols = frame.columns
    for sym in symbols:
        try:
            closes = frame[sym]["Close"] if getattr(cols, "nlevels", 1) > 1 else frame["Close"]
        except KeyError:
            continue
        series = [(idx.strftime("%Y-%m-%d"), float(v)) for idx, v in closes.dropna().items()]
        if series:
            out[sym] = series
    return out


def fetch_yfinance_bulk(symbols):
    import yfinance as yf  # installed in the GitHub Action; optional locally
    frame = yf.download(list(symbols), period="10y", interval="1d", auto_adjust=True, group_by="ticker",
                        progress=False, threads=False)
    return frame_to_series(frame, symbols)


def fetch_prices(symbol):
    """Daily closes as [(YYYY-MM-DD, close)], oldest first, for one symbol (fallback chain)."""
    errors = []
    sources = ([fetch_tiingo] if os.environ.get("TIINGO_API_KEY") else []) + [fetch_yahoo, fetch_stooq]
    for fn in sources:
        try:
            series = fn(symbol)
            if len(series) > 260:
                return series[-2600:]
            errors.append(f"{fn.__name__}: only {len(series)} rows")
        except Exception as exc:
            errors.append(f"{fn.__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def fetch_all_prices(symbols, fetch_one=None, workers=3):
    """Bulk yfinance first, then the per-symbol fallback chain for anything still missing."""
    from concurrent.futures import ThreadPoolExecutor
    prices, errors = {}, {}
    try:
        got = fetch_yfinance_bulk(symbols)
        prices.update({s: v[-2600:] for s, v in got.items() if len(v) > 260})
        print(f"yfinance: {len(prices)}/{len(symbols)} symbols")
    except Exception as exc:
        print(f"WARN yfinance bulk download failed: {type(exc).__name__}: {exc}")
    missing = [s for s in symbols if s not in prices]
    fetch_one = fetch_one or fetch_prices
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {s: ex.submit(fetch_one, s) for s in missing}
        for s, f in futs.items():
            try:
                prices[s] = f.result()
            except Exception as exc:
                errors[s] = str(exc)[:300]
    return prices, errors


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


def parse_fred_api(text):
    out = []
    for o in json.loads(text).get("observations", []):
        try:
            out.append((o["date"], float(o["value"])))
        except (KeyError, ValueError, TypeError):
            continue  # "." marks a missing observation
    return out


def fetch_fred(series_id, start="2010-01-01"):
    key = os.environ.get("FRED_API_KEY")
    if key:
        url = ("https://api.stlouisfed.org/fred/series/observations"
               f"?series_id={series_id}&api_key={key}&file_type=json&observation_start={start}")
        return parse_fred_api(_get(url, retries=3, timeout=30))
    return parse_fred_csv(_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}",
                               retries=2, timeout=45, headers={"User-Agent": "curl/8.5.0"}))
