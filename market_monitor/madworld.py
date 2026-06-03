"""
MadWorld.html — Daily MAD Magazine-style satirical news page.

Scans today's headlines, picks the most absurd stories, and generates
satirical illustrations via Hugging Face Inference API (free with HF_TOKEN).

Usage:
    python madworld.py
    python madworld.py --dry-run   # build HTML only, no FTP upload
"""

import argparse
import ftplib
import json
import logging
import os
import re
import sys
import time
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

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
HF_TOKEN     = os.getenv("HF_TOKEN", "")
OUTPUT_PATH  = Path(os.getenv("OUTPUT_PATH", "/tmp/MadWorld.html"))
RSS_BASE     = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

# Hugging Face Inference API — FLUX.1-schnell (free tier, fast)
HF_IMAGE_API = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

MAD_STYLE = (
    "gap-toothed big-eared grinning red-haired freckled boy mascot, "
    "MAD Magazine cover art, vintage 1960s American humor magazine illustration, "
    "bold flat colors, comic book halftone dots, exaggerated caricature style, "
    "satirical cartoon, Don Martin art style"
)

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

# Wide net of absurd-potential topics
NEWS_QUERIES = [
    "Trump OR Congress OR Senate bizarre OR weird OR controversial",
    "tech CEO OR Silicon Valley OR AI scandal OR controversy",
    "celebrity OR Hollywood bizarre OR weird news",
    "government OR politician gaffe OR fail OR ridiculous",
    "Wall Street OR billionaire OR corporate absurd OR ridiculous",
    "science OR NASA OR space weird OR bizarre discovery",
    "social media OR viral OR internet controversy",
]

# ── rss fetch ──────────────────────────────────────────────────────────────────
def fetch_rss(query: str, max_age_hours: int = 28, limit: int = 8) -> list[dict]:
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
            try:
                pub_dt    = parsedate_to_datetime(pub)
                age_hours = (now - pub_dt).total_seconds() / 3600
                if age_hours > max_age_hours:
                    continue
            except Exception:
                pass
            clean_title = re.sub(r"\s*-\s*[^-]+$", "", title).strip()
            if clean_title:
                items.append({"title": clean_title, "link": link})
        return items
    except Exception as e:
        logger.error("RSS failed for %s: %s", query, e)
        return []

# ── groq helpers ───────────────────────────────────────────────────────────────
def groq_pick_stories(headlines: list[str]) -> list[dict]:
    """Ask Groq to pick 6 stories sorted by satirical potential, return with image prompts and captions."""
    if not headlines:
        return []
    numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the editor of MAD Magazine — the master of satirical absurdity. "
                        "Your job: find the most ridiculous, hypocritical, or satirically rich stories "
                        "and write scathing, witty captions in the classic MAD Magazine voice. "
                        "Think Don Martin meets P.J. O'Rourke. Be specific, punchy, irreverent. "
                        "Return ONLY valid JSON, no markdown, no code fences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"From these headlines, pick the 6 MOST satirically worthy stories. "
                        f"For each, write:\n"
                        f"- A MAD Magazine-style satirical caption (2-3 sharp, funny sentences)\n"
                        f"- A vivid Pollinations.ai image prompt describing a caricature/illustration "
                        f"that satirizes the story (describe the scene, people as cartoons, what's happening)\n\n"
                        f"Headlines:\n{numbered}\n\n"
                        f"Return a JSON array of exactly 6 objects with keys: "
                        f"\"headline\", \"caption\", \"image_prompt\". "
                        f"First item should be the most satirically rich (hero story). "
                        f"Return ONLY the JSON array."
                    ),
                },
            ],
            temperature=0.8,
            max_tokens=1800,
        )
        content = resp.choices[0].message.content.strip()
        content = re.sub(r"^```[\w]*\n?", "", content).strip()
        content = re.sub(r"\n?```$", "", content).strip()
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            stories = json.loads(match.group(0))
            return stories[:6]
    except Exception as e:
        logger.error("Groq pick_stories failed: %s", e)
    return []

# ── hugging face image generation ─────────────────────────────────────────────
def generate_image_b64(scene_prompt: str, width: int = 800, height: int = 512) -> str:
    """Call HF Inference API, return base64 data URI or empty string on failure."""
    if not HF_TOKEN:
        logger.warning("HF_TOKEN not set — skipping image generation")
        return ""
    full_prompt = f"{MAD_STYLE}, {scene_prompt}"
    try:
        resp = requests.post(
            HF_IMAGE_API,
            headers={"Authorization": f"Bearer {HF_TOKEN}"},
            json={
                "inputs": full_prompt,
                "parameters": {"width": width, "height": height, "num_inference_steps": 4},
            },
            timeout=60,
        )
        if resp.status_code == 200:
            import base64
            b64 = base64.b64encode(resp.content).decode()
            return f"data:image/jpeg;base64,{b64}"
        elif resp.status_code == 503:
            # Model loading — retry once after a pause
            logger.info("HF model loading, waiting 20s...")
            time.sleep(20)
            resp = requests.post(
                HF_IMAGE_API,
                headers={"Authorization": f"Bearer {HF_TOKEN}"},
                json={
                    "inputs": full_prompt,
                    "parameters": {"width": width, "height": height, "num_inference_steps": 4},
                },
                timeout=60,
            )
            if resp.status_code == 200:
                import base64
                b64 = base64.b64encode(resp.content).decode()
                return f"data:image/jpeg;base64,{b64}"
        logger.warning("HF image failed: %s %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("HF image error: %s", e)
    return ""

# ── html builder ───────────────────────────────────────────────────────────────
def build_html(stories: list[dict], date_str: str) -> str:
    if not stories:
        stories = [{"headline": "Nothing happened today", "caption": "Somehow, nothing absurd happened. We're as shocked as you are.", "image_prompt": "empty newsroom cartoon", "image_data": ""}]

    hero = stories[0]
    grid_stories = stories[1:]

    hero_img_url = hero.get("image_data", "")

    grid_cards = ""
    for s in grid_stories:
        img_url = s.get("image_data", "")
        headline_escaped = s['headline'].replace('"', '&quot;')
        img_tag = f'<img class="card-img" src="{img_url}" alt="{headline_escaped}">' if img_url else f'<div class="card-img-placeholder">{s["headline"][:40]}…</div>'
        grid_cards += f"""
        <div class="grid-card">
          <div class="card-img-wrap">
            {img_tag}
          </div>
          <div class="card-body">
            <div class="card-headline">{s['headline']}</div>
            <div class="card-caption">{s['caption']}</div>
          </div>
        </div>"""

    hero_headline_escaped = hero['headline'].replace('"', '&quot;')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MAD World — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@700;900&family=Special+Elite&family=Permanent+Marker&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #1a0a00;
    --surface: #2a1200;
    --surface2: #3a1800;
    --border: #5a2a00;
    --text: #f5e6c8;
    --text-dim: #c4a882;
    --red: #cc0000;
    --yellow: #ffd700;
    --yellow2: #ffb300;
    --white: #fff8e7;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Special Elite', cursive;
    font-size: 16px;
    line-height: 1.6;
    max-width: 1100px;
    margin: 0 auto;
    padding: 0 24px 60px;
    background-image:
      repeating-linear-gradient(
        0deg,
        transparent,
        transparent 2px,
        rgba(255,215,0,0.015) 2px,
        rgba(255,215,0,0.015) 4px
      );
  }}

  /* ── MASTHEAD ── */
  .masthead {{
    text-align: center;
    padding: 36px 0 24px;
    border-bottom: 6px double var(--yellow);
    margin-bottom: 40px;
    position: relative;
  }}

  .masthead::before {{
    content: "THE MAGAZINE THAT MAKES FUN OF NEWS THAT MAKES ITSELF";
    display: block;
    font-family: 'Oswald', sans-serif;
    font-size: 11px;
    letter-spacing: 0.2em;
    color: var(--yellow2);
    text-transform: uppercase;
    margin-bottom: 12px;
  }}

  .masthead-title {{
    font-family: 'Oswald', sans-serif;
    font-size: 90px;
    font-weight: 900;
    line-height: 0.9;
    color: var(--yellow);
    text-shadow:
      4px 4px 0 var(--red),
      8px 8px 0 #660000;
    letter-spacing: -2px;
  }}

  .masthead-title span {{
    color: var(--red);
    text-shadow:
      4px 4px 0 var(--yellow),
      8px 8px 0 #884400;
  }}

  .masthead-sub {{
    font-family: 'Oswald', sans-serif;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    color: var(--red);
    margin-top: 8px;
  }}

  .masthead-date {{
    font-size: 12px;
    color: var(--text-dim);
    margin-top: 10px;
    font-family: 'Special Elite', cursive;
  }}

  .price-tag {{
    position: absolute;
    top: 36px;
    right: 0;
    background: var(--red);
    color: var(--yellow);
    font-family: 'Oswald', sans-serif;
    font-weight: 900;
    font-size: 22px;
    padding: 8px 14px;
    border-radius: 50%;
    transform: rotate(12deg);
    border: 3px solid var(--yellow);
    line-height: 1.1;
    text-align: center;
  }}

  /* ── HERO ── */
  .hero {{
    margin-bottom: 48px;
    border: 4px solid var(--yellow);
    border-radius: 4px;
    overflow: hidden;
    position: relative;
    background: #000;
  }}

  .hero-badge {{
    position: absolute;
    top: 16px;
    left: 16px;
    background: var(--red);
    color: var(--yellow);
    font-family: 'Oswald', sans-serif;
    font-weight: 900;
    font-size: 13px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    padding: 5px 12px;
    border: 2px solid var(--yellow);
    z-index: 2;
  }}

  .hero-img {{
    width: 100%;
    max-height: 520px;
    object-fit: cover;
    display: block;
    filter: saturate(1.3) contrast(1.1);
  }}

  .hero-img-placeholder {{
    width: 100%;
    height: 320px;
    background: repeating-linear-gradient(45deg, #2a1200 0, #2a1200 10px, #3a1800 10px, #3a1800 20px);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Oswald', sans-serif;
    font-size: 18px;
    color: var(--yellow2);
    text-align: center;
    padding: 20px;
  }}

  .card-img-placeholder {{
    width: 100%;
    height: 220px;
    background: repeating-linear-gradient(45deg, #2a1200 0, #2a1200 8px, #3a1800 8px, #3a1800 16px);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Special Elite', cursive;
    font-size: 12px;
    color: var(--yellow2);
    text-align: center;
    padding: 12px;
  }}

  .hero-body {{
    background: var(--surface);
    padding: 24px 28px;
    border-top: 4px solid var(--yellow);
  }}

  .hero-headline {{
    font-family: 'Oswald', sans-serif;
    font-size: 28px;
    font-weight: 700;
    color: var(--yellow);
    line-height: 1.2;
    margin-bottom: 14px;
  }}

  .hero-caption {{
    font-size: 17px;
    color: var(--text);
    line-height: 1.65;
    border-left: 5px solid var(--red);
    padding-left: 16px;
    font-style: italic;
  }}

  /* ── SECTION LABEL ── */
  .section-label {{
    font-family: 'Oswald', sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: var(--red);
    text-align: center;
    margin-bottom: 28px;
    display: flex;
    align-items: center;
    gap: 12px;
  }}

  .section-label::before,
  .section-label::after {{
    content: "";
    flex: 1;
    height: 2px;
    background: repeating-linear-gradient(90deg, var(--red) 0, var(--red) 6px, transparent 6px, transparent 10px);
  }}

  /* ── GRID ── */
  .story-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 28px;
    margin-bottom: 48px;
  }}

  .grid-card {{
    border: 3px solid var(--yellow2);
    background: var(--surface);
    border-radius: 4px;
    overflow: hidden;
    transition: transform 0.15s;
  }}

  .grid-card:hover {{
    transform: rotate(-0.5deg) scale(1.01);
    border-color: var(--yellow);
  }}

  .card-img-wrap {{
    overflow: hidden;
    background: #000;
    line-height: 0;
  }}

  .card-img {{
    width: 100%;
    height: 220px;
    object-fit: cover;
    display: block;
    filter: saturate(1.2) contrast(1.1);
    transition: filter 0.2s;
  }}

  .grid-card:hover .card-img {{
    filter: saturate(1.5) contrast(1.15);
  }}

  .card-body {{
    padding: 16px 18px;
    border-top: 3px solid var(--yellow2);
  }}

  .card-headline {{
    font-family: 'Oswald', sans-serif;
    font-size: 15px;
    font-weight: 700;
    color: var(--yellow);
    line-height: 1.3;
    margin-bottom: 10px;
  }}

  .card-caption {{
    font-size: 13px;
    color: var(--text);
    line-height: 1.55;
    font-style: italic;
    color: var(--text-dim);
  }}

  /* ── FOOTER ── */
  .footer {{
    border-top: 4px double var(--yellow);
    padding-top: 20px;
    margin-top: 40px;
    text-align: center;
    font-family: 'Oswald', sans-serif;
    font-size: 11px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--text-dim);
  }}

  .footer strong {{ color: var(--yellow); }}

  /* ── HALFTONE TEXTURE STRIP ── */
  .halftone-strip {{
    background:
      radial-gradient(circle, var(--red) 1px, transparent 1px);
    background-size: 8px 8px;
    height: 24px;
    opacity: 0.3;
    margin: 32px 0;
  }}

  @media (max-width: 600px) {{
    .masthead-title {{ font-size: 56px; }}
    .hero-headline {{ font-size: 22px; }}
    .story-grid {{ grid-template-columns: 1fr; }}
    .price-tag {{ display: none; }}
  }}
</style>
</head>
<body>

<div class="masthead">
  <div class="masthead-title">MAD<span>!</span></div>
  <div class="masthead-sub">World Edition</div>
  <div class="masthead-date">{date_str} &nbsp;·&nbsp; Today's Reality, Yesterday's Satire</div>
  <div class="price-tag">FREE<br>(Worth It)</div>
</div>

<div class="hero">
  <div class="hero-badge">🎯 TODAY'S BIG ONE</div>
  {'<img class="hero-img" src="' + hero_img_url + '" alt="' + hero_headline_escaped + '">' if hero_img_url else '<div class="hero-img-placeholder">🃏 IMAGE GENERATING…</div>'}
  <div class="hero-body">
    <div class="hero-headline">{hero['headline']}</div>
    <div class="hero-caption">{hero['caption']}</div>
  </div>
</div>

<div class="halftone-strip"></div>

<div class="section-label">MORE ABSURDITY FROM THE REAL WORLD</div>

<div class="story-grid">
{grid_cards}
</div>

<div class="footer">
  <strong>MAD! World</strong> &nbsp;·&nbsp;
  Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} &nbsp;·&nbsp;
  Images by Pollinations.ai &nbsp;·&nbsp;
  Satire by Groq &nbsp;·&nbsp;
  Reality by Whoever Is In Charge Up There
</div>

</body>
</html>"""

# ── ftp upload ─────────────────────────────────────────────────────────────────
def ftp_upload(local_path: Path, remote_filename: str = "MadWorld.html"):
    host = os.getenv("FTP_HOST", "")
    user = os.getenv("FTP_USER", "")
    pwd  = os.getenv("FTP_PASS", "")
    path = os.getenv("FTP_PATH", "/public_html/")
    if not all([host, user, pwd]):
        logger.warning("FTP credentials not set — skipping upload")
        return False
    try:
        with ftplib.FTP_TLS(host, timeout=30) as ftp:
            ftp.login(user, pwd)
            ftp.prot_p()
            ftp.cwd(path)
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_filename}", f)
        logger.info("✅ Uploaded to https://jonestech.xyz/%s", remote_filename)
        return True
    except Exception as e:
        logger.error("FTP upload failed: %s", e)
        return False

# ── main ───────────────────────────────────────────────────────────────────────
def main(dry_run: bool = False):
    date_str = datetime.now().strftime("%A %-d %B %Y")
    logger.info("🃏 Building MadWorld — %s", date_str)

    # 1. Collect headlines from all feeds
    all_headlines = []
    for query in NEWS_QUERIES:
        logger.info("Fetching: %s", query[:50])
        items = fetch_rss(query, limit=6)
        all_headlines.extend(i["title"] for i in items)

    # Deduplicate
    seen = set()
    unique = []
    for h in all_headlines:
        key = h.lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(h)
    logger.info("Got %d unique headlines", len(unique))

    # 2. Groq picks + writes captions
    logger.info("Asking Groq to pick and satirize...")
    stories = groq_pick_stories(unique[:40])
    logger.info("Got %d stories from Groq", len(stories))

    # 3. Generate images via HF Inference API
    if HF_TOKEN:
        logger.info("Generating %d images via Hugging Face...", len(stories))
        for i, story in enumerate(stories):
            w, h = (1200, 700) if i == 0 else (600, 400)
            logger.info("  Image %d/%d: %s", i + 1, len(stories), story.get("image_prompt", "")[:60])
            story["image_data"] = generate_image_b64(story.get("image_prompt", "satirical cartoon"), width=w, height=h)
            time.sleep(1)  # be polite to the free tier
    else:
        logger.warning("HF_TOKEN not set — pages will render without images. Add HF_TOKEN secret.")
        for story in stories:
            story["image_data"] = ""

    # 4. Build HTML
    logger.info("Building HTML...")
    html = build_html(stories, date_str)

    # 4. Save
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    logger.info("✅ Saved to %s", OUTPUT_PATH)

    if dry_run:
        logger.info("Dry run — skipping FTP upload")
        return

    # 5. FTP upload
    logger.info("Uploading to jonestech.xyz...")
    ftp_upload(OUTPUT_PATH)
    logger.info("🎉 MadWorld done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
