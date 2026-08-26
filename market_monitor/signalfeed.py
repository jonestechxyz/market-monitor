"""
Signal — Daily Futurology Briefing.

Each day: one near-future forecast on a rotating theme, written like a serious
analyst briefing. 1-year, 3-year, or 5-year horizon. One CF image. Clean sci-fi
terminal aesthetic. Archives daily to /archive/signal/.

Usage:
    python signal.py
    python signal.py --dry-run
"""

import ftplib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import base64
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
FTP_HOST      = os.getenv("FTP_HOST", "")
FTP_USER      = os.getenv("FTP_USER", "")
FTP_PASS      = os.getenv("FTP_PASS", "")
FTP_PATH      = os.getenv("FTP_PATH", "/")
OUTPUT_PATH   = Path(os.getenv("OUTPUT_PATH", "/tmp/Signal.html"))

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)
CF_IMAGE_URL  = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell"

# ── theme rotation ─────────────────────────────────────────────────────────────
THEMES = [
    ("Artificial Intelligence",     "AI systems, language models, automation, and machine cognition"),
    ("Biotechnology",               "gene editing, longevity, synthetic biology, and brain-computer interfaces"),
    ("Energy & Climate",            "fusion, renewables, carbon capture, and planetary-scale intervention"),
    ("Cities & Architecture",       "urban design, housing, autonomous transport, and living infrastructure"),
    ("Space & Exploration",         "orbital industry, lunar bases, Mars, and deep space"),
    ("Work & Economics",            "automation's impact on labour, UBI, new economic models"),
    ("Consciousness & Neuroscience","brain simulation, memory, identity, and the science of mind"),
    ("Materials & Manufacturing",   "nanotechnology, programmable matter, and molecular assembly"),
    ("Medicine & Health",           "AI diagnostics, personalised medicine, and pandemic prevention"),
    ("Communication & Society",     "post-social-media, AR/VR integration, collective intelligence"),
]

HORIZONS = ["1 year", "3 years", "5 years"]

# ── groq forecast ──────────────────────────────────────────────────────────────
def get_forecasts(day_of_year: int) -> dict:
    lead_theme_name, lead_theme_desc = THEMES[day_of_year % len(THEMES)]
    lead_horizon = HORIZONS[day_of_year % len(HORIZONS)]

    # Pick 3 different supporting themes from the rest
    supporting = [THEMES[(day_of_year + i + 1) % len(THEMES)] for i in range(3)]
    supporting_horizons = [HORIZONS[(day_of_year + i + 1) % len(HORIZONS)] for i in range(3)]

    prompt = f"""You are a rigorous futurist analyst writing a daily Signal briefing page.

Produce a JSON object with this exact structure:

{{
  "lead": {{
    "theme": "{lead_theme_name}",
    "horizon": "{lead_horizon}",
    "headline": "Sharp forecast statement, max 12 words",
    "subhead": "One sentence expanding the headline, max 25 words",
    "body": "Three substantive paragraphs separated by blank lines. Para 1: what is already happening now that makes this credible. Para 2: the specific threshold or change crossed within {lead_horizon}. Para 3: what this means for society. Each paragraph 3-4 sentences. Analytical, grounded, no hype.",
    "signal_tags": ["3 to 5 weak-signal keyword tags"],
    "image_prompt": "Cinematic near-future scene, photorealistic, no text, max 20 words"
  }},
  "signals": [
    {{
      "theme": "{supporting[0][0]}",
      "horizon": "{supporting_horizons[0]}",
      "headline": "Sharp forecast, max 10 words",
      "summary": "2-3 sentences. One concrete prediction grounded in current trends."
    }},
    {{
      "theme": "{supporting[1][0]}",
      "horizon": "{supporting_horizons[1]}",
      "headline": "Sharp forecast, max 10 words",
      "summary": "2-3 sentences. One concrete prediction grounded in current trends."
    }},
    {{
      "theme": "{supporting[2][0]}",
      "horizon": "{supporting_horizons[2]}",
      "headline": "Sharp forecast, max 10 words",
      "summary": "2-3 sentences. One concrete prediction grounded in current trends."
    }}
  ]
}}

Return ONLY the JSON. No markdown. No commentary."""

    resp = groq.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2000,
    )
    raw = resp.choices[0].message.content.strip()
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON in Groq response")
    return json.loads(match.group(0))


# ── image generation ───────────────────────────────────────────────────────────
def generate_image_b64(prompt: str) -> str:
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        return ""
    url = CF_IMAGE_URL.format(account_id=CF_ACCOUNT_ID)
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    payload = {"prompt": f"cinematic near-future photorealistic, {prompt}", "num_steps": 4, "width": 1024, "height": 576}
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 429 and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            resp.raise_for_status()
            b64 = resp.json()["result"]["image"]
            return f"data:image/png;base64,{b64}"
        except Exception as e:
            logger.error("CF image error (attempt %d): %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(10)
    return ""


# ── html builder ───────────────────────────────────────────────────────────────
def build_html(data: dict, image_data: str, date_str: str) -> str:
    forecast = data["lead"]
    signals  = data.get("signals", [])

    tags_html = "".join(f'<span class="tag">{t}</span>' for t in forecast.get("signal_tags", []))
    img_html  = f'<img class="hero-img" src="{image_data}" alt="signal image">' if image_data else '<div class="hero-placeholder"></div>'
    paragraphs = forecast["body"].strip().split("\n\n")
    body_html  = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())

    signals_html = ""
    for s in signals:
        signals_html += f"""
        <div class="signal-card">
          <div class="signal-meta">
            <span class="signal-theme">{s['theme']}</span>
            <span class="signal-horizon">{s['horizon']}</span>
          </div>
          <div class="signal-headline">{s['headline']}</div>
          <div class="signal-summary">{s['summary']}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Signal — {date_str}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&display=swap');

  :root {{
    --bg:       #080c12;
    --surface:  #0d1520;
    --border:   #1a2a40;
    --accent:   #00c8ff;
    --accent2:  #0066ff;
    --text:     #c8d8e8;
    --text-dim: #5a7a9a;
    --text-bright: #e8f4ff;
    --green:    #00ff88;
    --warn:     #ff6b35;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Space Grotesk', sans-serif;
    font-size: 16px;
    line-height: 1.7;
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse at 20% 0%, rgba(0,100,200,0.08) 0%, transparent 60%),
      radial-gradient(ellipse at 80% 100%, rgba(0,200,255,0.05) 0%, transparent 60%);
  }}

  .container {{
    max-width: 860px;
    margin: 0 auto;
    padding: 0 24px 80px;
  }}

  /* ── HEADER ── */
  .site-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 32px 0 28px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 56px;
  }}

  .wordmark {{
    font-family: 'Space Mono', monospace;
    font-size: 22px;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }}

  .wordmark span {{
    color: var(--text-dim);
    font-weight: 400;
    font-size: 11px;
    display: block;
    letter-spacing: 0.3em;
    margin-top: 2px;
  }}

  .header-meta {{
    font-family: 'Space Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    text-align: right;
    letter-spacing: 0.08em;
  }}

  .header-meta .live {{
    color: var(--green);
    display: flex;
    align-items: center;
    gap: 6px;
    justify-content: flex-end;
    margin-bottom: 4px;
  }}

  .header-meta .live::before {{
    content: '';
    width: 6px; height: 6px;
    background: var(--green);
    border-radius: 50%;
    animation: pulse 2s infinite;
  }}

  @keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.3; }}
  }}

  /* ── HORIZON BADGE ── */
  .horizon-bar {{
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 32px;
  }}

  .horizon-badge {{
    font-family: 'Space Mono', monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: var(--bg);
    background: var(--accent);
    padding: 5px 12px;
    border-radius: 2px;
  }}

  .theme-label {{
    font-family: 'Space Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    letter-spacing: 0.15em;
    text-transform: uppercase;
  }}

  /* ── HEADLINE ── */
  .headline {{
    font-size: clamp(28px, 5vw, 46px);
    font-weight: 700;
    color: var(--text-bright);
    line-height: 1.15;
    margin-bottom: 18px;
    letter-spacing: -0.02em;
  }}

  .subhead {{
    font-size: 18px;
    font-weight: 400;
    color: var(--accent);
    line-height: 1.5;
    margin-bottom: 40px;
    padding-left: 16px;
    border-left: 2px solid var(--accent2);
  }}

  /* ── HERO IMAGE ── */
  .hero-img {{
    width: 100%;
    aspect-ratio: 16/9;
    object-fit: cover;
    display: block;
    border-radius: 4px;
    border: 1px solid var(--border);
    margin-bottom: 48px;
    filter: saturate(0.9) brightness(0.95);
  }}

  .hero-placeholder {{
    width: 100%;
    aspect-ratio: 16/9;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    margin-bottom: 48px;
  }}

  /* ── BODY ── */
  .body-text p {{
    margin-bottom: 24px;
    color: var(--text);
    font-size: 16px;
    line-height: 1.8;
  }}

  .body-text p:first-child::first-letter {{
    font-size: 3.2em;
    font-weight: 700;
    color: var(--accent);
    float: left;
    line-height: 0.8;
    margin: 4px 10px 0 0;
    font-family: 'Space Mono', monospace;
  }}

  /* ── TAGS ── */
  .tags {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 48px;
    padding-top: 32px;
    border-top: 1px solid var(--border);
  }}

  .tag {{
    font-family: 'Space Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--text-dim);
    border: 1px solid var(--border);
    padding: 4px 10px;
    border-radius: 2px;
  }}

  /* ── SIGNAL CARDS ── */
  .signals-section {{
    margin-top: 64px;
  }}

  .signals-label {{
    font-family: 'Space Mono', monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 12px;
  }}

  .signals-label::before, .signals-label::after {{
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }}

  .signals-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }}

  .signal-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 20px;
    transition: border-color 0.2s;
  }}

  .signal-card:hover {{
    border-color: var(--accent2);
  }}

  .signal-meta {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }}

  .signal-theme {{
    font-family: 'Space Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--accent);
  }}

  .signal-horizon {{
    font-family: 'Space Mono', monospace;
    font-size: 9px;
    color: var(--text-dim);
    background: var(--border);
    padding: 2px 7px;
    border-radius: 2px;
  }}

  .signal-headline {{
    font-size: 14px;
    font-weight: 600;
    color: var(--text-bright);
    line-height: 1.3;
    margin-bottom: 10px;
  }}

  .signal-summary {{
    font-size: 13px;
    color: var(--text-dim);
    line-height: 1.6;
  }}

  /* ── FOOTER ── */
  .site-footer {{
    margin-top: 64px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
    font-family: 'Space Mono', monospace;
    font-size: 10px;
    color: var(--text-dim);
    letter-spacing: 0.1em;
    display: flex;
    justify-content: space-between;
  }}

  /* ── SCANLINE OVERLAY ── */
  body::after {{
    content: '';
    position: fixed;
    inset: 0;
    pointer-events: none;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 3px,
      rgba(0,200,255,0.012) 3px,
      rgba(0,200,255,0.012) 4px
    );
    z-index: 9999;
  }}
</style>
</head>
<body>
<div class="container">

  <header class="site-header">
    <div class="wordmark">
      SIGNAL
      <span>Near-Future Intelligence Briefing</span>
    </div>
    <div class="header-meta">
      <div class="live">LIVE FORECAST</div>
      <div>{date_str}</div>
    </div>
  </header>

  <div class="horizon-bar">
    <div class="horizon-badge">Horizon: {forecast['horizon']}</div>
    <div class="theme-label">{forecast['theme']}</div>
  </div>

  <h1 class="headline">{forecast['headline']}</h1>
  <p class="subhead">{forecast['subhead']}</p>

  {img_html}

  <div class="body-text">
    {body_html}
  </div>

  <div class="tags">
    {tags_html}
  </div>

  <div class="signals-section">
    <div class="signals-label">More Signals</div>
    <div class="signals-grid">
      {signals_html}
    </div>
  </div>

  <footer class="site-footer">
    <span>signal.jonestech.xyz</span>
    <span>Generated {date_str} · AI-assisted analysis</span>
  </footer>

</div>
</body>
</html>"""


# ── ftp ────────────────────────────────────────────────────────────────────────
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

def ftp_upload(local_path: Path, archive_name: str = ""):
    if not FTP_HOST:
        logger.warning("No FTP config — skipping upload")
        return
    try:
        ftp = _ftp_connect(FTP_HOST, FTP_USER, FTP_PASS)
        base = FTP_PATH.rstrip("/")

        # Main file
        try:
            ftp.cwd(base)
        except ftplib.error_perm:
            _ftp_mkdirs(ftp, base)
        with open(local_path, "rb") as f:
            ftp.storbinary("STOR Signal.html", f)
        logger.info("Uploaded Signal.html")

        # Archive
        if archive_name:
            archive_dir = base + "/archive/signal"
            _ftp_mkdirs(ftp, archive_dir)
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {archive_name}", f)
            logger.info("Archived to /archive/signal/%s", archive_name)

        ftp.quit()
    except Exception as e:
        logger.error("FTP error: %s", e)


# ── main ───────────────────────────────────────────────────────────────────────
def main(dry_run: bool = False):
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%d %B %Y")
    day_of_year = now.timetuple().tm_yday

    logger.info("Generating forecast for day %d (%s)", day_of_year, date_str)

    data = get_forecasts(day_of_year)
    forecast = data["lead"]
    logger.info("Theme: %s | Horizon: %s", forecast["theme"], forecast["horizon"])
    logger.info("Headline: %s", forecast["headline"])
    logger.info("Supporting signals: %d", len(data.get("signals", [])))

    image_data = generate_image_b64(forecast.get("image_prompt", ""))

    html = build_html(data, image_data, date_str)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    logger.info("Written to %s", OUTPUT_PATH)

    if not dry_run:
        archive_name = now.strftime("Signal-%Y-%m-%d.html")
        ftp_upload(OUTPUT_PATH, archive_name=archive_name)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
