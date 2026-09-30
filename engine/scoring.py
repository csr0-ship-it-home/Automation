"""Per-asset metrics, timing signals (with historical backtests) and the composite 0-100 score."""
from .indicators import (clip, drawdown_series, forward_return_stats, last_cross, pct_change,
                         percentile_rank, realized_vol, rolling_vol_series, rsi, sma)
from .universe import BENCHMARK, is_equity, sensitivities

WEIGHTS = {"trend": 0.25, "momentum": 0.20, "value": 0.20, "timing": 0.15, "macro": 0.20}

RATINGS = [(70, "Strong Buy"), (60, "Buy"), (45, "Hold"), (35, "Caution"), (0, "Avoid")]


def rating_for(score):
    for cut, label in RATINGS:
        if score >= cut:
            return label
    return "Avoid"


def _r(x, nd=4):
    return None if x is None else round(x, nd)


def analyze_asset(asset, series, bench_series, macro_factors):
    dates = [d for d, _ in series]
    closes = [c for _, c in series]
    n = len(closes)
    s50, s200 = sma(closes, 50), sma(closes, 200)
    r14 = rsi(closes, 14)
    dd = drawdown_series(closes, 252)
    price = closes[-1]

    # Deviation from 200-day average, and where today's deviation sits in history ("stretch")
    dev200 = [None if s200[i] is None else closes[i] / s200[i] - 1 for i in range(n)]
    stretch_pct = percentile_rank(dev200[:-1], dev200[-1]) if dev200[-1] is not None else None
    slope200 = (s200[-1] / s200[-21] - 1) if s200[-21] else None

    # Relative strength vs benchmark on common dates
    rel = None
    rel_series = []
    if asset["symbol"] != BENCHMARK and bench_series:
        bmap = dict(bench_series)
        rel_series = [(d, c / bmap[d]) for d, c in series if d in bmap and bmap[d]]
        if len(rel_series) > 260:
            rv = [v for _, v in rel_series]
            rel = {
                "r3m": _r(pct_change(rv, 63)),
                "r12m": _r(pct_change(rv, 252)),
                "pct10y": _r(percentile_rank(rv, rv[-1]), 3),
            }

    year = dates[-1][:4]
    ytd_base = next((c for d, c in series if d[:4] == year), None)
    prev_year_close = next((c for d, c in reversed(series) if d[:4] < year), ytd_base)
    vol = realized_vol(closes, 21)
    vols = rolling_vol_series(closes[-1260:], 21, 5)

    mom12_1 = None
    if n > 253:
        mom12_1 = closes[-22] / closes[-253] - 1

    cross_kind, cross_ago = last_cross(s50, s200)
    hi52 = max(closes[-252:])
    lo52 = min(closes[-252:])

    m = {
        "price": _r(price, 2), "date": dates[-1],
        "chg1d": _r(pct_change(closes, 1)),
        "r1w": _r(pct_change(closes, 5)), "r1m": _r(pct_change(closes, 21)),
        "r3m": _r(pct_change(closes, 63)), "r6m": _r(pct_change(closes, 126)),
        "r12m": _r(pct_change(closes, 252)), "r3y": _r(pct_change(closes, 756)),
        "ytd": _r(price / prev_year_close - 1) if prev_year_close else None,
        "mom12_1": _r(mom12_1),
        "sma50": _r(s50[-1], 2), "sma200": _r(s200[-1], 2),
        "vs_sma50": _r(price / s50[-1] - 1) if s50[-1] else None,
        "vs_sma200": _r(dev200[-1]),
        "sma200_slope": _r(slope200),
        "stretch_pct": _r(stretch_pct, 3),
        "rsi14": _r(r14[-1], 1),
        "dd52": _r(dd[-1]),
        "dd_max": _r(price / max(closes) - 1),
        "range52": _r((price - lo52) / (hi52 - lo52), 3) if hi52 > lo52 else None,
        "hi52": _r(hi52, 2), "lo52": _r(lo52, 2),
        "vol21": _r(vol), "vol_pct": _r(percentile_rank(vols, vol), 3) if vol is not None else None,
        "cross": cross_kind, "cross_ago": cross_ago,
        "rel": rel,
        "history_years": round(n / 252, 1),
    }

    signals = _signals(asset, closes, s50, s200, r14, dd, rel, m)

    # Chart payload: ~2y sampled every 2nd bar
    tail = slice(max(0, n - 504), n)
    step = 2
    chart = {
        "d": dates[tail][::step], "c": [_r(x, 2) for x in closes[tail][::step]],
        "s50": [_r(x, 2) for x in s50[tail][::step]], "s200": [_r(x, 2) for x in s200[tail][::step]],
    }
    if rel_series:
        rs = rel_series[-1260:][::5]
        base = rs[0][1]
        chart["rel"] = {"d": [d for d, _ in rs], "v": [_r(v / base * 100, 2) for _, v in rs]}

    return {**{k: asset.get(k) for k in ("symbol", "name", "group", "size", "style")},
            "equity": is_equity(asset), "metrics": m, "signals": signals, "chart": chart,
            "_macro": macro_tilt(asset["symbol"], macro_factors)}


def macro_tilt(symbol, factors):
    sens = sensitivities(symbol)
    tot = sum(abs(w) for w in sens.values()) or 1
    contrib = {k: w * factors.get(k, 0) for k, w in sens.items()}
    return {"score": sum(contrib.values()) / tot,
            "drivers": sorted(({"factor": k, "impact": round(v / tot, 3)} for k, v in contrib.items()),
                              key=lambda x: -abs(x["impact"]))}


def _bt(closes, cond):
    st = forward_return_stats(closes, cond)
    out = {"episodes": st["episodes"]}
    for h in (21, 63, 126):
        a, b = st.get(f"h{h}"), st.get(f"base{h}")
        out[f"h{h}"] = None if not a else {"avg": _r(a["avg"]), "win": _r(a["win"], 3), "n": a["n"]}
        out[f"base{h}"] = None if not b else {"avg": _r(b["avg"]), "win": _r(b["win"], 3)}
    a, b = out.get("h63"), out.get("base63")
    out["edge63"] = _r(a["avg"] - b["avg"]) if a and b else None
    if out["episodes"] < 5 or out["edge63"] is None:
        out["verdict"] = "insufficient"
    elif out["edge63"] > 0.005 and a["win"] >= b["win"]:
        out["verdict"] = "reliable"
    elif out["edge63"] < -0.005:
        out["verdict"] = "unreliable"
    else:
        out["verdict"] = "mixed"
    return out


def _signals(asset, closes, s50, s200, r14, dd, rel, m):
    n = len(closes)
    sym = asset["symbol"]
    rising = [s200[i] is not None and i >= 20 and s200[i - 20] is not None and s200[i] > s200[i - 20] for i in range(n)]
    out = []

    def add(kind, severity, title, detail, cond=None):
        sig = {"id": f"{kind}:{sym}", "kind": kind, "severity": severity, "title": title, "detail": detail}
        if cond is not None:
            sig["backtest"] = _bt(closes, cond)
            # Statistics override: a bullish signal that has lagged for this asset is only informational.
            if severity == "opportunity" and sig["backtest"]["verdict"] == "unreliable":
                sig["severity"] = "info"
                sig["detail"] += " Note: historically this setup has underperformed for this asset."
        out.append(sig)

    rsi_now = r14[-1] or 50
    if rsi_now < 30 and rising[-1]:
        add("oversold_uptrend", "opportunity", f"{sym}: oversold pullback in an uptrend",
            f"RSI {rsi_now:.0f} while the 200-day average is still rising — classic buy-the-dip setup.",
            [r14[i] is not None and r14[i] < 30 and rising[i] for i in range(n)])
    if dd[-1] <= -0.20 and rsi_now < 35:
        add("capitulation", "opportunity", f"{sym}: down {abs(dd[-1]) * 100:.0f}% from 52-week high and oversold",
            "Deep drawdown with washed-out momentum. Historically, forward returns from here are above average but volatile.",
            [dd[i] <= -0.20 and r14[i] is not None and r14[i] < 35 for i in range(n)])
    elif dd[-1] <= -0.15:
        add("correction", "info", f"{sym}: in a correction ({dd[-1] * 100:.0f}% from high)",
            "Price is well below its 52-week high — consider scaling in rather than lump-sum.",
            [dd[i] <= -0.15 for i in range(n)])

    if m["cross"] == "golden" and m["cross_ago"] is not None and m["cross_ago"] <= 10:
        cond = [False] * n
        for i in range(1, n):
            if None not in (s50[i - 1], s200[i - 1], s50[i], s200[i]) and s50[i - 1] <= s200[i - 1] and s50[i] > s200[i]:
                cond[i] = True
        add("golden_cross", "opportunity", f"{sym}: golden cross",
            f"50-day average crossed above the 200-day {m['cross_ago']} trading days ago — long-term trend turning up.", cond)
    if m["cross"] == "death" and m["cross_ago"] is not None and m["cross_ago"] <= 10:
        add("death_cross", "warning", f"{sym}: death cross",
            f"50-day average crossed below the 200-day {m['cross_ago']} trading days ago — long-term trend turning down.")

    if rel and asset.get("equity", True) and rel["pct10y"] is not None:
        if rel["pct10y"] <= 0.05 and (rel["r3m"] or 0) > 0:
            add("rel_value_turn", "opportunity", f"{sym}: historically cheap vs S&P 500 and turning up",
                f"Relative price vs SPY is in the bottom {max(1, round(rel['pct10y'] * 100))}% of its ~10-year range and has outperformed over the last 3 months — mean-reversion setup.")
        elif rel["pct10y"] <= 0.05:
            add("rel_value", "info", f"{sym}: near 10-year low relative to S&P 500",
                "Deep relative value, but no turn yet — watch for relative strength to improve before committing.")

    if closes[-1] >= max(closes[-252:]) and min(dd[-126:]) <= -0.10:
        add("breakout", "info", f"{sym}: new 52-week high after a correction",
            "Recovered from a 10%+ drawdown to a new high — momentum confirmation.")

    if rsi_now > 75 and (m["vs_sma200"] or 0) > 0.15:
        add("overextended", "warning", f"{sym}: overextended",
            f"RSI {rsi_now:.0f} and {m['vs_sma200'] * 100:.0f}% above the 200-day average — historically a poor short-term entry; wait for a pullback.",
            [r14[i] is not None and r14[i] > 75 and s200[i] and closes[i] / s200[i] - 1 > 0.15 for i in range(n)])
    return out


def finalize_scores(results):
    """Cross-sectional momentum ranking + composite score. Mutates results in place."""
    moms = [r["metrics"]["mom12_1"] for r in results if r["metrics"]["mom12_1"] is not None]
    r3s = [r["metrics"]["r3m"] for r in results if r["metrics"]["r3m"] is not None]
    for r in results:
        m = r["metrics"]
        # Trend: above 200d, 50>200, 200d rising
        t = []
        if m["vs_sma200"] is not None:
            t.append(1 if m["vs_sma200"] > 0 else -1)
        if m["sma50"] and m["sma200"]:
            t.append(1 if m["sma50"] > m["sma200"] else -1)
        if m["sma200_slope"] is not None:
            t.append(clip(m["sma200_slope"] / 0.02))
        trend = sum(t) / len(t) if t else 0

        mo = []
        if m["mom12_1"] is not None and moms:
            mo.append(percentile_rank(moms, m["mom12_1"]) * 2 - 1)
        if m["r3m"] is not None and r3s:
            mo.append(percentile_rank(r3s, m["r3m"]) * 2 - 1)
        momentum = sum(mo) / len(mo) if mo else 0

        v = []
        if m["stretch_pct"] is not None:
            v.append(1 - 2 * m["stretch_pct"])
        if r["equity"] and m["rel"] and m["rel"]["pct10y"] is not None:
            v.append(1 - 2 * m["rel"]["pct10y"])
        if m["dd_max"] is not None:
            v.append(clip(-m["dd_max"] / 0.25) * 2 - 1 if m["dd_max"] < -0.05 else -0.5)
        value = sum(v) / len(v) if v else 0

        rsi_v = m["rsi14"] or 50
        if trend > 0:
            timing = clip((50 - rsi_v) / 20)
        else:
            timing = clip((50 - rsi_v) / 40, -0.5, 0.5)

        macro = r.pop("_macro")
        comps = {"trend": trend, "momentum": momentum, "value": value, "timing": timing, "macro": macro["score"]}
        total = sum(WEIGHTS[k] * comps[k] for k in WEIGHTS)
        score = round(50 + 50 * total)
        r["components"] = {k: round(val, 3) for k, val in comps.items()}
        r["macro_drivers"] = macro["drivers"]
        r["score"] = score
        r["rating"] = rating_for(score)
    results.sort(key=lambda x: -x["score"])
    return results
