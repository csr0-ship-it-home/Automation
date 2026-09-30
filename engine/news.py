"""Market headlines from public RSS feeds (no keys), tagged by theme and linked to tracked funds."""
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .data_sources import _get

FEEDS = [
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("CNBC Markets", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ("CNBC Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Google News", "https://news.google.com/rss/search?q=stock+market+OR+%22federal+reserve%22+OR+economy+when:2d&hl=en-US&gl=US&ceid=US:en"),
]

SYMBOL_FEED = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"

# theme -> (regex, related fund symbols, related macro gauge ids)
THEMES = {
    "Fed & interest rates": (r"\bfed\b|fomc|powell|rate cuts?|rate hikes?|interest rates?|treasur(y|ies)|bond yields?|10-year",
                             ["TLT", "IEF", "ITB", "XLRE", "IWM", "XLU"], ["DFF", "DGS2", "DGS10"]),
    "Inflation": (r"inflation|\bcpi\b|\bpce\b|consumer prices|price pressures", ["TIP", "XLE", "DBC", "XLB"], ["CPIAUCSL", "T10YIE"]),
    "Jobs & economy": (r"\bjobs?\b|payrolls?|unemployment|jobless|\bgdp\b|recession|retail sales|consumer spending|economy|economic",
                       ["XLY", "XLP", "XLI", "IWM"], ["UNRATE", "ICSA", "SAHMREALTIME"]),
    "Energy & oil": (r"\boil\b|crude|opec|gasoline|natural gas|energy stocks", ["XLE", "DBC"], ["DCOILWTICO"]),
    "Tech & AI": (r"\bA\.?I\.?\b|artificial intelligence|nvidia|chips?\b|semiconductor|apple|microsoft|alphabet|google|meta\b|amazon|tech stocks",
                  ["XLK", "SMH", "QQQ", "IVW", "XLC"], []),
    "Banks & credit": (r"\bbanks?\b|lenders?|credit|defaults?|\bloans?\b|private credit", ["XLF", "KRE", "HYG", "LQD"], ["BAMLH0A0HYM2"]),
    "Housing": (r"housing|mortgages?|home sales|homebuilders?|home prices", ["ITB", "XLRE", "VNQ"], ["PERMIT"]),
    "China & trade": (r"china|chinese|tariffs?|trade war|trade deal|exports?|imports?", ["MCHI", "EEM", "XLI"], []),
    "Earnings": (r"earnings|quarterly results|profit|revenue|guidance|beats estimates|misses estimates", ["SPY", "QQQ"], []),
    "Dollar & global markets": (r"dollar|\beuro\b|\byen\b|europe|european|japan|emerging markets|india", ["EFA", "VGK", "EWJ", "EEM", "INDA"], ["DTWEXBGS"]),
    "Health care": (r"health|pharma|drugmakers?|\bfda\b|biotech|medicare", ["XLV", "XBI"], []),
    "Gold & commodities": (r"\bgold\b|silver|copper|commodit", ["GLD", "DBC", "XLB"], []),
    "Market sentiment": (r"sell-?off|rally|volatility|\bvix\b|record high|all-time high|correction|bear market|bull market|stocks (fall|drop|rise|jump|slide|surge)",
                         ["SPY"], ["VIXCLS"]),
}
_THEME_RE = {k: re.compile(v[0], re.I if k != "Tech & AI" else 0) for k, v in THEMES.items()}
# "Tech & AI" is case-sensitive only for the bare "AI" token; add case-insensitive words separately
_TECH_WORDS = re.compile(THEMES["Tech & AI"][0].split("|", 1)[1], re.I)


def _themes_for(text):
    out = []
    for k, rx in _THEME_RE.items():
        if rx.search(text) or (k == "Tech & AI" and _TECH_WORDS.search(text)):
            out.append(k)
    return out


def parse_rss(text, source):
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link.startswith(("http://", "https://")):
            continue
        src = (item.findtext("source") or "").strip() or source
        if source == "Google News" and " - " in title:
            title, _, tail = title.rpartition(" - ")
            src = src if src != "Google News" else tail
        when = None
        raw = item.findtext("pubDate")
        if raw:
            try:
                when = parsedate_to_datetime(raw)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                when = None
        out.append({"title": title, "link": link, "source": src, "published": when.isoformat() if when else None})
    return out


def _norm(title):
    return re.sub(r"[^a-z0-9 ]", "", title.lower())[:80]


def _fetch(feed):
    name, url = feed
    try:
        return parse_rss(_get(url, retries=2, timeout=20), name)
    except Exception as exc:
        print(f"WARN news feed {name}: {exc}")
        return []


def tag_and_rank(items, now, max_age_days=3, limit=60):
    cutoff = now - timedelta(days=max_age_days)
    seen, out = set(), []
    for it in items:
        key = _norm(it["title"])
        if key in seen:
            continue
        seen.add(key)
        if it.get("published") and datetime.fromisoformat(it["published"]) < cutoff:
            continue
        it["themes"] = _themes_for(it["title"])
        out.append(it)
    out.sort(key=lambda x: x.get("published") or "", reverse=True)
    return out[:limit]


def fetch_headlines(now, symbols=()):
    """General market headlines plus per-symbol headlines for `symbols`."""
    with ThreadPoolExecutor(max_workers=6) as ex:
        general = [i for batch in ex.map(_fetch, FEEDS) for i in batch]
        per_symbol = dict(zip(symbols, ex.map(lambda s: _fetch(("Yahoo Finance", SYMBOL_FEED.format(symbol=s))), symbols)))
    return tag_and_rank(general, now), {s: tag_and_rank(v, now, max_age_days=10, limit=6) for s, v in per_symbol.items()}


def theme_summary(items):
    counts = {}
    for it in items:
        for t in it["themes"]:
            counts.setdefault(t, []).append(it)
    ranked = sorted(counts.items(), key=lambda kv: -len(kv[1]))
    return [{"theme": t, "count": len(v), "symbols": THEMES[t][1], "gauges": THEMES[t][2]} for t, v in ranked]


def demo_headlines(now):
    samples = [
        ("Fed officials signal patience on further rate cuts as inflation cools", ["Fed & interest rates", "Inflation"]),
        ("Oil slides as OPEC+ weighs output increase", ["Energy & oil"]),
        ("Chipmakers rally on strong AI demand outlook", ["Tech & AI"]),
        ("Regional banks gain after credit quality holds up in earnings", ["Banks & credit", "Earnings"]),
        ("Mortgage rates dip to lowest level in months, lifting homebuilders", ["Housing", "Fed & interest rates"]),
        ("Jobless claims tick higher, adding to signs of a cooling labor market", ["Jobs & economy"]),
        ("Dollar weakens as investors rotate into European and emerging markets", ["Dollar & global markets"]),
        ("Gold hits record high on falling real yields", ["Gold & commodities"]),
    ]
    return [{"title": f"[Demo] {t}", "link": "https://example.com/", "source": "Demo",
             "published": (now - timedelta(hours=3 * i)).isoformat(), "themes": th} for i, (t, th) in enumerate(samples)]
