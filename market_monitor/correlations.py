"""
Global tech watchlist for the daily brief.

NOTE: This module also still defines the legacy Asian-mover → EU-stock
CORRELATION_RULES below. Those rules are German/DAX-specific and are no
longer surfaced in the live daily_brief.py output (the brief renders the
watchlist only), so they're left dormant rather than rewritten for the
global tech universe.
"""

# ---------------------------------------------------------------------------
# Watchlist: global tech names shown in the daily brief
# ---------------------------------------------------------------------------

# Global tech watchlist — US megacap technology names.
# (Kept the EU_WATCHLIST symbol name for backward-compat with the legacy
#  main.py/formatter.py pipeline; the live daily_brief.py only needs the
#  dict contents + get_all_watchlist_symbols().)
EU_WATCHLIST: dict[str, str] = {
    # US megacap tech
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "NVDA":  "Nvidia",
    "GOOGL": "Alphabet (Google)",
    "AMZN":  "Amazon",
    "META":  "Meta Platforms",
    "TSLA":  "Tesla",
    "AVGO":  "Broadcom",
    "AMD":   "AMD",
    "ORCL":  "Oracle",
    "CRM":   "Salesforce",
    "ADBE":  "Adobe",
    "NFLX":  "Netflix",
    "QCOM":  "Qualcomm",
    "CSCO":  "Cisco",
    "INTC":  "Intel",
}

# ---------------------------------------------------------------------------
# Correlation rules: which EU tickers respond to which Asian mover + direction
# ---------------------------------------------------------------------------
# Each entry: (asian_symbol, direction) → [(eu_ticker, reason, beta_estimate)]
# direction: "up" | "down" | "any"
# beta_estimate: rough expected move in EU stock per 1% move in Asian index

CORRELATION_MAP: list[dict] = [
    # --- Nikkei 225 (^N225) ---
    # Japanese auto exports → European automakers share direction (competition/demand signal)
    {"asian": "^N225", "direction": "any",  "eu": "BMW.DE",   "reason": "Auto sector demand signal; Nikkei auto weighting", "beta": 0.45},
    {"asian": "^N225", "direction": "any",  "eu": "MBG.DE",   "reason": "Auto sector demand signal; Japan luxury car market", "beta": 0.40},
    {"asian": "^N225", "direction": "any",  "eu": "VOW3.DE",  "reason": "Auto sector demand signal; VW Asia exposure", "beta": 0.35},
    {"asian": "^N225", "direction": "any",  "eu": "IFX.DE",   "reason": "Semiconductor supply chain; Sony/Panasonic links", "beta": 0.55},
    {"asian": "^N225", "direction": "any",  "eu": "SAP.DE",   "reason": "Tech sentiment spillover; Nikkei tech heavy", "beta": 0.30},
    {"asian": "^N225", "direction": "any",  "eu": "SIE.DE",   "reason": "Industrial exports to Japan; factory automation", "beta": 0.35},
    {"asian": "^N225", "direction": "any",  "eu": "ALV.DE",   "reason": "Risk-on/off sentiment; Allianz global insurance", "beta": 0.25},

    # Nikkei — EU tech
    {"asian": "^N225", "direction": "any",  "eu": "ASML.AS",    "reason": "ASML sells EUV machines to TSMC/Samsung; Nikkei tech sentiment drives sector", "beta": 0.60},
    {"asian": "^N225", "direction": "any",  "eu": "STM",     "reason": "STM chips go into Japanese auto/industrial; direct supply chain link", "beta": 0.55},
    {"asian": "^N225", "direction": "any",  "eu": "BESI.AS",    "reason": "BESI packaging equipment sold to Asian chip fabs; Nikkei semiconductor proxy", "beta": 0.65},
    {"asian": "^N225", "direction": "any",  "eu": "NOKIA.HE",   "reason": "Nokia 5G competes with Japanese vendors; risk-on tech sentiment", "beta": 0.30},
    {"asian": "^N225", "direction": "any",  "eu": "ERIC-B.ST",  "reason": "Ericsson 5G Asia contracts; Nikkei tech risk-on/off signal", "beta": 0.30},
    {"asian": "^N225", "direction": "any",  "eu": "CAP.PA",     "reason": "Capgemini IT services; Japan is top 5 revenue market", "beta": 0.25},
    {"asian": "^N225", "direction": "any",  "eu": "DSY.PA",     "reason": "Dassault PLM software sold to Japanese auto/aerospace OEMs", "beta": 0.25},

    # --- Hang Seng (^HSI) ---
    # HK/China financial sector → European banks with Asia exposure
    {"asian": "^HSI",  "direction": "any",  "eu": "HSBA.L",   "reason": "HSBC derives ~50% revenue from Asia-Pacific", "beta": 0.70},
    {"asian": "^HSI",  "direction": "any",  "eu": "STAN.L",   "reason": "Standard Chartered 70%+ revenue from Asia/Africa", "beta": 0.75},
    {"asian": "^HSI",  "direction": "any",  "eu": "PRU.L",    "reason": "Prudential Asia insurance arm; HK-listed sub", "beta": 0.60},
    {"asian": "^HSI",  "direction": "any",  "eu": "DBK.DE",   "reason": "Deutsche Bank Asia investment banking exposure", "beta": 0.30},
    # China demand → miners
    {"asian": "^HSI",  "direction": "any",  "eu": "RIO.L",    "reason": "China iron ore demand; Rio ~50% China revenue", "beta": 0.55},
    {"asian": "^HSI",  "direction": "any",  "eu": "AAL.L",    "reason": "Anglo American copper/platinum; China demand proxy", "beta": 0.50},
    {"asian": "^HSI",  "direction": "any",  "eu": "GLEN.L",   "reason": "Glencore coal/copper; major China commodity exposure", "beta": 0.50},
    {"asian": "^HSI",  "direction": "any",  "eu": "BAS.DE",   "reason": "BASF chemicals; China is largest single market", "beta": 0.40},
    {"asian": "^HSI",  "direction": "any",  "eu": "ADS.DE",   "reason": "Adidas China revenue ~20% of total sales", "beta": 0.45},
    {"asian": "^HSI",  "direction": "any",  "eu": "HEN3.DE",  "reason": "Henkel consumer goods; Asia-Pacific growth market", "beta": 0.30},

    # Hang Seng — EU tech (China chip demand)
    {"asian": "^HSI",  "direction": "any",  "eu": "ASML.AS",    "reason": "ASML restricted from China but HSI moves reflect global chip demand cycle", "beta": 0.45},
    {"asian": "^HSI",  "direction": "any",  "eu": "STM",     "reason": "STM sells into China electronics/EV market; HSI demand proxy", "beta": 0.50},
    {"asian": "^HSI",  "direction": "any",  "eu": "BESI.AS",    "reason": "BESI packaging equipment; China is largest semiconductor assembly hub", "beta": 0.55},
    {"asian": "^HSI",  "direction": "any",  "eu": "NOKIA.HE",   "reason": "Nokia China telecom exposure; HSI reflects broader China tech capex", "beta": 0.35},
    {"asian": "^HSI",  "direction": "any",  "eu": "ERIC-B.ST",  "reason": "Ericsson lost China contracts; HSI down = risk-off for telecom infra", "beta": 0.25},
    {"asian": "^HSI",  "direction": "any",  "eu": "CAP.PA",     "reason": "Capgemini APAC IT services; China digital transformation exposure", "beta": 0.20},

    # --- ASX 200 (^AXJO) ---
    # Australia commodity-heavy → European miners and energy
    {"asian": "^AXJO", "direction": "any",  "eu": "RIO.L",    "reason": "Rio Tinto dual-listed ASX/LSE; direct price linkage", "beta": 0.85},
    {"asian": "^AXJO", "direction": "any",  "eu": "BHP.L",    "reason": "BHP dual-listed ASX/LSE; direct price linkage", "beta": 0.85},
    {"asian": "^AXJO", "direction": "any",  "eu": "GLEN.L",   "reason": "Commodity sector correlation; Glencore mines overlap", "beta": 0.45},
    {"asian": "^AXJO", "direction": "any",  "eu": "AAL.L",    "reason": "Mining sector correlation; AUD/commodity link", "beta": 0.40},
    {"asian": "^AXJO", "direction": "any",  "eu": "BP.L",     "reason": "Energy sector sentiment; AUS LNG export market", "beta": 0.30},
    {"asian": "^AXJO", "direction": "any",  "eu": "SHEL.L",   "reason": "Shell LNG exposure; Australia major LNG exporter", "beta": 0.30},
    {"asian": "^AXJO", "direction": "any",  "eu": "AZN.L",    "reason": "AstraZeneca APAC pharma; Australia operations", "beta": 0.20},
]


def get_correlated_eu_stocks(asian_movers: list[dict]) -> list[dict]:
    """
    For each Asian mover, look up correlated EU stocks and return
    a deduplicated list sorted by estimated impact magnitude.
    """
    seen: dict[str, dict] = {}  # eu_ticker → best record

    for mover in asian_movers:
        asian_sym = mover["symbol"]
        direction = mover["direction"]
        pct = mover["pct_change"]

        for rule in CORRELATION_MAP:
            if rule["asian"] != asian_sym:
                continue
            if rule["direction"] not in ("any", direction):
                continue

            eu_ticker = rule["eu"]
            estimated_move = round(pct * rule["beta"], 4)

            record = {
                "eu_ticker": eu_ticker,
                "eu_name": EU_WATCHLIST.get(eu_ticker, eu_ticker),
                "driven_by": asian_sym,
                "asian_name": mover["name"],
                "asian_pct": pct,
                "direction": direction,
                "reason": rule["reason"],
                "beta": rule["beta"],
                "estimated_eu_move_pct": estimated_move,
            }

            # Keep the record with the largest absolute estimated move
            if eu_ticker not in seen or abs(estimated_move) > abs(seen[eu_ticker]["estimated_eu_move_pct"]):
                seen[eu_ticker] = record

    result = sorted(seen.values(), key=lambda r: abs(r["estimated_eu_move_pct"]), reverse=True)
    return result


def get_all_watchlist_symbols() -> list[str]:
    return list(EU_WATCHLIST.keys())
