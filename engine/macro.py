"""Turns FRED series into readable gauges, macro factor scores, a risk regime, and macro alerts."""
from datetime import date, timedelta

from .indicators import clip, percentile_rank, value_at_or_before, yoy_series


def _ago(d, days):
    return (date.fromisoformat(d) - timedelta(days=days)).isoformat()


def _change(series, days):
    if not series:
        return None
    last_d, last_v = series[-1]
    prev = value_at_or_before(series, _ago(last_d, days))
    return None if prev is None else last_v - prev


def _pct_change(series, days):
    if not series:
        return None
    last_d, last_v = series[-1]
    prev = value_at_or_before(series, _ago(last_d, days))
    return None if not prev else (last_v / prev - 1)


def _tail_years(series, years=10):
    if not series:
        return []
    cutoff = _ago(series[-1][0], int(365.25 * years))
    return [v for d, v in series if d >= cutoff]


def build_macro(raw, specs):
    """raw: {series_id: [(date, value)]}. Returns dict with gauges, factors, regime, alerts."""
    s = {}
    for spec in specs:
        series = raw.get(spec["id"]) or []
        if spec.get("scale"):
            series = [(d, v * spec["scale"]) for d, v in series]
        if spec["transform"] == "yoy":
            series = yoy_series(series)
        s[spec["id"]] = series

    # Buffett indicator: corporate equity market value / GDP (both quarterly, $mn vs $bn)
    mv, gdp = raw.get("NCBEILQ027S") or [], raw.get("GDP") or []
    buffett = []
    for d, v in mv:
        g = value_at_or_before(gdp, d)
        if g:
            buffett.append((d, v / 1000 / g * 100))
    s["BUFFETT"] = buffett

    def last(sid):
        return s[sid][-1][1] if s.get(sid) else None

    def pct(sid, years=10):
        if not s.get(sid):
            return None
        return percentile_rank(_tail_years(s[sid], years), s[sid][-1][1])

    gauges = []

    def gauge(sid, name, unit, state, read, extra=None):
        series = s.get(sid) or []
        if not series:
            return
        g = {
            "id": sid, "name": name, "unit": unit,
            "value": round(series[-1][1], 3), "date": series[-1][0],
            "pct10y": None if pct(sid) is None else round(pct(sid), 3),
            "chg3m": None if _change(series, 91) is None else round(_change(series, 91), 3),
            "state": state, "read": read,
            "spark": [round(v, 3) for _, v in series[-260:][::max(1, len(series[-260:]) // 60)]],
        }
        if extra:
            g.update(extra)
        gauges.append(g)

    alerts = []

    def alert(aid, severity, title, detail):
        alerts.append({"id": f"macro:{aid}", "scope": "macro", "severity": severity, "title": title, "detail": detail})

    # --- VIX
    vix = last("VIXCLS")
    if vix is not None:
        vix_peak_1m = max((v for d, v in s["VIXCLS"] if d >= _ago(s["VIXCLS"][-1][0], 30)), default=vix)
        if vix >= 30:
            state, read = "opportunity", "Fear is high. Historically, buying broad equities when VIX > 30 has produced above-average 6-12m returns."
            alert("vix_spike", "opportunity", f"VIX at {vix:.1f} — extreme fear",
                  "Contrarian signal: elevated fear has historically been a better-than-average entry point for broad equities (expect more volatility first).")
        elif vix_peak_1m >= 28 and vix < 22:
            state, read = "opportunity", "Volatility spike is fading — historically a favorable window to add equity exposure."
            alert("vix_fade", "opportunity", "Fear subsiding after a volatility spike",
                  f"VIX fell from {vix_peak_1m:.1f} to {vix:.1f} within a month; post-spike normalization has historically favored equities.")
        elif vix < 13:
            state, read = "warning", "Complacency — very low volatility. Protection is cheap; upside surprises less likely."
        else:
            state, read = "neutral", "Normal volatility regime."
        gauge("VIXCLS", "VIX (equity volatility)", "", state, read)

    # --- Yield curve
    curve, curve3m = last("T10Y2Y"), last("T10Y3M")
    if curve is not None:
        inverted_recent = any(v < 0 for d, v in s["T10Y2Y"] if d >= _ago(s["T10Y2Y"][-1][0], 365))
        if curve < 0:
            state, read = "warning", "Inverted curve. Has preceded every US recession since the 1970s (lead time 6-24 months)."
        elif inverted_recent and curve > 0:
            state, read = "warning", "Curve recently un-inverted. Historically, recessions often begin around the re-steepening."
            alert("curve_uninvert", "warning", "Yield curve has un-inverted",
                  "The 10y-2y spread turned positive after an inversion within the last year — a late-cycle warning; favors defensives, quality and Treasuries.")
        elif (_change(s["T10Y2Y"], 91) or 0) > 0.3:
            state, read = "positive", "Steepening curve — usually good for banks, value and small caps."
        else:
            state, read = "neutral", "Positively sloped curve."
        gauge("T10Y2Y", "Yield curve 10y-2y", "pp", state, read)
    if curve3m is not None:
        gauge("T10Y3M", "Yield curve 10y-3m", "pp", "warning" if curve3m < 0 else "neutral",
              "The Fed's preferred recession predictor; inverted = elevated risk." if curve3m < 0 else "Not inverted.")

    # --- Credit spreads
    hy = last("BAMLH0A0HYM2")
    if hy is not None:
        hy_chg = _change(s["BAMLH0A0HYM2"], 91) or 0
        hy_peak = max((v for d, v in s["BAMLH0A0HYM2"] if d >= _ago(s["BAMLH0A0HYM2"][-1][0], 120)), default=hy)
        if hy >= 6 and hy < hy_peak - 0.75:
            state, read = "opportunity", "Spreads are wide but falling from a peak — historically one of the best entry points for stocks, small caps and high-yield bonds."
            alert("credit_peak", "opportunity", "Credit stress peaking",
                  f"HY spread {hy:.2f}% is down from a recent {hy_peak:.2f}% peak — past credit-spread peaks have marked strong entry points for risk assets.")
        elif hy >= 6:
            state, read = "warning", "Credit stress — markets pricing elevated default risk."
        elif hy_chg > 1.0:
            state, read = "warning", "Spreads widening fast — risk-off pressure building."
            alert("credit_widening", "warning", "Credit spreads widening fast",
                  f"HY spread up {hy_chg:.2f}pp in 3 months. Widening credit spreads have preceded most equity drawdowns.")
        elif hy < 3.2:
            state, read = "warning", "Very tight spreads — investors are not being paid much for risk."
        else:
            state, read = "positive", "Healthy credit conditions."
        gauge("BAMLH0A0HYM2", "High-yield credit spread", "%", state, read)

    # --- Recession indicators
    sahm = last("SAHMREALTIME")
    if sahm is not None:
        if sahm >= 0.5:
            state, read = "danger", "Sahm rule triggered — historically signals a recession has begun."
            alert("sahm", "warning", "Sahm-rule recession signal triggered",
                  f"Sahm indicator at {sahm:.2f} (≥0.5). Favor defensives (staples, utilities, health care), Treasuries and gold; expect cyclicals to lag.")
        elif sahm >= 0.3:
            state, read = "warning", "Labor market softening — approaching the 0.5 recession threshold."
        else:
            state, read = "positive", "Labor market not signaling recession."
        gauge("SAHMREALTIME", "Sahm rule recession indicator", "pp", state, read)
    recp = last("RECPROUSM156N")
    if recp is not None:
        gauge("RECPROUSM156N", "Recession probability (smoothed)", "%",
              "danger" if recp > 50 else "warning" if recp > 20 else "positive",
              "Model-based probability the US is currently in recession.")
    un = last("UNRATE")
    if un is not None:
        chg = _change(s["UNRATE"], 365) or 0
        gauge("UNRATE", "Unemployment rate", "%", "warning" if chg > 0.5 else "neutral",
              f"{'Rising' if chg > 0 else 'Falling'} {abs(chg):.1f}pp over 12 months.")
    claims = last("ICSA")
    if claims is not None:
        chg = _pct_change(s["ICSA"], 182) or 0
        gauge("ICSA", "Initial jobless claims", "k", "warning" if chg > 0.2 else "neutral",
              f"{chg * 100:+.0f}% vs 6 months ago. A sustained 20%+ rise has preceded recessions.")

    # --- Rates & Fed
    ff = last("DFF")
    ff_chg = _change(s.get("DFF"), 182) if s.get("DFF") else None
    if ff is not None:
        if ff_chg is not None and ff_chg <= -0.5:
            state, read = "positive", "Fed is cutting. Easing cycles have historically favored small caps, REITs, homebuilders and long bonds (unless a recession hits)."
            alert("fed_easing", "info", "Fed easing cycle underway",
                  f"Fed funds down {abs(ff_chg):.2f}pp in 6 months. Rate-sensitive groups (small caps, real estate, homebuilders, utilities, bonds) tend to benefit.")
        elif ff_chg is not None and ff_chg >= 0.5:
            state, read = "warning", "Fed is hiking — headwind for long-duration and rate-sensitive assets."
        else:
            state, read = "neutral", "Policy rate roughly steady."
        gauge("DFF", "Fed funds rate", "%", state, read)
    for sid, name in (("DGS2", "2y Treasury yield"), ("DGS10", "10y Treasury yield")):
        if last(sid) is not None:
            gauge(sid, name, "%", "neutral", f"{(_change(s[sid], 182) or 0):+.2f}pp over 6 months.")
    ry = last("DFII10")
    if ry is not None:
        chg = _change(s["DFII10"], 182) or 0
        gauge("DFII10", "10y real yield (TIPS)", "%", "warning" if chg > 0.5 else "positive" if chg < -0.5 else "neutral",
              "Rising real yields pressure growth stocks and gold; falling real yields help them.")

    # --- Inflation
    cpi = last("CPIAUCSL")
    if cpi is not None:
        chg = _change(s["CPIAUCSL"], 182) or 0
        state = "warning" if cpi > 3.5 else "positive" if cpi < 2.8 else "neutral"
        gauge("CPIAUCSL", "CPI inflation (YoY)", "%", state,
              f"{'Accelerating' if chg > 0.2 else 'Decelerating' if chg < -0.2 else 'Stable'}. Hot inflation favors energy, materials, TIPS, commodities; cooling favors bonds and growth.")
    if last("PCEPILFE") is not None:
        gauge("PCEPILFE", "Core PCE inflation (YoY)", "%", "warning" if last("PCEPILFE") > 3 else "neutral",
              "The Fed's preferred inflation gauge (target 2%).")
    if last("T10YIE") is not None:
        gauge("T10YIE", "10y inflation breakeven", "%", "neutral", "Market-implied inflation expectation.")

    # --- Sentiment, liquidity, conditions
    sent = last("UMCSENT")
    if sent is not None:
        p = pct("UMCSENT", 30) or 0.5
        if p <= 0.1:
            state, read = "opportunity", "Sentiment near historic lows — a contrarian positive; stocks have averaged strong 12m returns from sentiment troughs."
            alert("sentiment_low", "opportunity", "Consumer sentiment at an extreme low",
                  f"UMich sentiment {sent:.1f} is in the bottom 10% of its history — historically a contrarian buy signal for equities.")
        else:
            state, read = "neutral", "Consumer sentiment."
        gauge("UMCSENT", "Consumer sentiment (UMich)", "", state, read)
    nfci = last("NFCI")
    if nfci is not None:
        gauge("NFCI", "Financial conditions (Chicago Fed)", "", "warning" if nfci > 0 else "positive",
              "Positive = tighter than average (headwind); negative = loose (tailwind).")
    m2 = last("M2SL")
    if m2 is not None:
        gauge("M2SL", "M2 money supply (YoY)", "%", "warning" if m2 < 0 else "neutral", "Liquidity growth; contraction is a headwind for risk assets.")
    ip = last("INDPRO")
    if ip is not None:
        gauge("INDPRO", "Industrial production (YoY)", "%", "warning" if ip < -1 else "neutral", "Manufacturing cycle; negative = contraction.")
    permits = last("PERMIT")
    if permits is not None:
        chg = _pct_change(s["PERMIT"], 365) or 0
        gauge("PERMIT", "Housing permits", "k", "warning" if chg < -0.15 else "neutral",
              f"{chg * 100:+.0f}% YoY. A leading indicator for the economy and homebuilders.")
    usd = last("DTWEXBGS")
    if usd is not None:
        chg = _pct_change(s["DTWEXBGS"], 182) or 0
        gauge("DTWEXBGS", "Trade-weighted US dollar", "", "neutral",
              f"{chg * 100:+.1f}% over 6 months. A falling dollar favors international/EM stocks, materials and gold.")
    oil = last("DCOILWTICO")
    if oil is not None:
        chg = _pct_change(s["DCOILWTICO"], 182) or 0
        gauge("DCOILWTICO", "WTI crude oil", "$", "neutral", f"{chg * 100:+.0f}% over 6 months.")
    if buffett:
        p = percentile_rank([v for _, v in buffett], buffett[-1][1])
        gauge("BUFFETT", "Buffett indicator (market cap / GDP)", "%",
              "warning" if p > 0.9 else "positive" if p < 0.3 else "neutral",
              f"Higher than {p * 100:.0f}% of readings since 2010. High = broad US equities expensive; long-run returns tend to be lower.")

    # --- Factor scores for the per-asset macro tilt
    def f_or0(x):
        return 0.0 if x is None else x

    hy_p = pct("BAMLH0A0HYM2")
    vix_p = pct("VIXCLS")
    rec_parts = []
    if sahm is not None:
        rec_parts.append(clip(sahm / 0.5, 0, 1))
    if curve3m is not None:
        rec_parts.append(1.0 if curve3m < 0 else 0.0)
    if recp is not None:
        rec_parts.append(clip(recp / 50, 0, 1))
    if nfci is not None:
        rec_parts.append(clip(nfci + 0.5, 0, 1))
    rec = sum(rec_parts) / len(rec_parts) if rec_parts else 0.3

    factors = {
        "curve_steepening": clip(f_or0(_change(s.get("T10Y2Y"), 91)) / 0.5),
        "rates_falling": clip(-f_or0(_change(s.get("DGS2"), 182)) / 1.0),
        "credit_stress": 0.0 if hy_p is None else clip((hy_p - 0.5) * 2),
        "recession_risk": clip(rec * 2 - 1),
        "inflation_pressure": 0.0 if cpi is None else clip((cpi - 2.5) / 2),
        "dollar_strength": clip(f_or0(_pct_change(s.get("DTWEXBGS"), 182)) / 0.05),
        "real_yields_rising": clip(f_or0(_change(s.get("DFII10"), 182)) / 0.75),
        "fear_contrarian": 0.0 if vix_p is None else clip((vix_p - 0.5) * 2),
        "oil_up": clip(f_or0(_pct_change(s.get("DCOILWTICO"), 182)) / 0.3),
    }

    # Overall risk regime: + is risk-on.
    parts = [-factors["credit_stress"] * 0.3, -factors["recession_risk"] * 0.4]
    if nfci is not None:
        parts.append(clip(-nfci * 2) * 0.15)
    if curve is not None:
        parts.append((0.15 if curve > 0 else -0.15))
    regime_score = round(sum(parts) * 100)
    if regime_score >= 25:
        regime = ("Risk-On", "Macro backdrop supports equities and cyclicals.")
    elif regime_score <= -25:
        regime = ("Risk-Off", "Macro backdrop favors defensives, quality, Treasuries and gold.")
    else:
        regime = ("Neutral", "Mixed macro signals — lean on asset-level trend and valuation.")

    for a in alerts:
        a["date"] = None
    return {
        "gauges": gauges,
        "factors": {k: round(v, 3) for k, v in factors.items()},
        "regime": {"label": regime[0], "score": regime_score, "summary": regime[1]},
        "alerts": alerts,
        "vix_series": s.get("VIXCLS") or [],
    }
