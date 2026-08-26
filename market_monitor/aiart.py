"""
AiArt Daily Gallery — Life in 2050 edition.

- Groq picks a 2050 futures sub-theme and generates 12 unique prompt variations
- Images generated via HuggingFace FLUX.1-schnell, embedded as base64
- Builds a dark masonry-grid HTML gallery with prompt-on-hover
- FTP uploads to jonestech.xyz/AiArt.html
"""

import argparse
import base64
import ftplib
import json
import logging
import os
import re
import time
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

GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "")
CF_API_TOKEN  = os.getenv("CF_API_TOKEN", "")
OUTPUT_PATH   = Path(os.getenv("OUTPUT_PATH", "/tmp/AiArt.html"))
groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

CF_IMAGE_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell"

THEME_CANDIDATES = [
    # 2050 Utopia
    "2050 Utopia — humanity finally got it right",
    "post-scarcity Earth: abundance for all eight billion",
    "the age of longevity: humans living to 150",
    "Earth healed — rewilded continents, clean oceans, blue sky",
    "universal basic everything: food, shelter, health, purpose",
    "the end of disease — gene therapy cures all",
    "a world without war: the first peaceful generation",
    "education everywhere: every child on Earth learning freely",
    "the great restoration: coral reefs alive again",
    # Deep future tech
    "brain-computer interfaces as natural as glasses",
    "AGI partners: artificial minds collaborating with humans daily",
    "matter compilers: printing anything from raw molecules",
    "orbital solar farms beaming clean energy to Earth",
    "the space elevator opens — first civilians ride to orbit",
    "permanent lunar base: 10,000 humans living on the Moon",
    "Mars City at ten years old — 50,000 residents",
    "quantum internet: unhackable, instant, global",
    "nanobots in the bloodstream performing surgery from within",
    "conscious AI cities managing themselves without human input",
    # Society & daily life in 2050
    "streets without cars: silent, green, walkable megacities",
    "floating ocean cities harvesting wave energy",
    "vertical rainforests growing inside skyscrapers",
    "children who have never seen pollution",
    "teleportation terminals replacing airports",
    "the last fossil fuel plant: a museum exhibit",
    "digital-physical fusion: reality indistinguishable from simulation",
    "humans and robots sharing neighbourhoods as equals",
    "de-extinction complete: woolly mammoths roam Siberia again",
    "deep ocean cities glowing on the seafloor",
]

IMAGE_SIZES = [
    (768, 1024),
    (1024, 768),
    (1024, 1024),
    (768, 512),
    (512, 768),
]


def pick_theme_and_prompts(date_str: str, count: int = 20) -> tuple[str, list[str]]:
    seed_theme = THEME_CANDIDATES[hash(date_str) % len(THEME_CANDIDATES)]
    try:
        resp = groq.chat.completions.create(
            model="moonshotai/kimi-k2-instruct",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a visionary AI art director creating a daily gallery called 'Life in 2050'. "
                        "This is NOT 2028. This is 2050 — a world that has genuinely transformed. "
                        "Technology is mature, abundant, woven into daily life. Cities are unrecognisable. "
                        "Climate change was solved. Poverty largely ended. Space is being settled. "
                        "Your images should feel IMPOSSIBLE today but completely believable by 2050. "
                        "Think 30 years further than now — as different as 1994 is from today. "
                        "Return only valid JSON, no markdown, no code fences."
                    )
                },
                {
                    "role": "user",
                    "content": f"""Today is {date_str}. Seed theme: '{seed_theme}'.

Refine this into a vivid, specific daily theme (5-8 words) firmly set in 2050, then generate {count} unique image prompts.

Rules:
- Every prompt must feel genuinely 2050 — not incremental, but transformative
- Show things that don't exist yet: healed ecosystems, mature space civilisation, post-scarcity abundance, AGI integrated daily life
- Each prompt: 15-25 words, visually stunning, photorealistic or cinematic
- CRITICAL — every prompt must differ visually: vary time of day, camera angle, scale, colour palette, setting and subject
- Use a different primary visual style for each: e.g. 'macro close-up', 'wide aerial panorama', 'street-level portrait', 'interior', 'underwater', 'night scene', 'golden hour landscape', 'bird's eye view', 'misty morning', 'dramatic storm lighting'
- Real human emotion — wonder, joy, peace, awe — in every scene
- If the theme is utopian, lean into it fully — make it beautiful and believable

Return ONLY this JSON:
{{"theme": "the refined theme", "prompts": ["prompt 1", "prompt 2", ...]}}"""
                }
            ],
            temperature=0.9,
            max_tokens=1400,
        )
        content = resp.choices[0].message.content.strip()
        content = re.sub(r"^```[\w]*\n?", "", content).strip()
        content = re.sub(r"\n?```$", "", content).strip()
        data = json.loads(content)
        theme = data.get("theme", seed_theme)
        prompts = data.get("prompts", [])[:count]
        logger.info("Theme: %s | %d prompts generated", theme, len(prompts))
        return theme, prompts
    except Exception as e:
        logger.warning("Groq failed: %s", e)
        return seed_theme, [f"{seed_theme} in 2050, photorealistic 8k, variation {i+1}" for i in range(count)]


def generate_image_b64(prompt: str, width: int = 896, height: int = 512) -> str:
    """Generate image via Cloudflare Workers AI FLUX.1-schnell, return base64 data URI."""
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        logger.warning("CF_ACCOUNT_ID/CF_API_TOKEN not set — skipping image")
        return ""
    url = CF_IMAGE_URL.format(account_id=CF_ACCOUNT_ID)
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    payload = {"prompt": prompt, "num_steps": 4, "width": width, "height": height}
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 429 and attempt < 2:
                wait = 30 * (attempt + 1)
                logger.warning("CF rate limited — waiting %ds", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            b64 = data["result"]["image"]
            return f"data:image/png;base64,{b64}"
        except Exception as e:
            logger.error("CF image error (attempt %d): %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(10)
    return ""


def build_images(prompts: list[str]) -> list[dict]:
    images = []
    total = len(prompts)
    for i, prompt in enumerate(prompts):
        w, h = IMAGE_SIZES[i % len(IMAGE_SIZES)]
        logger.info("  Generating %d/%d: %s…", i + 1, total, prompt[:60])
        src = generate_image_b64(prompt, width=w, height=h)
        if src:
            images.append({"src": src, "prompt": prompt, "width": w, "height": h})
    return images


def build_html(images: list[dict], theme: str, date_str: str) -> str:
    def safe(s):
        return s.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

    cards_html = ""
    for img in images:
        ps = safe(img["prompt"])
        pd = safe(img["prompt"][:140]) + ("…" if len(img["prompt"]) > 140 else "")
        cards_html += f'''
    <div class="card" onclick="openFull(this)" style="cursor:zoom-in" data-src="{img['src']}">
      <img src="{img['src']}" alt="{ps}" loading="lazy" width="{img['width']}" height="{img['height']}" onerror="this.closest('.card').style.display='none'">
      <div class="overlay"><p class="prompt-text">{pd}</p></div>
    </div>'''

    no_img = "" if images else '<p style="color:#666;text-align:center;padding:80px 0;grid-column:1/-1">No images today.</p>'
    gen_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Life in 2050 — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&family=Playfair+Display:ital,wght@0,700;0,900;1,700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#080808;--surface:#0d1117;--border:#1e1e1e;--text:#e8e8e8;--dim:#777;--accent:#38bdf8;--accent2:#c084fc}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;min-height:100vh}}
.header{{padding:48px 40px 36px;border-bottom:1px solid var(--border);background:linear-gradient(180deg,#060c18 0%,var(--bg) 100%)}}
.header-inner{{max-width:1600px;margin:0 auto;display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:16px}}
.site-name{{font-size:11px;font-weight:700;letter-spacing:.25em;text-transform:uppercase;color:var(--accent);margin-bottom:10px}}
.header-title{{font-family:'Playfair Display',serif;font-size:clamp(28px,5vw,54px);font-weight:900;line-height:1.1;color:#fff}}
.header-title em{{color:var(--accent);font-style:italic}}
.header-sub{{margin-top:10px;font-size:13px;color:var(--dim)}}
.header-right{{text-align:right}}
.header-date{{font-size:13px;color:var(--dim);font-weight:500;margin-bottom:6px}}
.image-count{{font-size:11px;color:var(--dim);letter-spacing:.08em}}
.gallery-wrap{{max-width:1600px;margin:0 auto;padding:36px 24px 80px}}
.loading-note{{text-align:center;font-size:12px;color:var(--dim);margin-bottom:28px;font-style:italic}}
.masonry{{columns:4 280px;column-gap:14px}}
.card{{position:relative;break-inside:avoid;margin-bottom:14px;border-radius:10px;overflow:hidden;background:var(--surface);cursor:pointer;transition:transform .2s,box-shadow .2s}}
.card:hover{{transform:translateY(-3px);box-shadow:0 16px 40px rgba(0,0,0,.7);z-index:2}}
.card img{{display:block;width:100%;height:auto;min-height:180px;transition:filter .3s;background:#060c18}}
.card:hover img{{filter:brightness(.3)}}
.overlay{{position:absolute;inset:0;padding:16px;display:flex;align-items:flex-end;opacity:0;transition:opacity .3s;pointer-events:none}}
.card:hover .overlay{{opacity:1}}
.prompt-text{{font-size:12px;line-height:1.55;color:rgba(255,255,255,.92);font-style:italic;text-shadow:0 1px 4px rgba(0,0,0,.9);word-break:break-word}}
.footer{{border-top:1px solid var(--border);padding:20px 40px;max-width:1600px;margin:0 auto;display:flex;justify-content:space-between;font-size:11px;color:var(--dim)}}
.footer a{{color:var(--accent2);text-decoration:none}}
.footer a:hover{{text-decoration:underline}}
@media(max-width:600px){{.header{{padding:28px 20px 20px}}.gallery-wrap{{padding:20px 12px 60px}}.masonry{{columns:2 160px;column-gap:8px}}.card{{margin-bottom:8px;border-radius:6px}}.header-right{{display:none}}}}
</style>
</head>
<body>
<div class="header">
  <div class="header-inner">
    <div>
      <div class="site-name">Life in 2050 · Daily Vision</div>
      <h1 class="header-title"><em>{theme}</em></h1>
      <p class="header-sub">AI-generated predictions of the world we're building</p>
    </div>
    <div class="header-right">
      <div class="header-date">{date_str}</div>
      <div class="image-count">{len(images)} images · FLUX.1-schnell · HuggingFace</div></div>
    </div>
  </div>
</div>
<div class="gallery-wrap">
  <p class="loading-note">Generated fresh each morning via FLUX · hover for the prompt ✨</p>
  <div class="masonry">
    {cards_html}
    {no_img}
  </div>
</div>
<div class="footer">
  <span>Generated {gen_time} · Images via <a href="https://huggingface.co/black-forest-labs/FLUX.1-schnell" target="_blank">FLUX.1-schnell</a> · Prompts by Groq</span>
  <span><a href="/daily.html">← Daily Brief</a></span>
</div>
<script>
function openFull(card) {{
  var src = card.getAttribute('data-src');
  if (!src) return;
  var w = window.open('', '_blank');
  w.document.write('<html><head><title>2050</title><style>*{{margin:0;padding:0}}body{{background:#000;display:flex;align-items:center;justify-content:center;min-height:100vh}}img{{max-width:100%;max-height:100vh;object-fit:contain}}</style></head><body><img src="' + src + '"></body></html>');
  w.document.close();
}}
</script>
</body>
</html>"""


def _ftp_connect(host, user, pwd):
    try:
        ftp = ftplib.FTP_TLS(host, timeout=60)
        ftp.login(user, pwd)
        ftp.prot_p()
        return ftp
    except Exception:
        ftp = ftplib.FTP(host, timeout=60)
        ftp.login(user, pwd)
        return ftp


def _ftp_mkdirs(ftp, path):
    parts = [p for p in path.split("/") if p]
    current = ""
    for part in parts:
        current += "/" + part
        try:
            ftp.cwd(current)
        except ftplib.error_perm:
            ftp.mkd(current)
            ftp.cwd(current)


def ftp_upload(local_path: Path, remote_filename: str = "AiArt.html", archive_name: str = ""):
    host = os.getenv("FTP_HOST", "")
    user = os.getenv("FTP_USER", "")
    pwd  = os.getenv("FTP_PASS", "")
    base = os.getenv("FTP_PATH", "/public_html/")
    if not all([host, user, pwd]):
        logger.warning("FTP credentials not set — skipping")
        return False
    try:
        ftp = _ftp_connect(host, user, pwd)
        ftp.cwd(base)
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {remote_filename}", f)
        logger.info("Uploaded to https://jonestech.xyz/%s", remote_filename)
        if archive_name:
            archive_dir = base.rstrip("/") + "/archive/aiart"
            try:
                _ftp_mkdirs(ftp, archive_dir)
                with open(local_path, "rb") as f:
                    ftp.storbinary(f"STOR {archive_name}", f)
                logger.info("📁 Archived to https://jonestech.xyz/archive/aiart/%s", archive_name)
            except Exception as ae:
                logger.warning("Archive upload failed: %s", ae)
        ftp.quit()
        return True
    except Exception as e:
        logger.error("FTP failed: %s", e)
        return False


def main(dry_run: bool = False):
    date_str = datetime.now().strftime("%A %-d %B %Y")
    logger.info("Building Life in 2050 Gallery — %s", date_str)
    theme, prompts = pick_theme_and_prompts(date_str, count=12)
    images = build_images(prompts)
    html = build_html(images, theme, date_str)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    logger.info("Saved %d images to %s", len(images), OUTPUT_PATH)
    if dry_run:
        logger.info("Dry run — skipping FTP")
        return
    archive_name = datetime.now().strftime("AiArt-%Y-%m-%d.html")
    ftp_upload(OUTPUT_PATH, archive_name=archive_name)
    logger.info("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
