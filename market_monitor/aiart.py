"""
AiArt Daily Gallery — top voted AI art of the day from Civitai.

- Fetches top 20 most-reacted images from Civitai (no API key needed)
- Groq writes a daily headline based on what came in
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
import re
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

CIVITAI_API = (
    "https://civitai.com/api/v1/images"
    "?limit=30&sort=Most+Reactions&period=Day&nsfw=None&type=image"
)

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)


def fetch_civitai_images(count: int = 20) -> list[dict]:
    """Fetch today's top-reacted AI images from Civitai."""
    try:
        r = requests.get(
            CIVITAI_API,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        logger.info("Civitai returned %d images", len(items))

        results = []
        for img in items:
            url = img.get("url", "")
            if not url:
                continue
            meta   = img.get("meta") or {}
            stats  = img.get("stats") or {}
            prompt = meta.get("prompt", "")
            hearts = stats.get("heartCount", 0)
            likes  = stats.get("likeCount", 0)
            total  = hearts + likes
            results.append({
                "url":      url,
                "prompt":   prompt,
                "width":    img.get("width", 512),
                "height":   img.get("height", 512),
                "hearts":   hearts,
                "likes":    likes,
                "total":    total,
                "username": img.get("username", ""),
            })
            if len(results) >= count:
                break

        logger.info("Using %d images", len(results))
        return results
    except Exception as e:
        logger.error("Civitai fetch failed: %s", e)
        return []


def groq_headline(images: list[dict], date_str: str) -> str:
    """Use Groq to write a punchy daily headline based on today's top images."""
    prompts = [img["prompt"][:120] for img in images if img["prompt"]][:8]
    if not prompts or not GROQ_API_KEY:
        return "Today's Best AI Art"
    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a creative art curator. Return only the headline — no quotes, no punctuation at the end, no explanation."},
                {"role": "user", "content": f"Today is {date_str}. Based on these AI image prompts from today's top voted gallery, write one evocative 4–7 word headline that captures the mood or dominant aesthetic:\n\n" + "\n".join(f"- {p}" for p in prompts)}
            ],
            temperature=0.8,
            max_tokens=30,
        )
        headline = resp.choices[0].message.content.strip().strip('"\'').rstrip(".")
        logger.info("Headline: %s", headline)
        return headline
    except Exception as e:
        logger.warning("Groq headline failed: %s", e)
        return "Today's Best AI Art"


def build_html(images: list[dict], headline: str, date_str: str) -> str:
    def safe(s: str) -> str:
        return s.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

    cards_html = ""
    for img in images:
        prompt_safe    = safe(img["prompt"][:300])
        prompt_display = safe(img["prompt"][:160]) + ("…" if len(img["prompt"]) > 160 else "")
        reactions_html = ""
        if img["hearts"] or img["likes"]:
            reactions_html = f'<div class="reactions">❤️ {img["hearts"]:,} &nbsp; 👍 {img["likes"]:,}</div>'
        by_html = f'<div class="by">by {safe(img["username"])}</div>' if img["username"] else ""

        # Use width param to get appropriately sized image from Civitai CDN
        src = img["url"]
        if "/width=" not in src:
            src = re.sub(r"(https://image\.civitai\.com/[^/]+/)", r"\1width=800/", src)

        cards_html += f"""
    <div class="card">
      <img src="{src}" alt="{prompt_safe}" loading="lazy" width="{img['width']}" height="{img['height']}" onerror="this.closest('.card').style.display='none'">
      <div class="overlay">
        {reactions_html}
        {by_html}
        <p class="prompt-text">{prompt_display}</p>
      </div>
    </div>"""

    no_images_msg = "" if images else '<p style="color:#666;text-align:center;padding:80px 0;grid-column:1/-1">No images today. Civitai may be unavailable.</p>'

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

  .header-title em {{ color: var(--accent); font-style: italic; }}

  .header-right {{ text-align: right; }}

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

  .card:hover img {{ filter: brightness(0.3); }}

  .overlay {{
    position: absolute;
    inset: 0;
    padding: 16px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    gap: 6px;
    opacity: 0;
    transition: opacity 0.3s ease;
    pointer-events: none;
    background: linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 60%);
  }}

  .card:hover .overlay {{ opacity: 1; }}

  .reactions {{
    font-size: 12px;
    font-weight: 600;
    color: rgba(255,255,255,0.9);
  }}

  .by {{
    font-size: 11px;
    color: var(--accent);
    font-weight: 600;
  }}

  .prompt-text {{
    font-size: 11px;
    line-height: 1.5;
    color: rgba(255,255,255,0.8);
    font-style: italic;
    word-break: break-word;
  }}

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
      <div class="site-name">AI Art Daily · Top Voted</div>
      <h1 class="header-title"><em>{headline}</em></h1>
    </div>
    <div class="header-right">
      <div class="header-date">{date_str}</div>
      <div class="image-count">{len(images)} images · <a href="https://civitai.com" target="_blank" style="color:var(--accent2);text-decoration:none">Civitai</a></div>
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
  <span>Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} · Top voted AI art via <a href="https://civitai.com" target="_blank">Civitai</a></span>
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

    images   = fetch_civitai_images(count=20)
    headline = groq_headline(images, date_str)
    html     = build_html(images, headline, date_str)

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
