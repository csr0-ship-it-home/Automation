# Market Timing Signals

A self-updating website that tells you when the statistics say it may be a good (or bad) time to buy a
**sector, size segment (small / mid / large), style (value / growth), factor, international market, or
bond / real-asset class**. It pushes an alert to your phone or inbox when something changes.

It runs for free on GitHub: a scheduled GitHub Action pulls the data every weekday after the US close,
scores everything, writes JSON into `docs/data/`, and GitHub Pages serves the dashboard from `docs/`.
No servers, API keys or paid data.

> Educational tool, not investment advice. The back-tests use a single ~10-year sample, and past
> patterns may not repeat.

## What it tracks

**45 ETFs**
- A full 3×3 style box: Large, Mid and Small × Value, Blend and Growth (S&P 500/400/600 families), plus QQQ and IWM.
- The 11 sectors (SPDRs) plus semiconductors, regional banks, biotech and homebuilders.
- Factors: equal weight, quality, momentum, min-vol and dividend growth.
- International: developed, emerging, Europe, Japan, China and India.
- Bonds and real assets: long and intermediate Treasuries, TIPS, IG and high-yield credit, gold, commodities and REITs.

**Per asset:** 1W/1M/3M/6M/12M/3Y/YTD returns, 12-1 momentum, 50/200-day averages and their slope, golden and death crosses,
RSI(14), drawdown from the 52-week and 10-year high, 52-week range position, realized volatility and its percentile,
"stretch" (the percentile of today's distance from the 200-day average), relative strength vs the S&P 500 (3M, 12M and 10-year percentile)
and 2 years of price and moving-average charts.

**Relative-value pairs:** value vs growth (large and small), small vs large, mid vs large, equal vs cap weight, international vs US,
EM vs US, and discretionary vs staples.

**24 macro series from FRED:** VIX, the 10y-2y and 10y-3m yield curves, high-yield credit spreads, the Fed funds rate, 2y and 10y yields,
the 10y real yield, breakevens, CPI and core PCE, unemployment, the Sahm rule, jobless claims, recession probability,
consumer sentiment, the Chicago Fed financial conditions index, the dollar, oil, M2, industrial production, housing permits,
and the Buffett indicator (market cap / GDP).

## How it decides

Each asset gets a **0–100 score** built from five parts:

| Component | Weight | What it measures |
|---|---|---|
| Trend | 25% | Price above its 200-day average, 50-day above 200-day, and a rising 200-day average |
| Momentum | 20% | 12-1 month and 3-month returns, ranked against every other asset |
| Value | 20% | Cheapness vs the asset's own history and vs the S&P 500 (10-year percentiles), plus distance from its high |
| Timing | 15% | Oversold RSI inside an uptrend scores well; overbought scores badly |
| Macro | 20% | How the asset has tended to respond to current conditions (curve, credit, recession risk, inflation, dollar, real yields, fear, oil). The table is `engine/universe.py` → `SENSITIVITIES` |

Ratings: Strong Buy ≥70 · Buy ≥60 · Hold ≥45 · Caution ≥35 · Avoid <35.

**Alerts** fire on any of the following:
- Rating changes, such as an upgrade to Buy or a downgrade to Caution.
- Timing setups: an oversold pullback in an uptrend, capitulation (a 20%+ drawdown while oversold), a golden or death cross,
  a relative-value extreme that is turning up, a breakout to a new high after a correction, or an overextended price.
- Macro thresholds: VIX above 30 or a fading volatility spike, credit spreads peaking or widening fast, the yield curve un-inverting,
  the Sahm rule triggering, a Fed easing cycle, or consumer sentiment at an extreme low.

Every asset-level setup is **back-tested on that asset's own history**. The alert shows the average 3-month and 6-month
return and the win rate after past occurrences, next to a normal 3-month period. If a bullish setup has historically
*underperformed* for that asset, it is demoted to Info.

## Setup (about 5 minutes)

1. **Merge this branch** into your default branch.
2. **Turn on GitHub Pages:** Settings → Pages → Source "Deploy from a branch" → branch `main`, folder `/docs`.
   The site will be at `https://<your-username>.github.io/<repo>/`.
3. **Run it once:** Actions → "Update market signals" → Run workflow. This replaces the demo data with live data. After that it runs
   every weekday at 22:15 UTC.
4. **Phone alerts (easiest):** install the free [ntfy](https://ntfy.sh) app, subscribe to a hard-to-guess topic name
   (for example `market-signals-8f3k2`), then add a repository secret `NTFY_TOPIC` with that name
   (Settings → Secrets and variables → Actions).

Optional channels, all set as repository secrets:

| Secret | Purpose |
|---|---|
| `WEBHOOK_URL` | Slack or Discord incoming webhook |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL_TO` | Email, for example Gmail with an app password (`smtp.gmail.com`, `587`) |

Optional repository **variables**: set `ALERT_MIN_SEVERITY=info` to also get informational alerts (by default you only get
opportunities and warnings), and set `SITE_URL` if you host the site somewhere else.

Notifications only include alerts that are *new* since the previous run, so you won't get the same alert every day.
The site can also show browser notifications for new alerts when you open it ("Enable browser alerts").

## Run locally

```bash
python -m unittest discover -s tests   # tests (pure stdlib, no installs)
python -m engine.run --no-notify        # live data -> docs/data/
python -m engine.run --demo             # synthetic data, no network
python -m http.server -d docs 8000      # open http://localhost:8000
```

## Layout

```
engine/universe.py      what is tracked + macro sensitivities (edit to add tickers)
engine/data_sources.py  Yahoo Finance (Stooq fallback) prices, FRED macro, all keyless
engine/indicators.py    SMA, RSI, drawdown, percentiles, forward-return back-tests
engine/macro.py         macro gauges, factor scores, risk regime, macro alerts
engine/scoring.py       per-asset metrics, timing signals, composite score
engine/notify.py        ntfy / webhook / email
engine/run.py           orchestration -> docs/data/{latest,history,alert_log}.json
docs/                   the static website
```
