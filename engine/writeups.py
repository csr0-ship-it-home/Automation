"""Plain-English writeups built from the numbers: a headline/market brief and a top-5 thesis for each leader."""
from .news import THEMES

FACTOR_TEXT = {  # factor -> (when positive, when negative)
    "curve_steepening": ("the yield curve is steepening", "the yield curve is flattening"),
    "rates_falling": ("short-term rates are falling", "short-term rates are rising"),
    "credit_stress": ("credit spreads are elevated", "credit markets are calm"),
    "recession_risk": ("recession indicators are elevated", "recession indicators are quiet"),
    "inflation_pressure": ("inflation is running hot", "inflation is cooling"),
    "dollar_strength": ("the dollar is strengthening", "the dollar is weakening"),
    "real_yields_rising": ("real yields are rising", "real yields are falling"),
    "fear_contrarian": ("fear (VIX) is elevated, a contrarian positive", "volatility is subdued"),
    "oil_up": ("oil prices are rising", "oil prices are falling"),
}


def _p(x, d=1):
    return "n/a" if x is None else f"{x * 100:+.{d}f}%"


def _factor_phrase(factor, factors):
    pos, neg = FACTOR_TEXT.get(factor, (factor, factor))
    return pos if factors.get(factor, 0) >= 0 else neg


def _component_reason(key, a, n_assets, factors):
    m = a["metrics"]
    if key == "trend":
        bits = []
        if m["vs_sma200"] is not None:
            bits.append(f"price is {abs(m['vs_sma200']) * 100:.1f}% {'above' if m['vs_sma200'] >= 0 else 'below'} its 200-day average")
        if m["sma50"] and m["sma200"]:
            bits.append("the 50-day average is " + ("above" if m["sma50"] > m["sma200"] else "below") + " the 200-day")
        if m["sma200_slope"] is not None:
            bits.append("the 200-day average is " + ("rising" if m["sma200_slope"] > 0 else "falling"))
        return "Trend: " + ", ".join(bits) + "."
    if key == "momentum":
        return (f"Momentum: {_p(m['mom12_1'])} over the last 12 months (excluding the latest month) and {_p(m['r3m'])} over 3 months, "
                f"ranking it near the top of the {n_assets} funds tracked.")
    if key == "value":
        bits = []
        if m["stretch_pct"] is not None:
            pc = round(m["stretch_pct"] * 100)
            bits.append(f"its distance from the 200-day average is at the {pc}th percentile of its history"
                        + (" (not stretched)" if pc < 60 else " (somewhat extended)" if pc < 85 else " (stretched)"))
        if a["equity"] and m["rel"] and m["rel"]["pct10y"] is not None:
            bits.append(f"relative to the S&P 500 it sits at the {round(m['rel']['pct10y'] * 100)}th percentile of its ~10-year range")
        if m["dd_max"] is not None and m["dd_max"] < -0.05:
            bits.append(f"it's still {abs(m['dd_max']) * 100:.0f}% below its 10-year high")
        return "Value: " + "; ".join(bits) + "." if bits else "Value: reasonably priced versus its own history."
    if key == "timing":
        return f"Timing: RSI is {m['rsi14']}, " + ("a pullback within an uptrend, which is historically a better entry than chasing strength."
                                                  if (m["rsi14"] or 50) < 45 else "neither overbought nor oversold.")
    if key == "macro":
        good = [d for d in a.get("macro_drivers", []) if d["impact"] > 0.05][:3]
        if not good:
            return "Macro: the current backdrop is broadly neutral for it."
        return "Macro: tailwinds because " + ", ".join(_factor_phrase(d["factor"], factors) for d in good) + "."
    return ""


def _risks(a, factors):
    m, out = a["metrics"], []
    comps = a["components"]
    weakest = min(comps, key=comps.get)
    if comps[weakest] < 0:
        out.append({"trend": "The long-term trend isn't confirmed yet, so the rebound could stall.",
                    "momentum": "Momentum lags the rest of the market; it may take time to be rewarded.",
                    "value": "It's no longer cheap: much of the good news may already be priced in.",
                    "timing": "Short-term overbought: waiting for a pullback may give a better entry.",
                    "macro": "The macro backdrop is a headwind."}[weakest])
    bad = [d for d in a.get("macro_drivers", []) if d["impact"] < -0.05][:2]
    if bad:
        out.append("Macro headwinds: " + ", ".join(_factor_phrase(d["factor"], factors) for d in bad) + ".")
    if m["r3m"] is not None and m["r3m"] < -0.03:
        out.append(f"Short-term momentum has faded ({_p(m['r3m'])} over 3 months); the score leans on longer-term strength.")
    if (m["rsi14"] or 50) > 70:
        out.append(f"RSI {m['rsi14']} is overbought, so short-term pullbacks are common from here.")
    if m["vol_pct"] is not None and m["vol_pct"] > 0.8:
        out.append(f"Volatility is high for this fund ({round(m['vol_pct'] * 100)}th percentile of the last 5 years); size positions accordingly.")
    if m["vs_sma200"] is not None and m["vs_sma200"] > 0.15:
        out.append(f"It's {m['vs_sma200'] * 100:.0f}% above its 200-day average, which is extended.")
    for s in a["signals"]:
        if s["severity"] == "warning":
            out.append(s["title"].split(": ", 1)[-1].capitalize() + ".")
    return out or ["No major red flags in the data today; the main risk is a broad market sell-off."]


def _watch(a):
    m = a["metrics"]
    out = []
    if m["sma200"]:
        out.append(f"A close below the 200-day average (about ${m['sma200']:,.2f}) would break the uptrend.")
    out.append("The score dropping below 60 would remove the Buy rating (you'll get an alert).")
    if a["equity"] and m["rel"] and m["rel"]["r3m"] is not None:
        if m["rel"]["r3m"] >= 0:
            out.append(f"Relative strength vs the S&P 500 ({_p(m['rel']['r3m'])} over 3 months) turning negative.")
        else:
            out.append(f"Whether it starts outperforming the S&P 500 again (it's {_p(m['rel']['r3m'])} relative over 3 months).")
    return out


def top5(latest, headlines, symbol_news):
    assets = latest["assets"][:5]
    n, factors = len(latest["assets"]), latest["macro_factors"]
    out = []
    for rank, a in enumerate(assets, 1):
        comps = sorted(a["components"].items(), key=lambda kv: -kv[1])
        strengths = [_component_reason(k, a, n, factors) for k, v in comps if v > 0.1][:3]
        related = [h for h in headlines if any(a["symbol"] in THEMES[t][1] for t in h["themes"])][:4]
        own = symbol_news.get(a["symbol"], [])[:4]
        signals = [{"title": s["title"], "severity": s["severity"], "backtest": s.get("backtest")} for s in a["signals"]]
        m = a["metrics"]
        summary = (f"{a['name']} ({a['symbol']}) ranks #{rank} of {n} with a score of {a['score']} ({a['rating']}). "
                   f"It's {_p(m['r3m'])} over 3 months and {_p(m['r12m'])} over 12 months. "
                   f"Its strongest pillars are {' and '.join(k for k, v in comps[:2])}.")
        out.append({"rank": rank, "symbol": a["symbol"], "name": a["name"], "score": a["score"], "rating": a["rating"],
                    "summary": summary, "strengths": strengths, "risks": _risks(a, factors), "watch": _watch(a),
                    "signals": signals, "headlines": own + [h for h in related if h not in own][: max(0, 5 - len(own))]})
    return out


def news_brief(latest, headlines, themes):
    r = latest["regime"]
    gauges = {g["id"]: g for g in latest["gauges"]}
    by_sym = {a["symbol"]: a for a in latest["assets"]}
    opp = sum(1 for a in latest["alerts"] if a["severity"] == "opportunity")
    warn = sum(1 for a in latest["alerts"] if a["severity"] == "warning")
    paras = [f"The data puts the market in a {r['label']} regime ({r['score']:+d}). {r['summary']} "
             f"There are {opp} opportunity and {warn} warning alerts active."]
    if themes:
        top = ", ".join(f"{t['theme'].lower()} ({t['count']})" for t in themes[:3])
        paras.append(f"The news flow over the last few days is dominated by {top}.")
    theme_notes = []
    for t in themes[:6]:
        facts = []
        for gid in t["gauges"]:
            g = gauges.get(gid)
            if g:
                facts.append(f"{g['name']} {g['value']:,.2f}{g['unit'] if g['unit'] not in ('', '$', 'k') else ''} ({g['read'].split('. ')[0].rstrip('.').lower()})")
        funds = [by_sym[s] for s in t["symbols"] if s in by_sym]
        funds.sort(key=lambda a: -a["score"])
        fund_txt = ", ".join(f"{a['symbol']} {a['score']} ({a['rating']})" for a in funds[:4])
        note = f"What the data says: {'; '.join(facts)}. " if facts else ""
        if fund_txt:
            note += f"Most exposed funds we track: {fund_txt}."
        theme_notes.append({"theme": t["theme"], "count": t["count"], "note": note.strip(), "symbols": t["symbols"]})
    return {"headline": f"{r['label']} backdrop: what today's news means for your watchlist", "paragraphs": paras,
            "themes": theme_notes}
