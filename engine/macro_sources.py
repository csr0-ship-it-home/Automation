"""Keyless public sources for economic data, straight from the agencies that publish it.

Everything is returned keyed by the FRED series id the rest of the engine already understands,
so FRED itself is only needed for the few series with no public alternative.

  U.S. Treasury   DGS2, DGS10, T10Y2Y, T10Y3M (par yield curve), DFII10 (real yields), T10YIE (10y - real)
  New York Fed    DFF (effective fed funds rate)
  BLS             CPIAUCSL, CORECPI, UNRATE (+ SAHMREALTIME computed from UNRATE)
  U. Michigan     UMCSENT
  Chicago Fed     NFCI
  Yahoo (bulk)    VIXCLS (^VIX), DCOILWTICO (CL=F), DTWEXBGS (DX-Y.NYB) -- fetched with the fund prices
"""
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from .data_sources import _get, _request

# Yahoo tickers downloaded alongside fund prices, mapped to the FRED ids they stand in for
MARKET_TICKERS = {"VIXCLS": "^VIX", "DCOILWTICO": "CL=F", "DTWEXBGS": "DX-Y.NYB"}

TREASURY_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
                "{year}/all?type={kind}&field_tdr_date_value={year}&page&_format=csv")
NYFED_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate={start}&endDate={end}"
BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_SERIES = {"CUSR0000SA0": "CPIAUCSL", "CUSR0000SA0L1E": "CORECPI", "LNS14000000": "UNRATE"}
UMICH_URL = "https://www.sca.isr.umich.edu/files/tbmics.csv"
NFCI_URL = "https://www.chicagofed.org/-/media/publications/nfci/nfci-data-series-csv.csv"
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"], 1)}


def _us_date(s):
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def parse_treasury_csv(text, columns):
    """-> {column: [(date, value)]} for the requested columns (header match is case-insensitive)."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = [h.strip().lower() for h in rows[0]]
    idx = {c: header.index(c.lower()) for c in columns if c.lower() in header}
    out = {c: [] for c in idx}
    for r in rows[1:]:
        d = _us_date(r[0]) if r else None
        if not d:
            continue
        for c, i in idx.items():
            v = _num(r[i]) if i < len(r) else None
            if v is not None:
                out[c].append((d, v))
    return {c: sorted(v) for c, v in out.items()}


def treasury_series(years):
    nominal, real = {}, {}

    def one(args):
        year, kind = args
        cols = ["3 Mo", "2 Yr", "10 Yr"] if kind == "daily_treasury_yield_curve" else ["10 YR"]
        try:
            return kind, parse_treasury_csv(_get(TREASURY_URL.format(year=year, kind=kind), retries=2), cols)
        except Exception as exc:
            print(f"WARN treasury {kind} {year}: {exc}")
            return kind, {}

    jobs = [(y, k) for y in years for k in ("daily_treasury_yield_curve", "daily_treasury_real_yield_curve")]
    with ThreadPoolExecutor(max_workers=4) as ex:
        for kind, cols in ex.map(one, jobs):
            target = nominal if kind == "daily_treasury_yield_curve" else real
            for c, series in cols.items():
                target.setdefault(c.lower(), {}).update(dict(series))
    m3, y2, y10 = nominal.get("3 mo", {}), nominal.get("2 yr", {}), nominal.get("10 yr", {})
    r10 = real.get("10 yr", {})
    ser = lambda d: sorted(d.items())
    out = {}
    if y2:
        out["DGS2"] = ser(y2)
    if y10:
        out["DGS10"] = ser(y10)
        if y2:
            out["T10Y2Y"] = ser({d: round(y10[d] - y2[d], 3) for d in y10 if d in y2})
        if m3:
            out["T10Y3M"] = ser({d: round(y10[d] - m3[d], 3) for d in y10 if d in m3})
        if r10:
            out["T10YIE"] = ser({d: round(y10[d] - r10[d], 3) for d in y10 if d in r10})
    if r10:
        out["DFII10"] = ser(r10)
    return out


def parse_nyfed(text):
    rows = json.loads(text).get("refRates", [])
    return sorted((r["effectiveDate"], float(r["percentRate"])) for r in rows
                  if r.get("effectiveDate") and r.get("percentRate") is not None)


def parse_bls(text):
    out = {}
    data = json.loads(text)
    if data.get("status") not in (None, "REQUEST_SUCCEEDED"):
        raise RuntimeError(f"BLS: {data.get('status')} {data.get('message')}")
    for s in data.get("Results", {}).get("series", []):
        sid = BLS_SERIES.get(s.get("seriesID"))
        if not sid:
            continue
        pts = []
        for p in s.get("data", []):
            per = p.get("period", "")
            v = _num(p.get("value"))
            if per.startswith("M") and per != "M13" and v is not None:
                pts.append((f"{p['year']}-{per[1:]}-01", v))
        out[sid] = sorted(pts)
    return out


def sahm_from_unrate(unrate):
    """Sahm rule: 3-month average unemployment minus the minimum 3-month average of the prior 12 months."""
    vals = [v for _, v in unrate]
    avg3 = [None if i < 2 else sum(vals[i - 2:i + 1]) / 3 for i in range(len(vals))]
    out = []
    for i in range(14, len(vals)):
        prior = [a for a in avg3[i - 12:i] if a is not None]
        if avg3[i] is not None and prior:
            out.append((unrate[i][0], round(avg3[i] - min(prior), 3)))
    return out


def parse_umich(text):
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        m = MONTHS.get(r.get("month", "").lower())
        y, v = r.get("yyyy"), _num(r.get("ics_all"))
        if m and y and v is not None:
            out.append((f"{int(y):04d}-{m:02d}-01", v))
    return sorted(out)


def parse_nfci(text):
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        d = _us_date(r.get("friday_of_week", "") or r.get("date", ""))
        v = _num(r.get("nfci"))
        if d and v is not None:
            out.append((d, v))
    return sorted(out)


def fetch_public_macro(today=None):
    """Returns ({fred_id: [(date, value)]}, {source: error})."""
    today = today or date.today()
    out, errors = {}, {}

    def attempt(name, fn):
        try:
            got = fn()
            out.update({k: v for k, v in got.items() if v})
        except Exception as exc:
            errors[name] = str(exc)[:300]
            print(f"WARN macro source {name}: {exc}")

    years = list(range(today.year - 11, today.year + 1))
    start = f"{today.year - 12}-01-01"
    tasks = {
        "treasury": lambda: treasury_series(years),
        "nyfed": lambda: {"DFF": parse_nyfed(_get(NYFED_URL.format(start=start, end=today.isoformat()), retries=2))},
        "bls": lambda: parse_bls(_request(BLS_URL, data=json.dumps({
            "seriesid": list(BLS_SERIES), "startyear": str(today.year - 9), "endyear": str(today.year)}).encode(),
            headers={"Content-Type": "application/json"}, retries=2)),
        "umich": lambda: {"UMCSENT": parse_umich(_get(UMICH_URL, retries=2))},
        "chicagofed": lambda: {"NFCI": parse_nfci(_get(NFCI_URL, retries=2))},
    }
    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(lambda kv: attempt(*kv), tasks.items()))
    if out.get("UNRATE"):
        out["SAHMREALTIME"] = sahm_from_unrate(out["UNRATE"])
    return out, errors


def credit_proxy(prices):
    """High-yield vs Treasury stress proxy from HYG/IEF prices: drawdown of the ratio from its 1-year high, in %.
    0 = calm; more negative = junk bonds lagging Treasuries (credit stress)."""
    hyg, ief = prices.get("HYG"), prices.get("IEF")
    if not hyg or not ief:
        return []
    imap = dict(ief)
    ratio = [(d, c / imap[d]) for d, c in hyg if imap.get(d)]
    out, window = [], []
    for d, r in ratio:
        window.append(r)
        if len(window) > 252:
            window.pop(0)
        out.append((d, round((r / max(window) - 1) * 100, 3)))
    return out
