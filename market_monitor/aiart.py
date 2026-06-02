"""
AiArt Daily Gallery — best AI-generated images from Lexica.art.

- Groq picks a daily theme (seeded by date for variety)
- Fetches top images from Lexica.art free API
- Builds a dark masonry-grid HTML gallery
- FTP uploads to jonestech.xyz/AiArt.html

Usage:
    python aiart.py
    python aiart.py --dry-run
"""

import argparse
import ftplib
import logging
import os
import random
import sys
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

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OUTPUT_PATH  = Path(os.getenv("OUTPUT_PATH", "/tmp/AiArt.html"))
LEXICA_API   = "https://lexica.art/api/v1/search?q={query}&n=30"

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

THEME_CANDIDATES = [
    "neon cyberpunk cities at night",
    "ethereal fantasy landscapes with floating islands",
    "ancient ruins reclaimed by nature",
    "deep sea bioluminescent creatures",
    "surreal dreamscape architecture",
    "mystical forest spirits glowing",
    "futuristic space colonies on alien worlds",
    "baroque oil painting style robots",
    "desert nomads in a post-apocalyptic world",
    "macro photography of crystalline structures",
    "art nouveau botanical gardens",
    "noir detective rain-soaked streets",
    "mythological gods in modern cities",
    "aurora borealis over ice castles",
    "steampunk clockwork cities",
    "enchanted underwater kingdoms",
    "retrofuturistic 1950s space age",
    "dark gothic cathedrals with stained glass",
    "hyperrealistic fruit and food still life",
    "psychedelic fractal mandalas",
    "lonely astronaut exploring alien landscapes",
    "dragons over medieval cityscapes",
    "minimalist zen gardens in fog",
    "vibrant Indian festival of colors",
    "biomechanical organisms fusing flesh and metal",
    "abandoned amusement parks overgrown",
    "celestial nebula skies over mountains",
    "samurai in cherry blossom storms",
    "art deco skyscrapers at golden hour",
    "microscopic worlds inside water droplets",
]


def pick_theme_with_groq(date_str: str) -> str:
    """Use Groq to pick and riff on a theme, seeded by today's date."""
    seed_theme = THEME_CANDIDATES[hash(date_str) % len(THEME_CANDIDATES)]
    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a creative AI art director. Return only the theme phrase — no preamble, no quotes, no punctuation at the end."},
                {"role": "user", "content": f"Today is {date_str}. Starting from this seed theme: '{seed_theme}' — give me one vivid, specific AI image search theme (5–10 words). Make it evocative and unique to today."}
            ],
            temperature=0.85,
            max_tokens=40,
        )
        theme = resp.choices[0].message.content.strip().strip('"\'').rstrip(".")
        logger.info("Groq theme: %s", theme)
        return theme
    except Exception as e:
        logger.warning("Groq theme selection failed, using seed: %s", e)
        return seed_theme


def fetch_lexica_images(theme: str, count: int = 20) -> list[dict]:
    """Fetch images from Lexica.art for the given theme."""
    try:
        url = LEXICA_API.format(query=requests.utils.quote(theme))
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        images = data.get("images", [])
        logger.info("Lexica returned %d images", len(images))

        results = []
        for img in images:
            src = img.get("src") or img.get("srcSmall") or ""
            prompt = img.get("prompt", "")
            width = img.get("width", 512)
            height = img.get("height", 512)
            if src and src.startswith("http"):
                results.append({"src": src, "prompt": prompt, "width": width, "height": height})
            if len(results) >= count:
                break

        logger.info("Using %d images", len(results))
        return results
    except Exception as e:
        logger.error("Lexica fetch failed: %s", e)
        return []


def build_html(images: list[dict], theme: str, date_str: str) -> str:
    def safe(s: str) -> str:
        return s.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

    cards_html = ""
    for img in images:
        prompt_safe = safe(img["prompt"][:200])
        prompt_display = safe(img["prompt"][:120]) + ("…" if len(img["prompt"]) > 120 else "")
        cards_html += f"""
    <div class="card">
      <img src="{img['src']}" alt="{prompt_safe}" loading="lazy" onerror="this.closest('.card').style.display='none'">
      <div class="overlay">
        <p class="prompt-text">{prompt_display}</p>
      </div>
    </div>"""

    no_images_msg = "" if images else '<p style="color:#666;text-align:center;padding:80px 0;grid-column:1/-1">No images found for today\'s theme. Try again later.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Art Daily — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&family=Playfair+Display:ital,wght@0,700;0,900;1,700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #080808;
    --surface: #111;
    --border: #1e1e1e;
    --text: #e8e8e8;
    --text-dim: #777;
    --accent: #c084fc;
    --accent2: #38bdf8;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    min-height: 100vh;
  }}

  /* HEADER */
  .header {{
    padding: 48px 40px 36px;
    border-bottom: 1px solid var(--border);
    background: linear-gradient(180deg, #0d0d0d 0%, var(--bg) 100%);
  }}

  .header-inner {{
    max-width: 1600px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    flex-wrap: wrap;
    gap: 16px;
  }}

  .site-name {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 10px;
  }}

  .header-title {{
    font-family: 'Playfair Display', serif;
    font-size: clamp(28px, 5vw, 54px);
    font-weight: 900;
    line-height: 1.1;
    color: #fff;
  }}

  .header-title em {{
    color: var(--accent);
    font-style: italic;
  }}

  .header-right {{
    text-align: right;
  }}

  .header-date {{
    font-size: 13px;
    color: var(--text-dim);
    font-weight: 500;
    margin-bottom: 6px;
  }}

  .image-count {{
    font-size: 11px;
    color: var(--text-dim);
    letter-spacing: 0.08em;
  }}

  /* GALLERY */
  .gallery-wrap {{
    max-width: 1600px;
    margin: 0 auto;
    padding: 36px 24px 80px;
  }}

  .masonry {{
    columns: 4 280px;
    column-gap: 14px;
  }}

  .card {{
    position: relative;
    break-inside: avoid;
    margin-bottom: 14px;
    border-radius: 10px;
    overflow: hidden;
    background: var(--surface);
    cursor: pointer;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
  }}

  .card:hover {{
    transform: translateY(-3px);
    box-shadow: 0 16px 40px rgba(0,0,0,0.7);
    z-index: 2;
  }}

  .card img {{
    display: block;
    width: 100%;
    height: auto;
    transition: filter 0.3s ease;
  }}

  .card:hover img {{
    filter: brightness(0.35);
  }}

  .overlay {{
    position: absolute;
    inset: 0;
    padding: 16px;
    display: flex;
    align-items: flex-end;
    opacity: 0;
    transition: opacity 0.3s ease;
    pointer-events: none;
  }}

  .card:hover .overlay {{
    opacity: 1;
  }}

  .prompt-text {{
    font-size: 12px;
    line-height: 1.55;
    color: rgba(255,255,255,0.92);
    font-style: italic;
    text-shadow: 0 1px 4px rgba(0,0,0,0.9);
    word-break: break-word;
  }}

  /* FOOTER */
  .footer {{
    border-top: 1px solid var(--border);
    padding: 20px 40px;
    max-width: 1600px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: var(--text-dim);
  }}

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
      <div class="image-count">{len(images)} images · Lexica.art</div>
    </div>
  </div>
</div>

<div class="gallery-wrap">
  <div class="masonry">
    {cards_html}
    {no_images_msg}
  </div>
</div>

<div class="footer">
  <span>Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} · Images via <a href="https://lexica.art" target="_blank">Lexica.art</a></span>
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
    date_str = datetime.now().strftime("%A %-d %B %Y")
    logger.info("🎨 Building AiArt Daily Gallery — %s", date_str)

    theme = pick_theme_with_groq(date_str)
    images = fetch_lexica_images(theme, count=20)

    if not images:
        logger.warning("No images fetched — building placeholder page")

    html = build_html(images, theme, date_str)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    logger.info("✅ Saved to %s", OUTPUT_PATH)

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
