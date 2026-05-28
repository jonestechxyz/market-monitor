"""
Orchestrator: fetches data, detects movers, maps correlations,
formats the briefing, saves JSON, and optionally emails.

Usage:
    python main.py              # full run + email if env vars set
    python main.py --no-email   # skip email
    python main.py --dry-run    # print briefing only, no saves, no email
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

from fetcher import (
    fetch_all_asian_indices,
    fetch_watchlist,
    get_latest_session,
    ASIAN_INDICES,
)
from detector import detect_movers, compute_atr
from correlations import get_correlated_eu_stocks, get_all_watchlist_symbols, EU_WATCHLIST
from formatter import format_text_briefing, build_json_record, save_briefing
from mailer import send_briefing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run(dry_run: bool = False, no_email: bool = False) -> int:
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    # 1. Fetch Asian indices
    logger.info("=== Fetching Asian indices ===")
    asian_data = fetch_all_asian_indices(lookback_days=30)
    if not asian_data:
        logger.error("No Asian index data retrieved. Aborting.")
        return 1

    # 2. Detect movers
    logger.info("=== Detecting movers ===")
    asian_movers = detect_movers(asian_data, ASIAN_INDICES)
    logger.info("%d Asian mover(s) flagged", len(asian_movers))

    # 3. Identify correlated EU stocks
    logger.info("=== Mapping correlations ===")
    correlated_eu = get_correlated_eu_stocks(asian_movers)
    logger.info("%d EU stock(s) flagged", len(correlated_eu))

    # 4. Fetch data for EU watchlist (always fetch for dashboard richness)
    eu_symbols = get_all_watchlist_symbols()
    logger.info("=== Fetching EU watchlist (%d symbols) ===", len(eu_symbols))
    eu_raw = fetch_watchlist(eu_symbols, lookback_days=30)

    # Build a compact eu_data dict for the formatter
    eu_data: dict[str, dict] = {}
    for sym, df in eu_raw.items():
        session = get_latest_session(df)
        if session:
            session["atr"] = compute_atr(df)
            eu_data[sym] = session

    # 5. Format briefing
    text = format_text_briefing(run_ts, asian_movers, correlated_eu, eu_data)
    print(text)

    if dry_run:
        logger.info("Dry-run mode — skipping save and email.")
        return 0

    # 6. Save JSON record
    record = build_json_record(run_ts, asian_movers, correlated_eu, eu_data)
    path = save_briefing(record)
    logger.info("Briefing saved → %s", path)

    # 7. Email
    if not no_email:
        date_label = datetime.now(timezone.utc).strftime("%a %d %b %Y")
        subject = f"Asia-EU Market Briefing — {date_label}"
        ok = send_briefing(subject, text)
        if not ok:
            logger.warning("Email not sent (check env vars or SMTP config).")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Asia-EU Market Monitor")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no save/email")
    parser.add_argument("--no-email", action="store_true", help="Skip emailing the briefing")
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run, no_email=args.no_email))


if __name__ == "__main__":
    main()
