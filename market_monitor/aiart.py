"""
AiArt Daily Gallery — top scored AI-generated art from Danbooru.

- GitHub Actions: Groq writes the daily headline, FTPs the HTML shell
- Browser: JS fetches images from Danbooru API directly (bypasses Actions IP blocks)
- Dark masonry-grid gallery, tags + score on hover, click opens Danbooru post

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

from openai import OpenAI

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

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

FALLBACKS = [
    "Visions of the Machine", "Dreams in Pixels", "The Synthetic Eye",
    "Worlds Made of Light", "Neural Reverie", "The Imagined Real",
]


def groq_headline(date_str: str) -> str:
    if not GROQ_API_KEY:
        return FALLBACKS[hash(date_str) % len(FALLBACKS)]
    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return only a headline — 3 to 5 words, poetic, no quotes, no punctuation at end."},
                {"role": "user",   "content": f"Today is {date_str}. Write a magazine-style headline for a daily gallery of the internet's top voted AI-generated illustrations."}
            ],
            temperature=0.85, max_tokens=20,
        )
        h = resp.choices[0].message.content.strip().strip('"\'').rstrip(".")
        logger.info("Headline: %s", h)
        return h
    except Exception as e:
        logger.warning("Groq failed: %s", e)
        return FALLBACKS[hash(date_str) % len(FALLBACKS)]


def build_html(headline: str, date_str: str, generated_at: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Art Daily — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&family=Playfair+Display:ital,wght@0,700;0,900;1,700&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:#080808; --surface:#111; --border:#1e1e1e; --text:#e8e8e8; --text-dim:#777; --accent:#c084fc; --accent2:#38bdf8; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:'Inter',sans-serif; min-height:100vh; }}

  .header {{ padding:48px 40px 36px; border-bottom:1px solid var(--border); background:linear-gradient(180deg,#0d0d0d 0%,var(--bg) 100%); }}
  .header-inner {{ max-width:1600px; margin:0 auto; display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap; gap:16px; }}
  .site-name {{ font-size:11px; font-weight:700; letter-spacing:0.25em; text-transform:uppercase; color:var(--accent); margin-bottom:10px; }}
  .header-title {{ font-family:'Playfair Display',serif; font-size:clamp(28px,5vw,54px); font-weight:900; line-height:1.1; color:#fff; }}
  .header-title em {{ color:var(--accent); font-style:italic; }}
  .header-right {{ text-align:right; }}
  .header-date {{ font-size:13px; color:var(--text-dim); font-weight:500; margin-bottom:6px; }}
  .image-count {{ font-size:11px; color:var(--text-dim); }}

  .gallery-wrap {{ max-width:1600px; margin:0 auto; padding:36px 24px 80px; }}
  #status {{ text-align:center; font-size:13px; color:var(--text-dim); padding:20px 0 28px; font-style:italic; }}
  .masonry {{ columns:4 280px; column-gap:14px; }}

  .card {{ position:relative; break-inside:avoid; margin-bottom:14px; border-radius:10px; overflow:hidden; background:var(--surface); cursor:pointer; transition:transform 0.2s ease,box-shadow 0.2s ease; }}
  .card:hover {{ transform:translateY(-3px); box-shadow:0 16px 40px rgba(0,0,0,0.7); z-index:2; }}
  .card img {{ display:block; width:100%; height:auto; transition:filter 0.3s ease; }}
  .card:hover img {{ filter:brightness(0.3); }}
  .overlay {{ position:absolute; inset:0; padding:16px; display:flex; flex-direction:column; justify-content:flex-end; gap:6px; opacity:0; transition:opacity 0.3s ease; pointer-events:none; background:linear-gradient(to top,rgba(0,0,0,0.9) 0%,transparent 60%); }}
  .card:hover .overlay {{ opacity:1; }}
  .score {{ font-size:13px; font-weight:700; color:var(--accent); }}
  .tags {{ font-size:11px; line-height:1.6; color:rgba(255,255,255,0.8); font-style:italic; word-break:break-word; }}

  .footer {{ border-top:1px solid var(--border); padding:20px 40px; max-width:1600px; margin:0 auto; display:flex; justify-content:space-between; font-size:11px; color:var(--text-dim); }}
  .footer a {{ color:var(--accent2); text-decoration:none; }}
  .footer a:hover {{ text-decoration:underline; }}

  @media(max-width:600px) {{
    .header {{ padding:28px 20px 20px; }}
    .gallery-wrap {{ padding:20px 12px 60px; }}
    .masonry {{ columns:2 160px; column-gap:8px; }}
    .card {{ margin-bottom:8px; border-radius:6px; }}
    .header-right {{ display:none; }}
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
      <div class="image-count" id="count-label">Loading · <a href="https://danbooru.donmai.us" target="_blank" style="color:var(--accent2);text-decoration:none">Danbooru</a></div>
    </div>
  </div>
</div>

<div class="gallery-wrap">
  <div id="status">Loading today's top scored AI art…</div>
  <div class="masonry" id="grid"></div>
</div>

<div class="footer">
  <span>Updated {generated_at} · AI art via <a href="https://danbooru.donmai.us" target="_blank">Danbooru</a></span>
  <span><a href="/daily.html">← Daily Brief</a></span>
</div>

<script>
const SKIP = new Set(["ai-generated","absurdres","highres","bad_id","bad_pixiv_id",
  "bad_twitter_id","commentary","english_commentary","translated","jpeg_artifacts",
  "watermark","signature","artist_name"]);

(async () => {{
  const status = document.getElementById('status');
  const grid   = document.getElementById('grid');
  const countLabel = document.getElementById('count-label');
  const API = 'https://danbooru.donmai.us/posts.json?tags=ai-generated+rating:general+order:score&limit=30';

  try {{
    const res = await fetch(API);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const posts = await res.json();

    const valid = posts.filter(p => {{
      const u = p.large_file_url || p.file_url || '';
      return u && !['.mp4','.webm','.zip','.swf'].some(e => u.endsWith(e));
    }}).slice(0, 20);

    if (!valid.length) {{ status.textContent = 'No images today.'; return; }}

    status.style.display = 'none';
    countLabel.innerHTML = valid.length + ' images · <a href="https://danbooru.donmai.us" target="_blank" style="color:var(--accent2);text-decoration:none">Danbooru</a>';

    valid.forEach(post => {{
      const src   = post.large_file_url || post.file_url;
      const score = post.score || 0;
      const tags  = (post.tag_string || '').split(' ').filter(t => !SKIP.has(t)).slice(0, 8)
                      .map(t => t.replace(/_/g,' ')).join(', ');
      const postUrl = 'https://danbooru.donmai.us/posts/' + post.id;

      const card = document.createElement('div');
      card.className = 'card';
      card.onclick = () => window.open(postUrl, '_blank');
      card.innerHTML = `
        <img src="${{src}}" loading="lazy" width="${{post.image_width||512}}" height="${{post.image_height||512}}"
             onerror="this.closest('.card').remove()">
        <div class="overlay">
          ${{score ? '<div class="score">▲ ' + score.toLocaleString() + '</div>' : ''}}
          ${{tags  ? '<p class="tags">'  + tags  + '</p>' : ''}}
        </div>`;
      grid.appendChild(card);
    }});
  }} catch(e) {{
    status.textContent = 'Could not load images: ' + e.message;
  }}
}})();
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

    # Try plain FTP first (more reliable from CI runners), then FTPS
    for use_tls in (False, True):
        try:
            cls = ftplib.FTP_TLS if use_tls else ftplib.FTP
            with cls(host, timeout=60) as ftp:
                ftp.login(user, pwd)
                if use_tls:
                    ftp.prot_p()
                ftp.cwd(path)
                with open(local_path, "rb") as f:
                    ftp.storbinary(f"STOR {remote_filename}", f)
            logger.info("✅ Uploaded to https://jonestech.xyz/%s (tls=%s)", remote_filename, use_tls)
            return True
        except Exception as e:
            logger.warning("FTP upload failed (tls=%s): %s", use_tls, e)

    logger.error("All FTP attempts failed")
    return False


def main(dry_run: bool = False):
    date_str     = datetime.now().strftime("%A %-d %B %Y")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info("🎨 Building AiArt Daily Gallery — %s", date_str)

    headline = groq_headline(date_str)
    html     = build_html(headline, date_str, generated_at)

    OUTPUT_PATH.write_text(html, encoding="utf-8")
    logger.info("✅ Saved to %s", OUTPUT_PATH)

    if dry_run:
        logger.info("Dry run — skipping FTP upload")
        return

    ftp_upload(OUTPUT_PATH)
    logger.info("🎉 Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
