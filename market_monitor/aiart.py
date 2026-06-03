"""
AiArt Daily Gallery — top voted AI art from Civitai.

- Server-side: fetches 30 images from Civitai with API token
- Client-side: shuffles 20 from the 30 on load + "Load New Batch" reshuffles
  (no client-side API calls — avoids CORS/auth issues)
- FTP uploads to jonestech.xyz/AiArt.html

Usage:
    python aiart.py
    python aiart.py --dry-run
"""

import argparse
import ftplib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from openai import OpenAI

_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
CIVITAI_API_TOKEN = os.getenv("CIVITAI_API_TOKEN", "")
OUTPUT_PATH       = Path(os.getenv("OUTPUT_PATH", "/tmp/AiArt.html"))

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)
FALLBACKS = ["Visions of the Machine", "Dreams in Pixels", "The Synthetic Eye",
             "Worlds Made of Light", "Neural Reverie", "The Imagined Real"]


def fetch_civitai(count: int = 30) -> list[dict]:
    headers = {"Authorization": f"Bearer {CIVITAI_API_TOKEN}", "Content-Type": "application/json"}
    url = f"https://civitai.com/api/v1/images?limit={count}&sort=Most+Reactions&period=Day&nsfw=None&type=image"
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            logger.info("Civitai status: %d", r.status_code)
            r.raise_for_status()
            items = r.json().get("items", [])
            results = []
            for img in items:
                src = img.get("url", "")
                if not src:
                    continue
                src = src.replace("/original=true/", "/width=1200/")
                meta   = img.get("meta") or {}
                stats  = img.get("stats") or {}
                results.append({
                    "url":      src,
                    "prompt":   (meta.get("prompt") or "")[:160],
                    "hearts":   stats.get("heartCount", 0),
                    "likes":    stats.get("likeCount", 0),
                    "username": img.get("username", ""),
                    "width":    img.get("width", 800),
                    "height":   img.get("height", 600),
                    "id":       img.get("id", ""),
                })
            logger.info("Civitai: %d images", len(results))
            return results
        except Exception as e:
            logger.warning("Civitai attempt %d failed: %s", attempt + 1, e)
    return []


def groq_headline(date_str: str, images: list[dict]) -> str:
    if not GROQ_API_KEY:
        return FALLBACKS[hash(date_str) % len(FALLBACKS)]
    prompts = [img["prompt"][:80] for img in images if img.get("prompt")][:5]
    ctx = "\n".join(f"- {p}" for p in prompts) if prompts else "top voted AI art"
    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return only a headline — 3 to 5 words, poetic, no quotes, no punctuation at end."},
                {"role": "user",   "content": f"Today is {date_str}. Magazine headline for today's top voted AI art gallery.\n{ctx}"}
            ],
            temperature=0.85, max_tokens=20,
        )
        return resp.choices[0].message.content.strip().strip('"\'').rstrip(".")
    except Exception as e:
        logger.warning("Groq failed: %s", e)
        return FALLBACKS[hash(date_str) % len(FALLBACKS)]


def build_html(images: list[dict], headline: str, date_str: str, generated_at: str) -> str:
    images_json = json.dumps(images, ensure_ascii=False)
    count = len(images)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Art Daily — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&family=Playfair+Display:ital,wght@0,700;0,900;1,700&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:#080808; --surface:#111; --border:#1e1e1e; --text:#e8e8e8; --dim:#777; --accent:#c084fc; --accent2:#38bdf8; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:'Inter',sans-serif; min-height:100vh; }}
  .header {{ padding:48px 40px 36px; border-bottom:1px solid var(--border); background:linear-gradient(180deg,#0d0d0d 0%,var(--bg) 100%); }}
  .header-inner {{ max-width:1600px; margin:0 auto; display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap; gap:16px; }}
  .site-name {{ font-size:11px; font-weight:700; letter-spacing:.25em; text-transform:uppercase; color:var(--accent); margin-bottom:10px; }}
  .header-title {{ font-family:'Playfair Display',serif; font-size:clamp(28px,5vw,54px); font-weight:900; line-height:1.1; color:#fff; }}
  .header-title em {{ color:var(--accent); font-style:italic; }}
  .header-right {{ text-align:right; }}
  .header-date {{ font-size:13px; color:var(--dim); font-weight:500; margin-bottom:6px; }}
  .image-count {{ font-size:11px; color:var(--dim); }}
  .gallery-wrap {{ max-width:1600px; margin:0 auto; padding:36px 24px 60px; }}
  .masonry {{ columns:4 280px; column-gap:14px; }}
  .card {{ position:relative; break-inside:avoid; margin-bottom:14px; border-radius:10px; overflow:hidden; background:var(--surface); cursor:pointer; transition:transform .2s,box-shadow .2s; }}
  .card:hover {{ transform:translateY(-3px); box-shadow:0 16px 40px rgba(0,0,0,.7); z-index:2; }}
  .card img {{ display:block; width:100%; height:auto; transition:filter .3s; }}
  .card:hover img {{ filter:brightness(.3); }}
  .overlay {{ position:absolute; inset:0; padding:16px; display:flex; flex-direction:column; justify-content:flex-end; gap:5px; opacity:0; transition:opacity .3s; pointer-events:none; background:linear-gradient(to top,rgba(0,0,0,.88) 0%,transparent 60%); }}
  .card:hover .overlay {{ opacity:1; pointer-events:auto; }}
  .overlay-actions {{ display:flex; gap:8px; margin-bottom:4px; }}
  .overlay-btn {{ font-size:11px; font-weight:600; padding:4px 10px; border-radius:5px; text-decoration:none; cursor:pointer; border:none; }}
  .btn-img {{ background:rgba(255,255,255,.15); color:#fff; }}
  .btn-img:hover {{ background:rgba(255,255,255,.25); }}
  .btn-civitai {{ background:rgba(192,132,252,.2); color:var(--accent); border:1px solid var(--accent); }}
  .btn-civitai:hover {{ background:rgba(192,132,252,.35); }}
  .reactions {{ font-size:12px; font-weight:600; color:rgba(255,255,255,.9); }}
  .by {{ font-size:11px; color:var(--accent); font-weight:600; }}
  .prompt {{ font-size:11px; line-height:1.5; color:rgba(255,255,255,.8); font-style:italic; word-break:break-word; }}
  .regen-wrap {{ text-align:center; padding:28px 0 0; }}
  .regen-btn {{ background:#1a1a1a; color:var(--accent); border:1px solid var(--accent); padding:10px 28px; border-radius:8px; font-size:13px; font-weight:600; cursor:pointer; letter-spacing:.05em; transition:background .15s; }}
  .regen-btn:hover {{ background:#2a1a3a; }}
  .footer {{ border-top:1px solid var(--border); padding:20px 40px; max-width:1600px; margin:0 auto; display:flex; justify-content:space-between; font-size:11px; color:var(--dim); }}
  .footer a {{ color:var(--accent2); text-decoration:none; }}
  @media(max-width:600px) {{
    .header {{ padding:28px 20px 20px; }} .gallery-wrap {{ padding:20px 12px 50px; }}
    .masonry {{ columns:2 160px; column-gap:8px; }} .card {{ margin-bottom:8px; border-radius:6px; }}
    .header-right {{ display:none; }}
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
      <div class="image-count" id="count-label">{count} images · <a href="https://civitai.com" target="_blank" style="color:var(--accent2);text-decoration:none">Civitai</a></div>
    </div>
  </div>
</div>

<div class="gallery-wrap">
  <div class="masonry" id="grid"></div>
  <div class="regen-wrap">
    <button class="regen-btn" onclick="showBatch()">↻ Load New Batch</button>
  </div>
</div>

<div class="footer">
  <span>Updated {generated_at} · Top voted AI art via <a href="https://civitai.com" target="_blank">Civitai</a></span>
  <span><a href="/daily.html">← Daily Brief</a></span>
</div>

<script>
// Initial images baked in — shown instantly on page load
const INITIAL = {images_json};

function renderCards(images) {{
  const grid = document.getElementById('grid');
  const countLabel = document.getElementById('count-label');
  grid.innerHTML = '';
  images.forEach(img => {{
    const civitaiUrl = img.id ? `https://civitai.com/images/${{img.id}}` : 'https://civitai.com';
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <img src="${{img.url}}" loading="lazy" width="${{img.width}}" height="${{img.height}}" onerror="this.closest('.card').remove()">
      <div class="overlay">
        <div class="overlay-actions">
          <a class="overlay-btn btn-img" href="${{img.url}}" target="_blank">🔍 Full image</a>
          <a class="overlay-btn btn-civitai" href="${{civitaiUrl}}" target="_blank">↗ Civitai</a>
        </div>
        ${{(img.hearts||img.likes) ? `<div class="reactions">❤️ ${{img.hearts.toLocaleString()}} &nbsp;👍 ${{img.likes.toLocaleString()}}</div>` : ''}}
        ${{img.username ? `<div class="by">by ${{img.username}}</div>` : ''}}
        ${{img.prompt ? `<p class="prompt">${{img.prompt.slice(0,160)}}${{img.prompt.length>160?'…':''}}</p>` : ''}}
      </div>`;
    grid.appendChild(card);
  }});
  countLabel.innerHTML = images.length + ' images · <a href="https://civitai.com" target="_blank" style="color:var(--accent2);text-decoration:none">Civitai</a>';
}}

async function loadBatch() {{
  const btn = document.querySelector('.regen-btn');
  btn.disabled = true;
  btn.textContent = 'Loading…';

  // AllTime pool = millions of images, random page = genuinely different every time
  const page = Math.floor(Math.random() * 500) + 1;
  const url = `https://civitai.com/api/v1/images?limit=20&sort=Most+Reactions&period=AllTime&nsfw=None&type=image&page=${{page}}`;

  try {{
    const r = await fetch(url);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const items = (await r.json()).items || [];
    const images = items.filter(i => i.url).slice(0, 20).map(i => {{
      const meta = i.meta || {{}};
      const stats = i.stats || {{}};
      return {{
        url: i.url.replace('/original=true/', '/width=1200/'),
        prompt: (meta.prompt || '').slice(0, 160),
        hearts: stats.heartCount || 0,
        likes: stats.likeCount || 0,
        username: i.username || '',
        width: i.width || 800,
        height: i.height || 600,
        id: i.id || '',
      }};
    }});
    if (images.length) renderCards(images);
    else throw new Error('No images returned');
  }} catch(e) {{
    // Fall back to initial set on error
    renderCards(INITIAL);
  }}

  btn.disabled = false;
  btn.textContent = '↻ Load New Batch';
}}

// Show baked-in images immediately
renderCards(INITIAL);
</script>
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
    for attempt in range(3):
        try:
            with ftplib.FTP_TLS(host, timeout=30) as ftp:
                ftp.login(user, pwd)
                ftp.cwd(path)
                with open(local_path, "rb") as f:
                    ftp.storbinary(f"STOR {remote_filename}", f)
            logger.info("✅ Uploaded to https://jonestech.xyz/%s", remote_filename)
            return True
        except Exception as e:
            logger.warning("FTP attempt %d failed: %s", attempt + 1, e)
    logger.error("All FTP attempts failed")
    return False


def main(dry_run: bool = False):
    date_str     = datetime.now().strftime("%A %-d %B %Y")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info("🎨 Building AiArt Daily Gallery — %s", date_str)

    images   = fetch_civitai(count=30)
    headline = groq_headline(date_str, images)
    html     = build_html(images, headline, date_str, generated_at)

    OUTPUT_PATH.write_text(html, encoding="utf-8")
    logger.info("✅ Saved (%d images)", len(images))

    if dry_run:
        logger.info("Dry run — skipping FTP")
        return

    ftp_upload(OUTPUT_PATH)
    logger.info("🎉 Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
