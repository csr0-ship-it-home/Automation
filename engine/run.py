"""Entry point: python -m engine.run [--demo] [--no-notify] [--out docs/data]"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import ai, data_sources, demo, news, notify, writeups
from .indicators import pct_change, percentile_rank
from .macro import build_macro
from .scoring import analyze_asset, finalize_scores
from .universe import ASSETS, BENCHMARK, GROUPS, MACRO_SERIES, PAIRS

UPGRADE = {"Strong Buy", "Buy"}
DOWNGRADE = {"Caution", "Avoid"}


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _fetch_all(fn, keys, workers=6):
    out, errors = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {k: ex.submit(fn, k) for k in keys}
        for k, f in futs.items():
            try:
                out[k] = f.result()
            except Exception as exc:
                errors[k] = str(exc)[:300]
    return out, errors


def build(prices, macro_raw, prev, now, is_demo=False, errors=None):
    macro = build_macro(macro_raw, MACRO_SERIES)
    bench = prices.get(BENCHMARK)
    results = [analyze_asset(a, prices[a["symbol"]], bench, macro["factors"])
               for a in ASSETS if len(prices.get(a["symbol"]) or []) > 260]
    finalize_scores(results)

    pairs = []
    for a, b, label in PAIRS:
        if a in prices and b in prices:
            bmap = dict(prices[b])
            ratio = [c / bmap[d] for d, c in prices[a] if d in bmap and bmap[d]]
            if len(ratio) > 260:
                p = percentile_rank(ratio, ratio[-1])
                pairs.append({"a": a, "b": b, "label": label, "pct10y": round(p, 3),
                              "r3m": round(pct_change(ratio, 63), 4), "r12m": round(pct_change(ratio, 252), 4),
                              "spark": [round(x / ratio[-1260 if len(ratio) > 1260 else 0] * 100, 2)
                                        for x in ratio[-1260:][::20]],
                              "read": (f"{a} is historically cheap vs {b}" if p < 0.15 else
                                       f"{a} is historically expensive vs {b}" if p > 0.85 else "Within normal range")})

    today = now.strftime("%Y-%m-%d")
    alerts = list(macro["alerts"])
    for r in results:
        alerts.extend({**s, "scope": "asset", "symbol": r["symbol"]} for s in r["signals"])
    prev_ratings = {a["symbol"]: a["rating"] for a in prev.get("assets", [])}
    for r in results:
        old = prev_ratings.get(r["symbol"])
        if old and old != r["rating"]:
            if r["rating"] in UPGRADE and old not in UPGRADE:
                alerts.append({"id": f"upgrade:{r['symbol']}:{r['rating']}", "scope": "asset", "symbol": r["symbol"],
                               "severity": "opportunity", "title": f"{r['symbol']} ({r['name']}) upgraded to {r['rating']}",
                               "detail": f"Composite score {r['score']} (was rated {old})."})
            elif r["rating"] in DOWNGRADE and old not in DOWNGRADE:
                alerts.append({"id": f"downgrade:{r['symbol']}:{r['rating']}", "scope": "asset", "symbol": r["symbol"],
                               "severity": "warning", "title": f"{r['symbol']} ({r['name']}) downgraded to {r['rating']}",
                               "detail": f"Composite score {r['score']} (was rated {old})."})

    prev_seen = {a["id"]: a.get("first_seen") for a in prev.get("alerts", [])}
    for a in alerts:
        a["first_seen"] = prev_seen.get(a["id"]) or today
        a["new"] = a["id"] not in prev_seen
    sev_order = {"opportunity": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (not a["new"], sev_order.get(a["severity"], 3), a["id"]))

    latest = {
        "generated_at": now.isoformat(timespec="seconds"),
        "demo": is_demo,
        "groups": [{"id": g, "label": l} for g, l in GROUPS],
        "regime": macro["regime"],
        "macro_factors": macro["factors"],
        "gauges": macro["gauges"],
        "pairs": pairs,
        "alerts": alerts,
        "assets": results,
        "errors": errors or {},
    }
    return latest


def add_commentary(latest, now, is_demo=False):
    """Headlines tab + top-5 writeups (data-driven, plus Claude-written when ANTHROPIC_API_KEY is set)."""
    top_syms = [a["symbol"] for a in latest["assets"][:5]]
    if is_demo:
        headlines, symbol_news = news.demo_headlines(now), {}
    else:
        headlines, symbol_news = news.fetch_headlines(now, top_syms)
    themes = news.theme_summary(headlines)
    top5 = writeups.top5(latest, headlines, symbol_news)
    brief = writeups.news_brief(latest, headlines, themes)
    written = None if is_demo else ai.write(latest, headlines, themes, top5, symbol_news)
    if written:
        brief["ai"] = {**written["market_brief"], "model": written.get("model")}
        takeaways = {t["theme"]: t["takeaway"] for t in written.get("themes", [])}
        for t in brief["themes"]:
            if t["theme"] in takeaways:
                t["ai"] = takeaways[t["theme"]]
        by_sym = {t["symbol"]: t for t in written.get("top5", [])}
        for t in top5:
            if t["symbol"] in by_sym:
                t["ai"] = {k: by_sym[t["symbol"]][k] for k in ("thesis", "risks", "watch")}
    latest["news"] = {"headlines": headlines, "themes": themes, "brief": brief,
                      "ai_enabled": bool(written)}
    latest["top5"] = top5


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="use synthetic data (no network)")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "docs", "data"))
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    latest_path = os.path.join(args.out, "latest.json")
    history_path = os.path.join(args.out, "history.json")
    log_path = os.path.join(args.out, "alert_log.json")
    prev = _load(latest_path, {})
    if args.demo or prev.get("demo"):
        prev = {}  # never diff against demo data
    now = datetime.now(timezone.utc)

    symbols = [a["symbol"] for a in ASSETS]
    if args.demo:
        prices, macro_raw, errors = demo.prices(symbols), demo.macro(MACRO_SERIES), {}
    else:
        prices, perr = _fetch_all(data_sources.fetch_prices, symbols)
        macro_raw, merr = _fetch_all(data_sources.fetch_fred, [m["id"] for m in MACRO_SERIES])
        errors = {**perr, **merr}
        for k, v in errors.items():
            print(f"WARN fetch {k}: {v}", file=sys.stderr)
        if BENCHMARK not in prices or len(prices) < len(symbols) // 2:
            print("ERROR: too many price fetches failed; keeping previous data", file=sys.stderr)
            return 1

    latest = build(prices, macro_raw, prev, now, is_demo=args.demo, errors=errors)
    try:
        add_commentary(latest, now, is_demo=args.demo)
    except Exception as exc:  # commentary is best-effort; never block the data update
        print(f"WARN commentary: {exc}", file=sys.stderr)
    with open(latest_path, "w") as f:
        json.dump(latest, f, separators=(",", ":"))

    history = [] if args.demo or not prev else _load(history_path, [])
    day = now.strftime("%Y-%m-%d")
    history = [h for h in history if h["date"] != day]
    history.append({"date": day, "regime": latest["regime"]["score"],
                    "scores": {a["symbol"]: a["score"] for a in latest["assets"]}})
    with open(history_path, "w") as f:
        json.dump(history[-730:], f, separators=(",", ":"))

    new = [a for a in latest["alerts"] if a["new"]]
    log = [] if args.demo or not prev else _load(log_path, [])
    log = [{"date": day, **{k: a.get(k) for k in ("id", "severity", "title", "detail", "symbol")}} for a in new] + log
    with open(log_path, "w") as f:
        json.dump(log[:500], f, separators=(",", ":"))

    print(f"{len(latest['assets'])} assets scored, regime {latest['regime']['label']}, "
          f"{len(latest['alerts'])} active alerts ({len(new)} new)")
    if not args.demo and not args.no_notify and prev:
        notify.send(new, latest["regime"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
