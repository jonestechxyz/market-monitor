"""
AIWorld.html — "The Marvel & The Panic" daily AI use-case showcase.

Scans today's news for the most interesting real-world ways people are using AI,
splits them into THE MARVEL (inspiring, useful, amazing) and THE PANIC (scary,
chaotic, cautionary), writes punchy summaries with Groq, and illustrates each
with Pollinations.ai (free, no API key, no quota).

Usage:
    python aiworld.py
    python aiworld.py --dry-run   # build HTML only, no FTP upload
"""

import argparse
import ftplib
import hashlib
import json
import logging
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from openai import OpenAI

# ── load .env ──────────────────────────────────────────────────────────────────
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
SKIP_IMAGES   = os.getenv("SKIP_IMAGES", "").lower() in ("1", "true", "yes")
OUTPUT_PATH   = Path(os.getenv("OUTPUT_PATH", "/tmp/AIWorld.html"))
RSS_BASE      = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

# Image style suffixes per side — keeps the two halves visually distinct.
MARVEL_STYLE = (
    "bright luminous hopeful editorial illustration, warm golden and teal palette, "
    "clean modern flat vector art, optimistic, glowing, inspiring, high detail"
)
PANIC_STYLE = (
    "dark ominous editorial illustration, deep red and black palette, glitch and "
    "static texture, unsettling, dramatic shadows, cautionary, cinematic, high detail"
)

# Wide net of AI use-case topics — both the marvelous and the alarming.
NEWS_QUERIES = [
    "AI breakthrough OR AI helped OR AI saved lives",
    "ChatGPT OR Claude OR Gemini used for OR helped",
    "AI medicine OR AI diagnosis OR AI healthcare discovery",
    "AI scam OR AI fraud OR deepfake victim",
    "AI job loss OR AI layoffs OR AI replacing workers",
    "AI startup OR new AI tool OR AI app launched",
    "AI art OR AI music OR AI film creativity",
    "AI fail OR AI hallucination OR AI mistake lawsuit",
    "AI science OR AI research OR AI discovery breakthrough",
    "students OR teachers using AI OR AI in classroom",
    "AI accessibility OR AI disability OR AI translation",
    "AI surveillance OR AI privacy OR AI bias controversy",
]

# ── rss fetch ──────────────────────────────────────────────────────────────────
def fetch_rss(query: str, max_age_hours: int = 36, limit: int = 6) -> list[dict]:
    url = RSS_BASE.format(query=urllib.parse.quote(query))
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        now = datetime.now(timezone.utc)
        for item in root.findall(".//item"):
            if len(items) >= limit:
                break
            title = item.findtext("title", "")
            link  = item.findtext("link", "")
            pub   = item.findtext("pubDate", "")
            source = item.findtext("{http://www.w3.org/2005/Atom}source", "") or ""
            try:
                pub_dt    = parsedate_to_datetime(pub)
                age_hours = (now - pub_dt).total_seconds() / 3600
                if age_hours > max_age_hours:
                    continue
            except Exception:
                pass
            # Google News appends " - Source" to titles; keep source, clean title.
            m = re.search(r"\s*-\s*([^-]+)$", title)
            src_name = m.group(1).strip() if m else ""
            clean_title = re.sub(r"\s*-\s*[^-]+$", "", title).strip()
            if clean_title:
                items.append({"title": clean_title, "link": link, "source": src_name})
        return items
    except Exception as e:
        logger.error("RSS failed for %s: %s", query, e)
        return []

# ── groq ───────────────────────────────────────────────────────────────────────
def groq_split_stories(items: list[dict]) -> dict:
    """Ask Groq to pick the best AI use-cases and split them into marvel vs panic."""
    if not items:
        return {"marvel": [], "panic": []}
    numbered = "\n".join(f"{i+1}. {it['title']}" for i, it in enumerate(items))
    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the editor of 'AI World — The Marvel & The Panic', a sharp, "
                        "human daily showcase of how people are ACTUALLY using AI right now. "
                        "You love real, specific, concrete use-cases — a doctor who caught a "
                        "tumor, a grandma who got scammed, a kid who built an app. You hate "
                        "vague 'AI is powerful' filler. Write with clarity and a little "
                        "personality. Return ONLY valid JSON, no markdown, no code fences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "From these headlines, choose the best stories about REAL ways people "
                        "are using (or being affected by) AI, and sort them into two groups:\n"
                        "- MARVEL: genuinely amazing / useful / inspiring uses of AI\n"
                        "- PANIC: worrying / chaotic / cautionary uses or consequences\n\n"
                        "Pick up to 4 for MARVEL and up to 4 for PANIC (the strongest, most "
                        "concrete, most distinct stories — skip duplicates and vague ones).\n\n"
                        "For each story return:\n"
                        '- "source_index": the number of the headline it came from\n'
                        '- "title": a punchy 6-12 word rewritten headline\n'
                        '- "summary": 2-3 plain-English sentences on what someone actually DID '
                        "with AI and why it matters\n"
                        '- "image_prompt": a vivid scene description for an illustration of this story\n\n'
                        f"Headlines:\n{numbered}\n\n"
                        'Return ONLY a JSON object: {"marvel": [...], "panic": [...]}.'
                    ),
                },
            ],
            temperature=0.7,
            max_tokens=2200,
        )
        content = resp.choices[0].message.content.strip()
        content = re.sub(r"^```[\w]*\n?", "", content).strip()
        content = re.sub(r"\n?```$", "", content).strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return {
                "marvel": (data.get("marvel") or [])[:4],
                "panic":  (data.get("panic") or [])[:4],
            }
    except Exception as e:
        logger.error("Groq split_stories failed: %s", e)
    return {"marvel": [], "panic": []}

def attach_links(stories: list[dict], items: list[dict]) -> list[dict]:
    """Map each story's source_index back to the real article link + source name."""
    for s in stories:
        try:
            idx = int(s.get("source_index", 0)) - 1
            if 0 <= idx < len(items):
                s["link"] = items[idx].get("link", "")
                s["source"] = items[idx].get("source", "")
        except (ValueError, TypeError):
            s["link"] = ""
            s["source"] = ""
    return stories

# ── pollinations images (free, no key) ──────────────────────────────────────────
def pollinations_url(prompt: str, side: str, width: int, height: int) -> str:
    """Build a Pollinations.ai image URL — generated on demand, no API key needed."""
    style = MARVEL_STYLE if side == "marvel" else PANIC_STYLE
    full = f"{prompt}, {style}"
    seed = int(hashlib.md5(full.encode()).hexdigest()[:8], 16) % 100000
    encoded = urllib.parse.quote(full, safe="")
    return (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true&seed={seed}"
    )

# ── html builder ────────────────────────────────────────────────────────────────
def _card(s: dict, side: str) -> str:
    title = s.get("title", "Untitled")
    summary = s.get("summary", "")
    link = s.get("link", "")
    source = s.get("source", "")
    title_escaped = title.replace('"', "&quot;")
    if SKIP_IMAGES:
        img = f'<div class="card-img-placeholder">{title_escaped}</div>'
    else:
        url = pollinations_url(s.get("image_prompt", title), side, 700, 440)
        img = f'<img class="card-img" src="{url}" alt="{title_escaped}" loading="lazy">'
    src_line = ""
    if link:
        label = source or "Read the story"
        src_line = f'<a class="card-source" href="{link}" target="_blank" rel="noopener">{label} ↗</a>'
    return f"""
      <article class="card">
        <div class="card-img-wrap">{img}</div>
        <div class="card-body">
          <h3 class="card-title">{title}</h3>
          <p class="card-summary">{summary}</p>
          {src_line}
        </div>
      </article>"""

def build_html(data: dict, date_str: str) -> str:
    marvel = data.get("marvel") or []
    panic  = data.get("panic") or []
    if not marvel and not panic:
        marvel = [{"title": "A quiet day in the machine", "summary": "No fresh AI stories surfaced today. Check back tomorrow — the robots never rest for long.", "image_prompt": "a calm empty futuristic control room", "link": "", "source": ""}]

    marvel_cards = "".join(_card(s, "marvel") for s in marvel)
    panic_cards  = "".join(_card(s, "panic") for s in panic)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI World — The Marvel &amp; The Panic — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0a0a0f;
    --panel: #13131c;
    --text: #e8e8f0;
    --dim: #9a9ab0;
    --marvel: #36e0c8;
    --marvel-2: #ffcf5c;
    --panic: #ff4d5e;
    --panic-2: #ff8a3d;
    --border: #23232f;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: radial-gradient(ellipse at top, #14141f 0%, var(--bg) 60%);
    color: var(--text);
    font-family: 'Space Grotesk', system-ui, sans-serif;
    line-height: 1.6;
    max-width: 1180px;
    margin: 0 auto;
    padding: 0 24px 80px;
  }}
  .masthead {{
    text-align: center;
    padding: 56px 0 28px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 40px;
  }}
  .eyebrow {{
    font-size: 12px;
    letter-spacing: 0.35em;
    text-transform: uppercase;
    color: var(--dim);
    margin-bottom: 14px;
  }}
  .masthead h1 {{
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: clamp(38px, 7vw, 76px);
    line-height: 1.0;
    letter-spacing: -1px;
  }}
  .masthead h1 .m {{ color: var(--marvel); }}
  .masthead h1 .p {{ color: var(--panic); }}
  .masthead .date {{ color: var(--dim); margin-top: 16px; font-size: 14px; letter-spacing: 0.05em; }}
  .section {{ margin-bottom: 64px; }}
  .section-head {{
    display: flex;
    align-items: baseline;
    gap: 16px;
    margin-bottom: 28px;
    padding-bottom: 12px;
    border-bottom: 2px solid var(--border);
  }}
  .section-head h2 {{
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 30px;
    letter-spacing: -0.5px;
  }}
  .section-head .tag {{ font-size: 13px; color: var(--dim); letter-spacing: 0.04em; }}
  .marvel .section-head h2 {{ color: var(--marvel); }}
  .panic .section-head h2 {{ color: var(--panic); }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 26px;
  }}
  .card {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: transform 0.18s ease, border-color 0.18s ease;
  }}
  .card:hover {{ transform: translateY(-4px); }}
  .marvel .card:hover {{ border-color: var(--marvel); }}
  .panic .card:hover {{ border-color: var(--panic); }}
  .card-img-wrap {{ background: #000; line-height: 0; aspect-ratio: 7 / 4.4; }}
  .card-img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .card-img-placeholder {{
    width: 100%; height: 100%; min-height: 180px;
    display: flex; align-items: center; justify-content: center;
    padding: 18px; text-align: center; color: var(--dim); font-size: 13px;
    background: repeating-linear-gradient(45deg, #15151f 0 10px, #1b1b27 10px 20px);
  }}
  .card-body {{ padding: 20px 22px 22px; display: flex; flex-direction: column; gap: 10px; flex: 1; }}
  .card-title {{ font-family: 'Syne', sans-serif; font-weight: 700; font-size: 18px; line-height: 1.25; }}
  .card-summary {{ color: var(--dim); font-size: 14.5px; flex: 1; }}
  .card-source {{ font-size: 12.5px; text-decoration: none; letter-spacing: 0.03em; margin-top: 4px; }}
  .marvel .card-source {{ color: var(--marvel-2); }}
  .panic .card-source {{ color: var(--panic-2); }}
  .card-source:hover {{ text-decoration: underline; }}
  .footer {{
    text-align: center; color: var(--dim); font-size: 12.5px;
    border-top: 1px solid var(--border); padding-top: 28px; letter-spacing: 0.04em;
  }}
  .footer a {{ color: var(--dim); }}
  @media (max-width: 560px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>

<header class="masthead">
  <div class="eyebrow">A Daily Look At How The World Actually Uses AI</div>
  <h1>The <span class="m">Marvel</span> &amp; The <span class="p">Panic</span></h1>
  <div class="date">{date_str}</div>
</header>

<section class="section marvel">
  <div class="section-head">
    <h2>✦ The Marvel</h2>
    <span class="tag">the amazing, useful & inspiring</span>
  </div>
  <div class="grid">{marvel_cards}</div>
</section>

<section class="section panic">
  <div class="section-head">
    <h2>⚠ The Panic</h2>
    <span class="tag">the chaotic, risky & cautionary</span>
  </div>
  <div class="grid">{panic_cards}</div>
</section>

<footer class="footer">
  Generated {generated} &nbsp;·&nbsp;
  Stories curated by Groq &nbsp;·&nbsp;
  Images by <a href="https://pollinations.ai" target="_blank" rel="noopener">Pollinations.ai</a> &nbsp;·&nbsp;
  Headlines via Google News
</footer>

</body>
</html>"""

# ── ftp upload ─────────────────────────────────────────────────────────────────
def ftp_upload(local_path: Path, remote_filename: str = "AIWorld.html"):
    host = os.getenv("FTP_HOST", "")
    user = os.getenv("FTP_USER", "")
    pwd  = os.getenv("FTP_PASS", "")
    path = os.getenv("FTP_PATH", "/public_html/")
    if not all([host, user, pwd]):
        logger.warning("FTP credentials not set — skipping upload")
        return False
    try:
        with ftplib.FTP_TLS(host, timeout=60) as ftp:
            ftp.login(user, pwd)
            ftp.prot_p()
            ftp.cwd(path)
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_filename}", f)
        logger.info("✅ Uploaded to https://jonestech.xyz/%s", remote_filename)
        return True
    except Exception as e:
        logger.warning("FTP_TLS failed (%s), trying plain FTP...", e)
        try:
            with ftplib.FTP(host, timeout=60) as ftp:
                ftp.login(user, pwd)
                ftp.cwd(path)
                with open(local_path, "rb") as f:
                    ftp.storbinary(f"STOR {remote_filename}", f)
            logger.info("✅ Uploaded via plain FTP to https://jonestech.xyz/%s", remote_filename)
            return True
        except Exception as e2:
            logger.error("FTP upload failed: %s", e2)
            return False

# ── main ────────────────────────────────────────────────────────────────────────
def main(dry_run: bool = False):
    date_str = datetime.now().strftime("%A %-d %B %Y")
    logger.info("✦ Building AIWorld — %s", date_str)

    # 1. Collect headlines (with links) from all feeds
    all_items = []
    for query in NEWS_QUERIES:
        logger.info("Fetching: %s", query[:50])
        all_items.extend(fetch_rss(query, limit=6))

    # Deduplicate by title
    seen, items = set(), []
    for it in all_items:
        key = it["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            items.append(it)
    logger.info("Got %d unique headlines", len(items))

    # 2. Groq picks + splits into marvel / panic
    logger.info("Asking Groq to curate marvel vs panic...")
    data = groq_split_stories(items[:50])
    data["marvel"] = attach_links(data.get("marvel", []), items)
    data["panic"]  = attach_links(data.get("panic", []), items)
    logger.info("Got %d marvel + %d panic stories", len(data["marvel"]), len(data["panic"]))

    # 3. Build HTML (Pollinations image URLs are embedded — generated on demand)
    logger.info("Building HTML...")
    html = build_html(data, date_str)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    logger.info("✅ Saved to %s", OUTPUT_PATH)

    if dry_run:
        logger.info("Dry run — skipping FTP upload")
        return

    # 4. FTP upload
    logger.info("Uploading to jonestech.xyz...")
    ftp_upload(OUTPUT_PATH)
    logger.info("🎉 AIWorld done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
