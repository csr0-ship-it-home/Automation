"""Synthetic data so the dashboard renders (clearly labeled DEMO) before the first live run."""
import math
import random
from datetime import date, timedelta


def _bdays(n, end):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out[::-1]


def prices(symbols, n=2520, end=None, seed=7):
    end = end or date.today()
    days = _bdays(n, end)
    rng = random.Random(seed)
    market = [rng.gauss(0.0003, 0.011) for _ in range(n)]
    for i in range(int(n * 0.55), int(n * 0.58)):  # a crash episode
        market[i] -= 0.012
    out = {}
    for k, sym in enumerate(symbols):
        r = random.Random(seed + k * 101)
        beta = r.uniform(0.3, 1.4)
        drift = r.uniform(-0.0002, 0.0004)
        vol = r.uniform(0.005, 0.012)
        cyc_amp, cyc_len = r.uniform(0.0, 0.0015), r.uniform(200, 900)
        p, series = 100.0, []
        for i in range(n):
            ret = drift + beta * market[i] + r.gauss(0, vol) + cyc_amp * math.sin(i / cyc_len * 2 * math.pi)
            if i > n - 25 and k % 7 == 3:  # recent sell-off in a few names -> oversold signals
                ret -= 0.012
            p *= math.exp(ret)
            series.append((days[i], round(p, 4)))
        out[sym] = series
    return out


def macro(specs, end=None, seed=11):
    end = end or date.today()
    rng = random.Random(seed)
    base = {"VIXCLS": (18, 5), "T10Y2Y": (0.4, 0.6), "T10Y3M": (0.5, 0.8), "BAMLH0A0HYM2": (4, 1.2), "DFF": (3, 1.5),
            "DGS2": (3, 1.2), "DGS10": (3.5, 1), "DFII10": (1, 0.8), "T10YIE": (2.3, 0.3), "CPIAUCSL": (250, 30),
            "PCEPILFE": (115, 10), "UNRATE": (4.5, 1), "SAHMREALTIME": (0.2, 0.2), "ICSA": (230000, 30000),
            "RECPROUSM156N": (5, 8), "UMCSENT": (75, 10), "NFCI": (-0.4, 0.2), "DTWEXBGS": (120, 6),
            "DCOILWTICO": (70, 12), "M2SL": (20000, 2000), "INDPRO": (102, 3), "PERMIT": (1400, 150),
            "NCBEILQ027S": (55_000_000, 10_000_000), "GDP": (25_000, 3_000)}
    step = {"d": 1, "w": 7, "m": 30, "q": 91}
    out = {}
    for spec in specs:
        mu, sd = base.get(spec["id"], (1, 0.1))
        days = []
        d = end
        while d >= end - timedelta(days=365 * 12):
            days.append(d)
            d -= timedelta(days=step[spec["freq"]])
        days = days[::-1]
        x, series = 0.0, []
        growth = spec["id"] in ("CPIAUCSL", "PCEPILFE", "M2SL", "GDP", "NCBEILQ027S", "INDPRO")
        for i, dd in enumerate(days):
            x = 0.97 * x + rng.gauss(0, 0.25)
            v = mu + sd * x
            if growth:
                v = mu * 0.7 * (1 + 0.035) ** (i * step[spec["freq"]] / 365) * (1 + 0.01 * x)
            series.append((dd.isoformat(), round(v, 4)))
        out[spec["id"]] = series
    return out
