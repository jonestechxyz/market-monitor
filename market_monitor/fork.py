"""
THE FORK — reads today's AI and robotics news, then writes two dispatches from
five years ahead: one from the timeline where it goes right, one where it goes
wrong. Each gets an illustration; both are narrated to MP3.

Usage:
    python fork.py
    python fork.py --dry-run   # build locally, no FTP upload
"""

import argparse
import asyncio
import html
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import edge_tts

from madworld import _ftp_connect, _ftp_mkdirs, fetch_feed_url, fetch_rss, generate_image_b64, groq

logger = logging.getLogger(__name__)

OUT_DIR = Path(os.getenv("FORK_OUT", "/tmp/fork"))
YEARS_AHEAD = 5

QUERIES = [
    "humanoid robot OR Figure AI OR Tesla Optimus OR Boston Dynamics",
    "robotics factory automation OR warehouse robots",
    "AGI OR superintelligence OR frontier AI model",
    "AI safety OR AI regulation OR AI law",
    "AI jobs OR AI layoffs OR AI replacing workers",
    "AI military OR autonomous weapons OR AI surveillance",
    "AI medicine OR AI drug discovery OR AI science breakthrough",
    "AI energy OR data center power OR AI chips",
    "AI companion OR AI relationship OR AI loneliness",
    "self-driving OR robotaxi OR autonomous vehicles",
]
FALLBACK_FEEDS = [
    "https://www.technologyreview.com/feed/",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
]

BRIGHT_STYLE = ("hopeful solarpunk illustration, warm golden light, lush greenery on architecture, "
                "people and gentle robots side by side, painterly, Moebius-inspired, optimistic future")
DARK_STYLE = ("bleak dystopian illustration, cold sodium and neon light, rain, brutalist megastructures, "
              "surveillance drones, lonely figures, cinematic, Blade Runner-inspired, muted palette")
VOICE_BRIGHT = os.getenv("FORK_VOICE_BRIGHT", "en-GB-SoniaNeural")
VOICE_DARK = os.getenv("FORK_VOICE_DARK", "en-GB-RyanNeural")


def gather() -> list[dict]:
    items = []
    for q in QUERIES:
        items += fetch_rss(q, max_age_hours=36, limit=6)
    if len(items) < 15:
        for feed in FALLBACK_FEEDS:
            items += fetch_feed_url(feed, max_age_hours=48, limit=8)
    seen, unique = set(), []
    for it in items:
        k = it["title"].lower()[:60]
        if k not in seen:
            seen.add(k)
            unique.append(it)
    return unique[:50]


def forecast(items: list[dict], year: int) -> dict | None:
    numbered = "\n".join(f"{i+1}. {it['title']}" for i, it in enumerate(items))
    resp = groq.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": (
                "You are a sober futurist with a novelist's eye. You extrapolate from real, current "
                "signals; you never invent present-day facts. Your future dispatches are vivid, concrete "
                "and human-scale: a named person, a street, a smell, a price. Return ONLY valid JSON."
            )},
            {"role": "user", "content": (
                f"Today's AI and robotics headlines:\n{numbered}\n\n"
                f"1. Choose the 5 headlines that most shape the world of {year}. For each, give its number "
                f"and one sentence on why it matters.\n"
                f"2. Write THE BRIGHT FORK: a 220-280 word first-person dispatch from an ordinary person in "
                f"{year}, in the timeline where these trends went right.\n"
                f"3. Write THE DARK FORK: a 220-280 word first-person dispatch from an ordinary person in "
                f"{year}, in the timeline where they went wrong. Unsettling, plausible, not cartoonish.\n"
                f"4. Name THE HINGE: the single decision or event in the next few years that separates the two.\n"
                f"5. Give your honest odds (0-100) that we end up closer to the dark fork.\n\n"
                'Return JSON: {"signals":[{"n":number,"why":"..."}], '
                '"bright":{"title":"...","who":"name, job, city","dispatch":"paragraphs separated by \\n\\n",'
                '"image_prompt":"one sentence scene"}, '
                '"dark":{"title":"...","who":"...","dispatch":"...","image_prompt":"..."}, '
                '"hinge":"two sentences", "odds_dark": number}'
            )},
        ],
        temperature=0.85,
        max_tokens=4000,
    )
    content = resp.choices[0].message.content or ""
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        logger.error("No JSON in Groq response: %s", content[:300])
        return None
    data = json.loads(m.group(0))
    if not (data.get("bright", {}).get("dispatch") and data.get("dark", {}).get("dispatch")):
        return None
    for s in data.get("signals", []):
        idx = int(s.get("n", 0)) - 1
        if 0 <= idx < len(items):
            s["headline"], s["link"] = items[idx]["title"], items[idx]["link"]
    data["signals"] = [s for s in data.get("signals", []) if s.get("headline")]
    return data


async def _tts_all(parts: list[tuple[str, str]], path: Path):
    with open(path, "wb") as out:
        for text, voice in parts:
            async for chunk in edge_tts.Communicate(text, voice, rate="-4%").stream():
                if chunk["type"] == "audio":
                    out.write(chunk["data"])


def make_audio(d: dict, year: int, path: Path) -> bool:
    parts = [
        (f"The Fork. Two dispatches from {year}. First, the bright fork. {d['bright']['title']}.", VOICE_BRIGHT),
        (d["bright"]["dispatch"], VOICE_BRIGHT),
        (f"And now, the dark fork. {d['dark']['title']}.", VOICE_DARK),
        (d["dark"]["dispatch"], VOICE_DARK),
        (f"The hinge. {d.get('hinge', '')}", VOICE_DARK),
    ]
    try:
        asyncio.run(_tts_all(parts, path))
        return path.stat().st_size > 1000
    except Exception as e:
        logger.error("TTS failed: %s", e)
        return False


def build_html(d: dict, year: int, date_str: str, imgs: dict, audio: str | None) -> str:
    e = html.escape

    def paras(t):
        return "".join(f"<p>{e(p.strip())}</p>" for p in t.split("\n\n") if p.strip())

    def side(key, label):
        s = d[key]
        img = f'<img src="{imgs[key]}" alt="">' if imgs.get(key) else ""
        return (f'<article class="{key}"><div class="label">{label} · {year}</div>{img}'
                f'<h2>{e(s["title"])}</h2><div class="who">{e(s.get("who", ""))}</div>{paras(s["dispatch"])}</article>')

    signals = "".join(
        f'<li><a href="{e(s["link"])}" rel="noopener" target="_blank">{e(s["headline"])}</a>'
        f'<span>{e(s.get("why", ""))}</span></li>' for s in d["signals"])
    odds = max(0, min(100, int(d.get("odds_dark", 50))))
    player = (f'<div class="listen"><span>▶ Listen to both futures</span>'
              f'<audio controls preload="none" src="{audio}"></audio></div>') if audio else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>THE FORK — {year}, as of {e(date_str)}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Newsreader:ital,wght@0,400;1,400&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:#0b0c0e; --ink:#e6e4df; --dim:#8b8a86; --rule:#26272b;
          --bright:#f2b544; --dark:#5ad1e6; --danger:#e5484d; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font:18px/1.65 'Newsreader', Georgia, serif; }}
  main {{ max-width:1180px; margin:0 auto; padding:40px 16px 80px; }}
  header {{ text-align:center; margin-bottom:30px; }}
  h1 {{ font:700 clamp(48px,10vw,96px)/0.9 'Space Grotesk', sans-serif; margin:0; letter-spacing:-.04em; }}
  h1 span {{ color:var(--danger); }}
  .tag {{ font:600 13px 'Space Grotesk', sans-serif; letter-spacing:.2em; text-transform:uppercase; color:var(--dim); margin-top:10px; }}
  .sans {{ font-family:'Space Grotesk', sans-serif; }}
  .signals {{ border:1px solid var(--rule); padding:18px 20px; margin:0 0 28px; }}
  .signals h3, .hinge h3 {{ font:600 12px 'Space Grotesk', sans-serif; letter-spacing:.2em; text-transform:uppercase; color:var(--dim); margin:0 0 10px; }}
  .signals ol {{ margin:0; padding-left:20px; }}
  .signals li {{ margin:6px 0; font-size:16px; }}
  .signals a {{ color:var(--ink); }}
  .signals span {{ display:block; color:var(--dim); font-style:italic; font-size:15px; }}
  .listen {{ display:flex; gap:14px; align-items:center; flex-wrap:wrap; margin:0 0 28px; }}
  .listen span {{ font:600 14px 'Space Grotesk', sans-serif; }}
  .listen audio {{ flex:1; min-width:240px; }}
  .forks {{ display:grid; grid-template-columns:1fr 1fr; gap:28px; }}
  article {{ border-top:4px solid; padding-top:14px; min-width:0; }}
  article.bright {{ border-color:var(--bright); }}
  article.dark {{ border-color:var(--dark); }}
  article img {{ width:100%; display:block; margin:10px 0 16px; aspect-ratio:16/10; object-fit:cover; }}
  .label {{ font:700 13px 'Space Grotesk', sans-serif; letter-spacing:.2em; text-transform:uppercase; }}
  .bright .label {{ color:var(--bright); }}
  .dark .label {{ color:var(--dark); }}
  h2 {{ font:600 26px/1.2 'Space Grotesk', sans-serif; margin:0 0 4px; }}
  .who {{ color:var(--dim); font-style:italic; margin-bottom:14px; }}
  p {{ margin:0 0 1em; }}
  .hinge {{ margin:40px 0 0; border:1px solid var(--rule); padding:22px; text-align:center; }}
  .hinge p {{ font-size:21px; max-width:760px; margin:0 auto 18px; }}
  .meter {{ height:10px; background:linear-gradient(90deg,var(--bright),var(--dark)); position:relative; max-width:520px; margin:0 auto; border-radius:5px; }}
  .needle {{ position:absolute; top:-6px; width:3px; height:22px; background:var(--ink); left:{odds}%; }}
  .odds {{ font:600 14px 'Space Grotesk', sans-serif; color:var(--dim); margin-top:12px; }}
  footer {{ margin-top:40px; text-align:center; color:var(--dim); font:13px 'Space Grotesk', sans-serif; }}
  footer a {{ color:var(--ink); }}
  @media (max-width:760px) {{ .forks {{ grid-template-columns:1fr; gap:40px; }} }}
</style>
</head>
<body>
<main>
  <header>
    <h1>THE F<span>O</span>RK</h1>
    <div class="tag">Two dispatches from {year} · written {e(date_str)}</div>
  </header>
  <section class="signals"><h3>Today's signals</h3><ol>{signals}</ol></section>
  {player}
  <div class="forks">
    {side("bright", "The bright fork")}
    {side("dark", "The dark fork")}
  </div>
  <section class="hinge">
    <h3>The hinge</h3>
    <p>{e(d.get("hinge", ""))}</p>
    <div class="meter"><div class="needle"></div></div>
    <div class="odds">Today's odds of the dark fork: {odds}%</div>
  </section>
  <footer>Speculative fiction extrapolated by machine from real headlines · the people are invented ·
    <a href="/archive/fork/index.php">Archive</a></footer>
</main>
</body>
</html>"""


def upload(live: dict[str, Path], archive: dict[str, Path]):
    host, user, pwd = os.getenv("FTP_HOST"), os.getenv("FTP_USER"), os.getenv("FTP_PASS")
    base = os.getenv("FTP_PATH", "/public_html/").rstrip("/")
    if not all([host, user, pwd]):
        logger.warning("FTP credentials not set — skipping upload")
        return
    ftp = _ftp_connect(host, user, pwd)
    ftp.cwd(base)
    for remote, local in live.items():
        with open(local, "rb") as f:
            ftp.storbinary(f"STOR {remote}", f)
        logger.info("Uploaded https://jonestech.xyz/%s", remote)
    _ftp_mkdirs(ftp, base + "/archive/fork")
    for remote, local in archive.items():
        with open(local, "rb") as f:
            ftp.storbinary(f"STOR {remote}", f)
        logger.info("Archived https://jonestech.xyz/archive/fork/%s", remote)
    ftp.quit()


def main(dry_run: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    year, stamp, date_str = now.year + YEARS_AHEAD, now.strftime("%Y-%m-%d"), now.strftime("%A %-d %B %Y")

    items = gather()
    logger.info("Got %d AI/robotics headlines", len(items))
    if len(items) < 5:
        logger.error("Too few headlines — aborting, live page untouched")
        return

    d = None
    for attempt in range(3):
        try:
            d = forecast(items, year)
        except Exception as e:
            logger.error("Groq attempt %d failed: %s", attempt + 1, e)
        if d:
            break
        time.sleep(5)
    if not d:
        logger.error("No forecast — aborting, live page untouched")
        return
    logger.info("Bright: %s | Dark: %s | odds %s", d["bright"]["title"], d["dark"]["title"], d.get("odds_dark"))

    imgs = {
        "bright": generate_image_b64(d["bright"].get("image_prompt", ""), style=BRIGHT_STYLE),
        "dark": generate_image_b64(d["dark"].get("image_prompt", ""), style=DARK_STYLE),
    }

    mp3 = OUT_DIR / f"Fork-{stamp}.mp3"
    has_audio = make_audio(d, year, mp3)
    logger.info("Audio: %s", "ok" if has_audio else "skipped")

    live = OUT_DIR / "Fork.html"
    live.write_text(build_html(d, year, date_str, imgs, "Fork.mp3" if has_audio else None), encoding="utf-8")
    dated = OUT_DIR / f"Fork-{stamp}.html"
    dated.write_text(build_html(d, year, date_str, imgs, mp3.name if has_audio else None), encoding="utf-8")
    logger.info("Saved %s", live)

    if dry_run:
        logger.info("Dry run — skipping upload")
        return

    live_files = {"Fork.html": live}
    archive = {dated.name: dated, "index.php": Path(__file__).parent / "fork_archive.php"}
    if has_audio:
        live_files["Fork.mp3"] = mp3
        archive[mp3.name] = mp3
    upload(live_files, archive)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    main(ap.parse_args().dry_run)
