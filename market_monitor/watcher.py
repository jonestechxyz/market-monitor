"""
Market news watcher — monitors Trump & Musk statements via Google News RSS,
analyses against your watchlist via Groq, fires Pushover alerts.

Usage:
    python watcher.py
"""

import time
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timezone
from pathlib import Path
from openai import OpenAI

# load .env if present
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────

PUSHOVER_USER  = "uwb6u3d6hqvcynmthjbwa1g6wyxhzo"
PUSHOVER_TOKEN = "afgjsjzi2gx7uitk9ty6275mq9ddd4"
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")

POLL_INTERVAL  = 300  # seconds (5 min)
SEEN_FILE      = Path(__file__).parent / ".seen_posts.json"

WATCHLIST = [
    "ASML", "STM", "BESI", "Nokia", "Ericsson",
    "Capgemini", "Dassault", "Nvidia", "Apple", "Tesla",
    "Microsoft", "Amazon", "Meta", "Google", "AMD",
]

# Google News RSS queries to monitor
FEEDS = [
    {"name": "Donald Trump",  "query": "Trump+tariffs+OR+Trump+trade+OR+Trump+economy+OR+\"Trump+says\""},
    {"name": "Elon Musk",     "query": "\"Elon+Musk\"+market+OR+\"Elon+Musk\"+Tesla+OR+\"Elon+Musk\"+tariff"},
    {"name": "AI Breaking",   "query": "AI+breakthrough+OR+\"artificial+intelligence\"+chips+OR+OpenAI+OR+Anthropic+OR+Gemini+OR+\"AI+model\""},
    {"name": "Chip Sector",   "query": "NVIDIA+OR+ASML+OR+AMD+OR+\"semiconductor\"+earnings+OR+\"chip+ban\"+OR+\"export+controls\""},
]

RSS_BASE = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

# ── GROQ CLIENT ───────────────────────────────────────────────────────────────

groq = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)

# ── SEEN POSTS PERSISTENCE ────────────────────────────────────────────────────

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()

def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen)))

# ── RSS FETCH ─────────────────────────────────────────────────────────────────

def fetch_rss(query: str, max_age_hours: int = 2) -> list[dict]:
    url = RSS_BASE.format(query=query)
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        now = datetime.now(timezone.utc)
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title", "")
            link  = item.findtext("link", "")
            guid  = item.findtext("guid", link)
            pub   = item.findtext("pubDate", "")
            # parse pubDate and filter by age
            try:
                from email.utils import parsedate_to_datetime
                pub_dt = parsedate_to_datetime(pub)
                age_hours = (now - pub_dt).total_seconds() / 3600
                if age_hours > max_age_hours:
                    continue
            except Exception:
                pass  # if we can't parse the date, include it anyway
            items.append({"id": guid, "title": title, "link": link, "pub": pub})
        return items
    except Exception as e:
        logger.error("RSS fetch failed: %s", e)
        return []

# ── GROQ ANALYSIS ─────────────────────────────────────────────────────────────

def analyse_headline(source: str, headline: str) -> dict:
    watchlist_str = ", ".join(WATCHLIST)
    prompt = f"""A news headline about {source}:

"{headline}"

Does this headline suggest a potential market impact on any of these stocks?
{watchlist_str}

Respond in JSON only:
{{
  "relevant": true or false,
  "affected_stocks": ["TICKER1", "TICKER2"],
  "reason": "one sentence",
  "sentiment": "bullish" or "bearish" or "neutral"
}}

Only return JSON."""

    try:
        response = groq.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a financial analyst. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=150,
        )
        content = response.choices[0].message.content.strip()
        content = content.strip("`").strip()
        if content.startswith("json"):
            content = content[4:].strip()
        return json.loads(content)
    except Exception as e:
        logger.error("Groq analysis failed: %s", e)
        return {"relevant": False, "affected_stocks": [], "reason": "", "sentiment": "neutral"}

# ── PUSHOVER ──────────────────────────────────────────────────────────────────

def send_pushover(title: str, message: str, priority: int = 0, url: str = ""):
    data = {
        "token":    PUSHOVER_TOKEN,
        "user":     PUSHOVER_USER,
        "title":    title,
        "message":  message,
        "priority": priority,
    }
    if url:
        data["url"] = url
        data["url_title"] = "Read more"
    if priority == 2:
        data["retry"] = 60
        data["expire"] = 3600

    try:
        r = requests.post("https://api.pushover.net/1/messages.json", data=data, timeout=10)
        r.raise_for_status()
        logger.info("✅ Pushover sent: %s", title)
    except Exception as e:
        logger.error("Pushover failed: %s", e)

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────

def main():
    logger.info("🚀 Market watcher starting...")

    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not set in environment")
        return

    seen = load_seen()
    logger.info("Loaded %d seen item IDs", len(seen))

    send_pushover(
        "🚀 Market Watcher Live",
        "Monitoring Trump & Musk news for market-moving headlines.",
        priority=-1
    )

    while True:
        for feed in FEEDS:
            items = fetch_rss(feed["query"])
            new_count = 0

            for item in items:
                iid = item["id"]
                if iid in seen:
                    continue

                seen.add(iid)
                new_count += 1

                headline = item["title"]
                logger.info("New: %s", headline[:80])

                analysis = analyse_headline(feed["name"], headline)
                logger.info("Analysis: %s", analysis)

                if analysis.get("relevant"):
                    stocks    = ", ".join(analysis.get("affected_stocks", []))
                    sentiment = analysis.get("sentiment", "neutral").upper()
                    reason    = analysis.get("reason", "")

                    title   = f"📰 {feed['name']} — {sentiment}"
                    if stocks:
                        title += f" | {stocks}"
                    message = f"{headline}\n\n📊 {reason}"

                    affected = len(analysis.get("affected_stocks", []))
                    priority = 1 if affected >= 3 else 0

                    send_pushover(title, message, priority=priority, url=item["link"])
                else:
                    logger.info("Not market relevant — skipped")

            if new_count:
                save_seen(seen)
                logger.info("%d new item(s) from %s feed", new_count, feed["name"])

        logger.info("Sleeping %ds...", POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
