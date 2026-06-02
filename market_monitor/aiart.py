"""
AiArt Daily Gallery — top liked digital/AI art from Unsplash.

- Groq picks today's art style theme
- Fetches 20 images from Unsplash (existing UNSPLASH_ACCESS_KEY secret)
- Builds a dark masonry-grid HTML gallery with prompt + stats on hover
- FTP uploads to jonestech.xyz/AiArt.html

Usage:
    python aiart.py
    python aiart.py --dry-run
"""

import argparse
import ftplib
import logging
import os
from datetime import datetime, timezone
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

GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
UNSPLASH_KEY       = os.getenv("UNSPLASH_ACCESS_KEY", "")
OUTPUT_PATH        = Path(os.getenv("OUTPUT_PATH", "/tmp/AiArt.html"))
UNSPLASH_SEARCH    = "https://api.unsplash.com/search/photos"
UNSPLASH_RANDOM    = "https://api.unsplash.com/photos/random"

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

THEME_SEEDS = [
    "neon cyberpunk digital art",
    "fantasy concept art",
    "sci-fi space art",
    "surreal dreamscape art",
    "dark gothic illustration",
    "futuristic city digital art",
    "AI generated portrait art",
    "abstract generative art",
    "bioluminescent art",
    "steampunk illustration",
    "art nouveau digital",
    "psychedelic fractal art",
    "dark fantasy creature art",
    "retro synthwave art",
    "ethereal landscape art",
    "cosmic nebula art",
    "biomechanical art",
    "magical realism illustration",
    "noir digital illustration",
    "hyperrealistic digital painting",
]


def pick_theme(date_str: str) -> str:
    seed = THEME_SEEDS[hash(date_str) % len(THEME_SEEDS)]
    if not GROQ_API_KEY:
        return seed
    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return only a short search phrase (3-5 words) for finding beautiful AI/digital art images. No punctuation, no quotes."},
                {"role": "user",   "content": f"Today is {date_str}. Starting from '{seed}', give me one evocative 3-5 word search phrase for today's AI art gallery."}
            ],
            temperature=0.85, max_tokens=15,
        )
        theme = resp.choices[0].message.content.strip().strip('"\'').rstrip(".")
        logger.info("Theme: %s", theme)
        return theme
    except Exception as e:
        logger.warning("Groq theme failed: %s", e)
        return seed


def fetch_unsplash_images(theme: str, count: int = 20) -> list[dict]:
    if not UNSPLASH_KEY:
        logger.error("UNSPLASH_ACCESS_KEY not set")
        return []

    headers = {"Authorization": f"Client-ID {UNSPLASH_KEY}"}
    images  = []

    # Search for the theme
    try:
        r = requests.get(
            UNSPLASH_SEARCH,
            headers=headers,
            params={"query": theme, "per_page": count, "order_by": "relevant", "orientation": "all"},
            timeout=15,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        logger.info("Unsplash returned %d results for '%s'", len(results), theme)
        for img in results:
            urls = img.get("urls", {})
            src  = urls.get("regular") or urls.get("full") or ""
            if not src:
                continue
            user  = img.get("user", {})
            likes = img.get("likes", 0)
            desc  = img.get("description") or img.get("alt_description") or ""
            images.append({
                "url":      src,
                "desc":     desc[:200],
                "likes":    likes,
                "username": user.get("name", ""),
                "profile":  user.get("links", {}).get("html", ""),
                "width":    img.get("width", 800),
                "height":   img.get("height", 600),
            })
    except Exception as e:
        logger.error("Unsplash search failed: %s", e)

    # Top up with random if needed
    if len(images) < count:
        try:
            r = requests.get(
                UNSPLASH_RANDOM,
                headers=headers,
                params={"query": theme, "count": count - len(images), "orientation": "all"},
                timeout=15,
            )
            r.raise_for_status()
            for img in r.json():
                urls = img.get("urls", {})
                src  = urls.get("regular") or ""
                if src:
                    user = img.get("user", {})
                    images.append({
                        "url":      src,
                        "desc":     (img.get("description") or img.get("alt_description") or "")[:200],
                        "likes":    img.get("likes", 0),
                        "username": user.get("name", ""),
                        "profile":  user.get("links", {}).get("html", ""),
                        "width":    img.get("width", 800),
                        "height":   img.get("height", 600),
                    })
        except Exception as e:
            logger.warning("Unsplash random top-up failed: %s", e)

    logger.info("Using %d images", len(images))
    return images[:count]


def build_html(images: list[dict], theme: str, date_str: str, generated_at: str) -> str:
    def safe(s: str) -> str:
        return s.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

    cards_html = ""
    for img in images:
        desc_safe    = safe(img["desc"])
        desc_display = safe(img["desc"][:160]) + ("…" if len(img["desc"]) > 160 else "")
        likes_html   = f'<div class="reactions">❤️ {img["likes"]:,}</div>' if img["likes"] else ""
        profile_url  = img["profile"] or "https://unsplash.com"
        by_html      = f'<div class="by"><a href="{profile_url}?utm_source=aiart&utm_medium=referral" target="_blank">{safe(img["username"])}</a></div>' if img["username"] else ""
        cards_html += f"""
    <div class="card">
      <img src="{img['url']}" alt="{desc_safe}" loading="lazy" width="{img['width']}" height="{img['height']}" onerror="this.closest('.card').remove()">
      <div class="overlay">
        {likes_html}
        {by_html}
        {"<p class='prompt-text'>" + desc_display + "</p>" if desc_display else ""}
      </div>
    </div>"""

    no_images = "" if images else '<p style="color:#666;text-align:center;padding:80px 0">No images today.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Art Daily — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&family=Playfair+Display:ital,wght@0,700;0,900;1,700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #080808; --surface: #111; --border: #1e1e1e;
    --text: #e8e8e8; --text-dim: #777; --accent: #c084fc; --accent2: #38bdf8;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; min-height: 100vh; }}

  .header {{ padding: 48px 40px 36px; border-bottom: 1px solid var(--border); background: linear-gradient(180deg, #0d0d0d 0%, var(--bg) 100%); }}
  .header-inner {{ max-width: 1600px; margin: 0 auto; display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 16px; }}
  .site-name {{ font-size: 11px; font-weight: 700; letter-spacing: 0.25em; text-transform: uppercase; color: var(--accent); margin-bottom: 10px; }}
  .header-title {{ font-family: 'Playfair Display', serif; font-size: clamp(28px, 5vw, 54px); font-weight: 900; line-height: 1.1; color: #fff; }}
  .header-title em {{ color: var(--accent); font-style: italic; }}
  .header-right {{ text-align: right; }}
  .header-date {{ font-size: 13px; color: var(--text-dim); font-weight: 500; margin-bottom: 6px; }}
  .image-count {{ font-size: 11px; color: var(--text-dim); }}

  .gallery-wrap {{ max-width: 1600px; margin: 0 auto; padding: 36px 24px 80px; }}
  .masonry {{ columns: 4 280px; column-gap: 14px; }}

  .card {{ position: relative; break-inside: avoid; margin-bottom: 14px; border-radius: 10px; overflow: hidden; background: var(--surface); cursor: pointer; transition: transform 0.2s ease, box-shadow 0.2s ease; }}
  .card:hover {{ transform: translateY(-3px); box-shadow: 0 16px 40px rgba(0,0,0,0.7); z-index: 2; }}
  .card img {{ display: block; width: 100%; height: auto; transition: filter 0.3s ease; }}
  .card:hover img {{ filter: brightness(0.3); }}

  .overlay {{ position: absolute; inset: 0; padding: 16px; display: flex; flex-direction: column; justify-content: flex-end; gap: 5px; opacity: 0; transition: opacity 0.3s ease; pointer-events: none; background: linear-gradient(to top, rgba(0,0,0,0.88) 0%, transparent 65%); }}
  .card:hover .overlay {{ opacity: 1; pointer-events: auto; }}
  .reactions {{ font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.9); }}
  .by {{ font-size: 11px; color: var(--accent); font-weight: 600; }}
  .by a {{ color: var(--accent); text-decoration: none; }}
  .by a:hover {{ text-decoration: underline; }}
  .prompt-text {{ font-size: 11px; line-height: 1.5; color: rgba(255,255,255,0.8); font-style: italic; word-break: break-word; }}

  .footer {{ border-top: 1px solid var(--border); padding: 20px 40px; max-width: 1600px; margin: 0 auto; display: flex; justify-content: space-between; font-size: 11px; color: var(--text-dim); }}
  .footer a {{ color: var(--accent2); text-decoration: none; }}
  .footer a:hover {{ text-decoration: underline; }}

  @media (max-width: 600px) {{
    .header {{ padding: 28px 20px 20px; }}
    .gallery-wrap {{ padding: 20px 12px 60px; }}
    .masonry {{ columns: 2 160px; column-gap: 8px; }}
    .card {{ margin-bottom: 8px; border-radius: 6px; }}
    .header-right {{ display: none; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <div>
      <div class="site-name">AI Art Daily</div>
      <h1 class="header-title"><em>{theme}</em></h1>
    </div>
    <div class="header-right">
      <div class="header-date">{date_str}</div>
      <div class="image-count">{len(images)} images · <a href="https://unsplash.com?utm_source=aiart&utm_medium=referral" target="_blank" style="color:var(--accent2);text-decoration:none">Unsplash</a></div>
    </div>
  </div>
</div>

<div class="gallery-wrap">
  <div class="masonry">
    {cards_html}
    {no_images}
  </div>
</div>

<div class="footer">
  <span>Updated {generated_at} · Photos via <a href="https://unsplash.com?utm_source=aiart&utm_medium=referral" target="_blank">Unsplash</a></span>
  <span><a href="/daily.html">← Daily Brief</a></span>
</div>

</body>
</html>"""


def ftp_upload(local_path: Path, remote_filename: str = "AiArt.html"):
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


def main(dry_run: bool = False):
    date_str     = datetime.now().strftime("%A %-d %B %Y")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info("🎨 Building AiArt Daily Gallery — %s", date_str)

    theme  = pick_theme(date_str)
    images = fetch_unsplash_images(theme, count=20)
    html   = build_html(images, theme, date_str, generated_at)

    OUTPUT_PATH.write_text(html, encoding="utf-8")
    logger.info("✅ Saved to %s (%d images)", OUTPUT_PATH, len(images))

    if dry_run:
        logger.info("Dry run — skipping FTP upload")
        return

    logger.info("Uploading to jonestech.xyz...")
    ftp_upload(OUTPUT_PATH)
    logger.info("🎉 Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
