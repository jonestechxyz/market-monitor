"""
AiArt Daily Gallery — top scored AI-generated art from Danbooru.

- Fetches top 20 scored ai-generated posts from Danbooru (no API key needed)
- Groq writes a daily headline
- Builds a dark masonry-grid HTML gallery with tags + score on hover
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

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OUTPUT_PATH  = Path(os.getenv("OUTPUT_PATH", "/tmp/AiArt.html"))

DANBOORU_URL = (
    "https://danbooru.donmai.us/posts.json"
    "?tags=ai-generated+rating:general+order:score"
    "&limit=30"
)

# Tags to clean up for display (technical/meta tags)
SKIP_TAGS = {
    "ai-generated", "absurdres", "highres", "bad_id", "bad_pixiv_id",
    "bad_twitter_id", "commentary", "english_commentary", "translated",
    "jpeg_artifacts", "watermark", "signature", "artist_name",
}

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)


def fetch_danbooru_images(count: int = 20) -> list[dict]:
    try:
        r = requests.get(
            DANBOORU_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        r.raise_for_status()
        posts = r.json()
        logger.info("Danbooru returned %d posts", len(posts))

        results = []
        for post in posts:
            url = post.get("file_url", "")
            # skip videos, webm, zip (ugoira)
            if not url or any(url.endswith(ext) for ext in (".mp4", ".webm", ".zip", ".swf")):
                continue
            # use sample URL for large originals to keep page fast
            src = post.get("large_file_url") or post.get("sample_file_url") or url

            raw_tags = post.get("tag_string", "")
            tags = [t for t in raw_tags.split() if t not in SKIP_TAGS][:12]

            results.append({
                "url":    src,
                "score":  post.get("score", 0),
                "tags":   tags,
                "width":  post.get("image_width", 512),
                "height": post.get("image_height", 512),
                "id":     post.get("id", ""),
            })
            if len(results) >= count:
                break

        logger.info("Using %d images", len(results))
        return results
    except Exception as e:
        logger.error("Danbooru fetch failed: %s", e)
        return []


def groq_headline(images: list[dict], date_str: str) -> str:
    if not GROQ_API_KEY:
        return "Today's Best AI Art"
    # pull a sample of descriptive tags to give Groq context
    tag_sample = []
    for img in images[:6]:
        tag_sample.extend(img["tags"][:4])
    tag_str = ", ".join(dict.fromkeys(tag_sample))[:200]
    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a creative art curator. Return only the headline — 3 to 6 words, evocative, no quotes, no punctuation at end."},
                {"role": "user",   "content": f"Today is {date_str}. Write a poetic 3–6 word magazine-style headline for a daily gallery of today's top voted AI-generated illustrations. These tags describe the art: {tag_str}"}
            ],
            temperature=0.85,
            max_tokens=20,
        )
        headline = resp.choices[0].message.content.strip().strip('"\'').rstrip(".")
        logger.info("Headline: %s", headline)
        return headline
    except Exception as e:
        logger.warning("Groq headline failed: %s", e)
        return "Today's Best AI Art"


def build_html(images: list[dict], headline: str, date_str: str, generated_at: str) -> str:
    def safe(s: str) -> str:
        return s.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

    cards_html = ""
    for img in images:
        tags_display = ", ".join(t.replace("_", " ") for t in img["tags"][:8])
        tags_safe    = safe(tags_display)
        score_html   = f'<div class="score">▲ {img["score"]:,}</div>' if img["score"] else ""
        post_url     = f"https://danbooru.donmai.us/posts/{img['id']}"

        cards_html += f"""
    <div class="card" onclick="window.open('{post_url}','_blank')">
      <img src="{img['url']}" alt="{tags_safe}" loading="lazy" width="{img['width']}" height="{img['height']}" onerror="this.closest('.card').remove()">
      <div class="overlay">
        {score_html}
        {"<p class='tags'>" + tags_safe + "</p>" if tags_safe else ""}
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

  .overlay {{ position: absolute; inset: 0; padding: 16px; display: flex; flex-direction: column; justify-content: flex-end; gap: 6px; opacity: 0; transition: opacity 0.3s ease; pointer-events: none; background: linear-gradient(to top, rgba(0,0,0,0.9) 0%, transparent 60%); }}
  .card:hover .overlay {{ opacity: 1; }}
  .score {{ font-size: 13px; font-weight: 700; color: var(--accent); }}
  .tags {{ font-size: 11px; line-height: 1.6; color: rgba(255,255,255,0.8); font-style: italic; word-break: break-word; }}

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
      <div class="site-name">AI Art Daily · Top Scored</div>
      <h1 class="header-title"><em>{headline}</em></h1>
    </div>
    <div class="header-right">
      <div class="header-date">{date_str}</div>
      <div class="image-count">{len(images)} images · <a href="https://danbooru.donmai.us" target="_blank" style="color:var(--accent2);text-decoration:none">Danbooru</a></div>
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
  <span>Updated {generated_at} · AI art via <a href="https://danbooru.donmai.us" target="_blank">Danbooru</a></span>
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

    images   = fetch_danbooru_images(count=20)
    headline = groq_headline(images, date_str)
    html     = build_html(images, headline, date_str, generated_at)

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
