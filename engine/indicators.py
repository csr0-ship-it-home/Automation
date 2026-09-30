"""Pure-Python technical/statistical helpers. All series are plain lists, oldest first."""
import math


def sma(values, n):
    out = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def rsi(values, n=14):
    """Wilder's RSI; returns list aligned with values (None until warm)."""
    out = [None] * len(values)
    if len(values) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    avg_g, avg_l = gains / n, losses / n
    out[n] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    for i in range(n + 1, len(values)):
        d = values[i] - values[i - 1]
        avg_g = (avg_g * (n - 1) + max(d, 0)) / n
        avg_l = (avg_l * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def pct_change(values, lookback, end=None):
    end = len(values) - 1 if end is None else end
    start = end - lookback
    if start < 0 or values[start] == 0:
        return None
    return values[end] / values[start] - 1


def percentile_rank(history, value):
    """Fraction of history <= value (0..1)."""
    h = [x for x in history if x is not None]
    if not h:
        return None
    return sum(1 for x in h if x <= value) / len(h)


def rolling_max(values, n):
    from collections import deque
    out, dq = [], deque()
    for i, v in enumerate(values):
        while dq and values[dq[-1]] <= v:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - n:
            dq.popleft()
        out.append(values[dq[0]])
    return out


def drawdown_series(values, window=252):
    peaks = rolling_max(values, window)
    return [v / p - 1 for v, p in zip(values, peaks)]


def realized_vol(values, n=21):
    if len(values) <= n:
        return None
    rets = [math.log(values[i] / values[i - 1]) for i in range(len(values) - n, len(values))]
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    return math.sqrt(var) * math.sqrt(252)


def rolling_vol_series(values, n=21, step=5):
    """Sampled rolling vol for percentile context."""
    out = []
    for end in range(n + 1, len(values), step):
        out.append(realized_vol(values[:end], n))
    return out


def last_cross(fast, slow, lookback=260):
    """Return (kind, bars_ago) of the most recent fast/slow crossover, or (None, None)."""
    n = len(fast)
    for i in range(n - 1, max(n - lookback, 1), -1):
        a0, b0, a1, b1 = fast[i - 1], slow[i - 1], fast[i], slow[i]
        if None in (a0, b0, a1, b1):
            break
        if a0 <= b0 and a1 > b1:
            return "golden", n - 1 - i
        if a0 >= b0 and a1 < b1:
            return "death", n - 1 - i
    return None, None


def forward_return_stats(values, condition, horizons=(21, 63, 126), min_gap=20):
    """Historical forward returns after a condition first turns true (episodes spaced >= min_gap bars).

    Returns {"episodes": n, "h21": {"avg":..,"win":..}, ..., "base": {...unconditional...}}.
    """
    idx, last = [], -10 ** 9
    for i, c in enumerate(condition):
        if c and i - last >= min_gap:
            idx.append(i)
            last = i
        elif c:
            last = i  # extend the episode so a long-lasting condition counts once
    res = {"episodes": 0}
    for h in horizons:
        fw = [values[i + h] / values[i] - 1 for i in idx if i + h < len(values)]
        base = [values[i + h] / values[i] - 1 for i in range(0, len(values) - h, 5)]
        res[f"h{h}"] = _summ(fw)
        res[f"base{h}"] = _summ(base)
        res["episodes"] = max(res["episodes"], len(fw))
    return res


def _summ(xs):
    if not xs:
        return None
    return {"avg": sum(xs) / len(xs), "win": sum(1 for x in xs if x > 0) / len(xs), "n": len(xs)}


def clip(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def value_at_or_before(series, date):
    """series: [(date, value)] oldest first. Latest value dated <= date."""
    best = None
    for d, v in series:
        if d <= date:
            best = v
        else:
            break
    return best


def yoy_series(series):
    """Monthly/quarterly [(date,val)] -> [(date, % change vs ~1y earlier)]."""
    out = []
    for d, v in series:
        y, m, dd = d.split("-")
        prior = value_at_or_before(series, f"{int(y) - 1:04d}-{m}-{dd}")
        if prior:
            out.append((d, (v / prior - 1) * 100))
    return out
