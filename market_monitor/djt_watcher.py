"""
DJT Truth Social watcher.

Monitors Trump's posts via Google News RSS (Truth Social blocks API access).
Emails within 15 minutes of a new post, with Groq market/geopolitical analysis.

Usage:
    python djt_watcher.py
    python djt_watcher.py --dry-run   # print posts, no email

State is stored in .djt_seen_id — the GUID of the last article we emailed about.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from mailer import send_briefing

# load .env if present
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RSS_URL    = "https://news.google.com/rss/search?q=%22Trump%22+%22Truth+Social%22&hl=en-US&gl=US&ceid=US:en"
STATE_FILE = Path(__file__).parent / ".djt_seen_id"

groq = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ.get("GROQ_API_KEY", ""),
)


def groq_analyse(post_text: str) -> str:
    """Return a short market/geopolitical analysis of a DJT post."""
    try:
        resp = groq.chat.completions.create(
            model="moonshotai/kimi-k2-instruct",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a sharp financial and geopolitical analyst. "
                        "When given a post by Donald Trump, give a concise 3-4 sentence analysis covering: "
                        "1) what he's signalling, 2) likely market impact (sectors/assets), "
                        "3) geopolitical implications if any. Be direct and specific. No fluff."
                    ),
                },
                {"role": "user", "content": post_text},
            ],
            max_tokens=250,
            temperature=0.4,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("Groq analysis failed: %s", e)
        return ""


def get_latest_posts(seen_guid: str | None = None) -> list[dict]:
    """Fetch recent Trump/Truth Social news items from Google News RSS."""
    try:
        r = requests.get(RSS_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        logger.error("Failed to fetch RSS: %s", e)
        return []

    items = []
    for item in root.findall(".//item")[:10]:  # cap at 10 per run
        guid = (item.findtext("guid") or "").strip()
        if seen_guid and guid == seen_guid:
            break  # stop at last seen
        title   = item.findtext("title") or ""
        link    = item.findtext("link") or ""
        pub     = item.findtext("pubDate") or ""
        source  = item.findtext("source") or ""
        try:
            dt = parsedate_to_datetime(pub)
            time_str = dt.strftime("%H:%M UTC")
        except Exception:
            time_str = pub
        items.append({"guid": guid, "title": title, "link": link,
                      "time_str": time_str, "source": source})

    return items


def strip_html(text: str) -> str:
    import re
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def load_seen_id() -> str | None:
    if STATE_FILE.exists():
        return STATE_FILE.read_text().strip() or None
    return None


def save_seen_id(post_id: str):
    STATE_FILE.write_text(post_id)


def build_email(posts: list[dict]) -> tuple[str, str, str]:
    count = len(posts)
    subject = f"🇺🇸 DJT Truth Social Alert — {count} new {'story' if count == 1 else 'stories'}"

    plain_lines = []
    html_parts = []

    for post in reversed(posts):  # oldest first
        title    = post["title"]
        url      = post["link"]
        time_str = post["time_str"]
        source   = post["source"]
        analysis = groq_analyse(title)

        analysis_plain = f"\n📊 Analysis:\n{analysis}" if analysis else ""
        plain_lines.append(f"[{time_str}] {source}\n{title}{analysis_plain}\n{url}\n")

        analysis_html = (
            f'<div style="margin-top:12px;padding:12px;background:#f0f4ff;border-left:3px solid #3b5bdb;'
            f'border-radius:4px;font-size:14px;line-height:1.6;color:#333;">'
            f'<strong style="color:#3b5bdb;">📊 Groq Analysis</strong><br>{analysis}</div>'
        ) if analysis else ""

        html_parts.append(f"""
        <div style="margin-bottom:24px;padding:16px;background:#fff8f0;border-left:4px solid #b22234;border-radius:4px;">
          <div style="font-size:11px;color:#888;margin-bottom:6px;">{time_str} · {source}</div>
          <div style="font-size:17px;font-weight:bold;line-height:1.4;color:#111;font-family:Georgia,serif;">{title}</div>
          {analysis_html}
          <div style="margin-top:10px;"><a href="{url}" style="font-size:12px;color:#b22234;">Read article →</a></div>
        </div>""")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="background:#f4f4f4;padding:24px;font-family:Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;">
    <div style="background:#b22234;color:white;padding:16px 20px;border-radius:6px 6px 0 0;">
      <span style="font-size:22px;font-weight:bold;">🇺🇸 DJT Truth Social Alert</span>
      <span style="float:right;font-size:13px;opacity:0.85;">{count} new {'story' if count == 1 else 'stories'}</span>
    </div>
    <div style="background:white;padding:20px;border-radius:0 0 6px 6px;">
      {''.join(html_parts)}
    </div>
  </div>
</body></html>"""

    return subject, "\n".join(plain_lines), html


def main(dry_run: bool = False):
    seen_guid = load_seen_id()
    first_run = seen_guid is None
    logger.info("Last seen GUID: %s", seen_guid or "none (first run)")

    posts = get_latest_posts(seen_guid=seen_guid)

    if not posts:
        logger.info("No new posts.")
        return

    # On first run, just bookmark the latest item — don't flood with old news
    if first_run:
        save_seen_id(posts[0]["guid"])
        logger.info("First run — bookmarked latest GUID, no email sent.")
        return

    logger.info("Found %d new item(s)", len(posts))

    subject, plain, html = build_email(posts)

    if dry_run:
        print(subject)
        print(plain)
        return

    send_briefing(subject, plain, html)

    save_seen_id(posts[0]["guid"])
    logger.info("State updated to GUID %s", posts[0]["guid"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
