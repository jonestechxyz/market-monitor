"""
DJT Truth Social watcher.

Polls @realDonaldTrump's Truth Social feed every 15 minutes via the
public Mastodon-compatible API. Emails immediately when new posts appear.

Usage:
    python djt_watcher.py
    python djt_watcher.py --dry-run   # print posts, no email

State is stored in .djt_seen_id — the ID of the last post we emailed about.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

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

API_BASE    = "https://truthsocial.com/api/v1"
ACCOUNT_ID  = "107780257626128497"   # @realDonaldTrump
STATE_FILE  = Path(__file__).parent / ".djt_seen_id"


def get_latest_posts(since_id: str | None = None, limit: int = 10) -> list[dict]:
    params = {"limit": limit, "exclude_replies": "true", "exclude_reblogs": "false"}
    if since_id:
        params["since_id"] = since_id
    try:
        r = requests.get(
            f"{API_BASE}/accounts/{ACCOUNT_ID}/statuses",
            params=params,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error("Failed to fetch posts: %s", e)
        return []


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
    subject = f"🇺🇸 DJT just posted on Truth Social ({count} new {'post' if count == 1 else 'posts'})"

    plain_lines = []
    html_parts = []

    for post in reversed(posts):  # oldest first
        ts = post.get("created_at", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M UTC")
        except Exception:
            time_str = ts

        content = strip_html(post.get("content", ""))
        url = post.get("url", "https://truthsocial.com/@realDonaldTrump")

        plain_lines.append(f"[{time_str}]\n{content}\n{url}\n")
        html_parts.append(f"""
        <div style="margin-bottom:24px;padding:16px;background:#fff8f0;border-left:4px solid #b22234;border-radius:4px;font-family:Georgia,serif;">
          <div style="font-size:12px;color:#888;margin-bottom:8px;">{time_str}</div>
          <div style="font-size:17px;line-height:1.6;color:#111;">{post.get('content','')}</div>
          <div style="margin-top:10px;"><a href="{url}" style="font-size:12px;color:#b22234;">View on Truth Social →</a></div>
        </div>""")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="background:#f4f4f4;padding:24px;font-family:Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;">
    <div style="background:#b22234;color:white;padding:16px 20px;border-radius:6px 6px 0 0;">
      <span style="font-size:22px;font-weight:bold;">🇺🇸 DJT Truth Social Alert</span>
      <span style="float:right;font-size:13px;opacity:0.85;">{count} new {'post' if count == 1 else 'posts'}</span>
    </div>
    <div style="background:white;padding:20px;border-radius:0 0 6px 6px;">
      {''.join(html_parts)}
    </div>
  </div>
</body></html>"""

    return subject, "\n".join(plain_lines), html


def main(dry_run: bool = False):
    seen_id = load_seen_id()
    logger.info("Last seen post ID: %s", seen_id or "none (first run)")

    posts = get_latest_posts(since_id=seen_id)

    if not posts:
        logger.info("No new posts.")
        return

    logger.info("Found %d new post(s)", len(posts))

    subject, plain, html = build_email(posts)

    if dry_run:
        print(subject)
        print(plain)
        return

    send_briefing(subject, plain, html)

    # save the newest post ID (first in list = most recent)
    save_seen_id(posts[0]["id"])
    logger.info("State updated to post ID %s", posts[0]["id"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
