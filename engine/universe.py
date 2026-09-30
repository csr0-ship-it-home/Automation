"""Everything the engine tracks: ETFs by group, macro series, and each asset's macro sensitivities.

Macro factor keys (all scaled to [-1, 1], positive means "this condition is present"):
  curve_steepening   10y-2y spread widening over 3 months
  rates_falling      2y Treasury yield falling over 6 months (Fed easing)
  credit_stress      high-yield spreads high vs. their 10y history
  recession_risk     Sahm rule, yield-curve inversion, recession probability
  inflation_pressure CPI running hot / breakevens rising
  dollar_strength    trade-weighted dollar rising
  real_yields_rising 10y TIPS yield rising
  fear_contrarian    VIX elevated vs. history (historically a contrarian buy for equities)
  oil_up             crude oil rising
"""

BENCHMARK = "SPY"

GROUPS = [
    ("size_style", "Size & Style"),
    ("sector", "Sectors"),
    ("factor", "Factors"),
    ("intl", "International"),
    ("defensive", "Bonds & Real Assets"),
]

# symbol, name, group, extra attributes
ASSETS = [
    # 3x3 style box (size x style)
    {"symbol": "SPY", "name": "S&P 500 (Large Blend)", "group": "size_style", "size": "Large", "style": "Blend"},
    {"symbol": "IVE", "name": "S&P 500 Value (Large Value)", "group": "size_style", "size": "Large", "style": "Value"},
    {"symbol": "IVW", "name": "S&P 500 Growth (Large Growth)", "group": "size_style", "size": "Large", "style": "Growth"},
    {"symbol": "IJH", "name": "S&P 400 (Mid Blend)", "group": "size_style", "size": "Mid", "style": "Blend"},
    {"symbol": "IJJ", "name": "S&P 400 Value (Mid Value)", "group": "size_style", "size": "Mid", "style": "Value"},
    {"symbol": "IJK", "name": "S&P 400 Growth (Mid Growth)", "group": "size_style", "size": "Mid", "style": "Growth"},
    {"symbol": "IJR", "name": "S&P 600 (Small Blend)", "group": "size_style", "size": "Small", "style": "Blend"},
    {"symbol": "IJS", "name": "S&P 600 Value (Small Value)", "group": "size_style", "size": "Small", "style": "Value"},
    {"symbol": "IJT", "name": "S&P 600 Growth (Small Growth)", "group": "size_style", "size": "Small", "style": "Growth"},
    {"symbol": "QQQ", "name": "Nasdaq 100", "group": "size_style"},
    {"symbol": "IWM", "name": "Russell 2000", "group": "size_style"},
    # Sectors
    {"symbol": "XLK", "name": "Technology", "group": "sector"},
    {"symbol": "XLF", "name": "Financials", "group": "sector"},
    {"symbol": "XLE", "name": "Energy", "group": "sector"},
    {"symbol": "XLV", "name": "Health Care", "group": "sector"},
    {"symbol": "XLI", "name": "Industrials", "group": "sector"},
    {"symbol": "XLP", "name": "Consumer Staples", "group": "sector"},
    {"symbol": "XLY", "name": "Consumer Discretionary", "group": "sector"},
    {"symbol": "XLU", "name": "Utilities", "group": "sector"},
    {"symbol": "XLB", "name": "Materials", "group": "sector"},
    {"symbol": "XLRE", "name": "Real Estate", "group": "sector"},
    {"symbol": "XLC", "name": "Communication Services", "group": "sector"},
    {"symbol": "SMH", "name": "Semiconductors", "group": "sector"},
    {"symbol": "KRE", "name": "Regional Banks", "group": "sector"},
    {"symbol": "XBI", "name": "Biotech", "group": "sector"},
    {"symbol": "ITB", "name": "Homebuilders", "group": "sector"},
    # Factors
    {"symbol": "RSP", "name": "S&P 500 Equal Weight", "group": "factor"},
    {"symbol": "QUAL", "name": "Quality", "group": "factor"},
    {"symbol": "MTUM", "name": "Momentum", "group": "factor"},
    {"symbol": "USMV", "name": "Min Volatility", "group": "factor"},
    {"symbol": "SCHD", "name": "Dividend Growth", "group": "factor"},
    # International
    {"symbol": "EFA", "name": "Developed ex-US", "group": "intl"},
    {"symbol": "EEM", "name": "Emerging Markets", "group": "intl"},
    {"symbol": "VGK", "name": "Europe", "group": "intl"},
    {"symbol": "EWJ", "name": "Japan", "group": "intl"},
    {"symbol": "MCHI", "name": "China", "group": "intl"},
    {"symbol": "INDA", "name": "India", "group": "intl"},
    # Bonds & real assets
    {"symbol": "TLT", "name": "20+ Yr Treasuries", "group": "defensive", "equity": False},
    {"symbol": "IEF", "name": "7-10 Yr Treasuries", "group": "defensive", "equity": False},
    {"symbol": "TIP", "name": "TIPS", "group": "defensive", "equity": False},
    {"symbol": "LQD", "name": "IG Corporate Bonds", "group": "defensive", "equity": False},
    {"symbol": "HYG", "name": "High Yield Bonds", "group": "defensive", "equity": False},
    {"symbol": "GLD", "name": "Gold", "group": "defensive", "equity": False},
    {"symbol": "DBC", "name": "Commodities", "group": "defensive", "equity": False},
    {"symbol": "VNQ", "name": "US REITs", "group": "defensive"},
]

# Relative-value pairs: ratio of first/second; low percentile => first is historically cheap vs second.
PAIRS = [
    ("IVE", "IVW", "Large Value vs Large Growth"),
    ("IJS", "IJT", "Small Value vs Small Growth"),
    ("IJR", "SPY", "Small Caps vs Large Caps"),
    ("IJH", "SPY", "Mid Caps vs Large Caps"),
    ("RSP", "SPY", "Equal Weight vs Cap Weight"),
    ("EFA", "SPY", "International vs US"),
    ("EEM", "SPY", "Emerging vs US"),
    ("XLY", "XLP", "Discretionary vs Staples (risk appetite)"),
]

# FRED series pulled via the keyless fredgraph CSV endpoint.
# transform: "level" (latest value) or "yoy" (% change vs. 12 months earlier)
MACRO_SERIES = [
    {"id": "VIXCLS", "name": "VIX (equity volatility)", "unit": "", "transform": "level", "freq": "d"},
    {"id": "T10Y2Y", "name": "Yield curve 10y-2y", "unit": "pp", "transform": "level", "freq": "d"},
    {"id": "T10Y3M", "name": "Yield curve 10y-3m", "unit": "pp", "transform": "level", "freq": "d"},
    {"id": "BAMLH0A0HYM2", "name": "High-yield credit spread", "unit": "%", "transform": "level", "freq": "d"},
    {"id": "DFF", "name": "Fed funds rate", "unit": "%", "transform": "level", "freq": "d"},
    {"id": "DGS2", "name": "2y Treasury yield", "unit": "%", "transform": "level", "freq": "d"},
    {"id": "DGS10", "name": "10y Treasury yield", "unit": "%", "transform": "level", "freq": "d"},
    {"id": "DFII10", "name": "10y real yield (TIPS)", "unit": "%", "transform": "level", "freq": "d"},
    {"id": "T10YIE", "name": "10y inflation breakeven", "unit": "%", "transform": "level", "freq": "d"},
    {"id": "CPIAUCSL", "name": "CPI inflation (YoY)", "unit": "%", "transform": "yoy", "freq": "m"},
    {"id": "PCEPILFE", "name": "Core PCE inflation (YoY)", "unit": "%", "transform": "yoy", "freq": "m"},
    {"id": "UNRATE", "name": "Unemployment rate", "unit": "%", "transform": "level", "freq": "m"},
    {"id": "SAHMREALTIME", "name": "Sahm rule recession indicator", "unit": "pp", "transform": "level", "freq": "m"},
    {"id": "ICSA", "name": "Initial jobless claims", "unit": "k", "transform": "level", "freq": "w", "scale": 0.001},
    {"id": "RECPROUSM156N", "name": "Recession probability (smoothed)", "unit": "%", "transform": "level", "freq": "m"},
    {"id": "UMCSENT", "name": "Consumer sentiment (UMich)", "unit": "", "transform": "level", "freq": "m"},
    {"id": "NFCI", "name": "Financial conditions (Chicago Fed)", "unit": "", "transform": "level", "freq": "w"},
    {"id": "DTWEXBGS", "name": "Trade-weighted US dollar", "unit": "", "transform": "level", "freq": "d"},
    {"id": "DCOILWTICO", "name": "WTI crude oil", "unit": "$", "transform": "level", "freq": "d"},
    {"id": "M2SL", "name": "M2 money supply (YoY)", "unit": "%", "transform": "yoy", "freq": "m"},
    {"id": "INDPRO", "name": "Industrial production (YoY)", "unit": "%", "transform": "yoy", "freq": "m"},
    {"id": "PERMIT", "name": "Housing permits", "unit": "k", "transform": "level", "freq": "m"},
    {"id": "NCBEILQ027S", "name": "US corporate equity market value", "unit": "", "transform": "level", "freq": "q"},
    {"id": "GDP", "name": "Nominal GDP", "unit": "", "transform": "level", "freq": "q"},
]

# How each asset tends to respond to each macro factor (roughly -1..1). Unlisted assets use DEFAULT.
DEFAULT_EQUITY_SENS = {"recession_risk": -0.5, "credit_stress": -0.5, "fear_contrarian": 0.4, "real_yields_rising": -0.2}

SENSITIVITIES = {
    "SPY": DEFAULT_EQUITY_SENS,
    "QQQ": {"real_yields_rising": -0.7, "rates_falling": 0.4, "recession_risk": -0.4, "fear_contrarian": 0.4},
    "IVE": {"curve_steepening": 0.5, "inflation_pressure": 0.3, "recession_risk": -0.5, "credit_stress": -0.4},
    "IVW": {"real_yields_rising": -0.7, "rates_falling": 0.4, "recession_risk": -0.3, "fear_contrarian": 0.3},
    "IJH": {"rates_falling": 0.5, "credit_stress": -0.6, "recession_risk": -0.6, "curve_steepening": 0.3},
    "IJJ": {"curve_steepening": 0.5, "credit_stress": -0.6, "recession_risk": -0.6, "inflation_pressure": 0.3},
    "IJK": {"rates_falling": 0.5, "real_yields_rising": -0.5, "credit_stress": -0.5, "recession_risk": -0.5},
    "IJR": {"rates_falling": 0.7, "credit_stress": -0.7, "recession_risk": -0.6, "curve_steepening": 0.5, "dollar_strength": 0.2},
    "IJS": {"rates_falling": 0.6, "credit_stress": -0.7, "recession_risk": -0.6, "curve_steepening": 0.6, "inflation_pressure": 0.2},
    "IJT": {"rates_falling": 0.7, "real_yields_rising": -0.5, "credit_stress": -0.6, "recession_risk": -0.6},
    "IWM": {"rates_falling": 0.7, "credit_stress": -0.7, "recession_risk": -0.6, "curve_steepening": 0.5, "dollar_strength": 0.2},
    "XLK": {"real_yields_rising": -0.6, "rates_falling": 0.4, "recession_risk": -0.3},
    "SMH": {"real_yields_rising": -0.5, "recession_risk": -0.6, "dollar_strength": -0.3},
    "XLF": {"curve_steepening": 0.8, "credit_stress": -0.6, "recession_risk": -0.5},
    "KRE": {"curve_steepening": 0.9, "credit_stress": -0.8, "recession_risk": -0.6},
    "XLE": {"oil_up": 0.9, "inflation_pressure": 0.6, "dollar_strength": -0.3},
    "XLV": {"recession_risk": 0.4, "credit_stress": 0.2},
    "XBI": {"rates_falling": 0.7, "credit_stress": -0.5, "real_yields_rising": -0.5},
    "XLI": {"recession_risk": -0.6, "curve_steepening": 0.3, "dollar_strength": -0.2},
    "XLP": {"recession_risk": 0.6, "credit_stress": 0.3, "inflation_pressure": -0.2},
    "XLY": {"recession_risk": -0.7, "rates_falling": 0.4, "oil_up": -0.3},
    "ITB": {"rates_falling": 0.9, "recession_risk": -0.5, "real_yields_rising": -0.5},
    "XLU": {"rates_falling": 0.7, "recession_risk": 0.5, "real_yields_rising": -0.4},
    "XLB": {"inflation_pressure": 0.5, "dollar_strength": -0.5, "recession_risk": -0.4},
    "XLRE": {"rates_falling": 0.8, "real_yields_rising": -0.6, "credit_stress": -0.3},
    "VNQ": {"rates_falling": 0.8, "real_yields_rising": -0.6, "credit_stress": -0.3},
    "XLC": {"real_yields_rising": -0.4, "recession_risk": -0.4},
    "RSP": {"rates_falling": 0.4, "credit_stress": -0.5, "recession_risk": -0.5, "curve_steepening": 0.3},
    "QUAL": {"recession_risk": 0.1, "credit_stress": -0.3, "fear_contrarian": 0.3},
    "MTUM": {"recession_risk": -0.3, "fear_contrarian": 0.2},
    "USMV": {"recession_risk": 0.5, "credit_stress": 0.2, "rates_falling": 0.3},
    "SCHD": {"recession_risk": 0.1, "inflation_pressure": 0.2, "curve_steepening": 0.2},
    "EFA": {"dollar_strength": -0.7, "recession_risk": -0.4},
    "VGK": {"dollar_strength": -0.7, "recession_risk": -0.4, "curve_steepening": 0.2},
    "EWJ": {"dollar_strength": -0.3, "recession_risk": -0.4},
    "EEM": {"dollar_strength": -0.8, "credit_stress": -0.4, "oil_up": 0.2},
    "MCHI": {"dollar_strength": -0.6, "credit_stress": -0.4},
    "INDA": {"dollar_strength": -0.5, "oil_up": -0.4},
    "TLT": {"rates_falling": 0.9, "recession_risk": 0.7, "inflation_pressure": -0.6},
    "IEF": {"rates_falling": 0.8, "recession_risk": 0.6, "inflation_pressure": -0.5},
    "TIP": {"inflation_pressure": 0.6, "real_yields_rising": -0.7},
    "LQD": {"rates_falling": 0.6, "credit_stress": -0.4, "inflation_pressure": -0.4},
    "HYG": {"credit_stress": -0.8, "recession_risk": -0.6},
    "GLD": {"real_yields_rising": -0.8, "dollar_strength": -0.6, "inflation_pressure": 0.3, "credit_stress": 0.3},
    "DBC": {"inflation_pressure": 0.7, "oil_up": 0.7, "dollar_strength": -0.5},
}


def sensitivities(symbol):
    return SENSITIVITIES.get(symbol, DEFAULT_EQUITY_SENS)


def is_equity(asset):
    return asset.get("equity", True)
