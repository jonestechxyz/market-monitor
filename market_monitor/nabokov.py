"""
The Daily Nabokov — one headline a day, rendered as a short prose piece in
the manner of Nabokov, with a specimen-plate illustration and a narrated MP3.

Usage:
    python nabokov.py
    python nabokov.py --dry-run   # build HTML + MP3 locally, no FTP upload
"""

import argparse
import asyncio
import html
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import edge_tts

from madworld import (
    FALLBACK_FEEDS, NEWS_QUERIES, _ftp_connect, _ftp_mkdirs,
    fetch_feed_url, fetch_rss, generate_image_b64, groq,
)

logger = logging.getLogger(__name__)

OUT_DIR = Path(os.getenv("NABOKOV_OUT", "/tmp/nabokov"))
VOICE = os.getenv("NABOKOV_VOICE", "en-GB-RyanNeural")

PLATE_STYLE = (
    "antique natural history specimen plate, hand-coloured copperplate engraving, "
    "pinned butterflies and moths with tiny handwritten latin labels, sepia paper, "
    "fine cross-hatching, museum cabinet, 1940s entomology illustration, no modern text"
)


def gather_headlines() -> list[str]:
    heads = []
    for q in NEWS_QUERIES:
        heads += [i["title"] for i in fetch_rss(q, limit=6)]
    if len(heads) < 10:
        for feed in FALLBACK_FEEDS:
            heads += [i["title"] for i in fetch_feed_url(feed, limit=6)]
    seen, unique = set(), []
    for h in heads:
        k = h.lower()[:60]
        if k not in seen:
            seen.add(k)
            unique.append(h)
    return unique


def write_piece(headlines: list[str]) -> dict | None:
    numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines[:40]))
    resp = groq.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": (
                "You write original pastiche in the manner of Vladimir Nabokov: luminous, exact, "
                "playful prose; synaesthetic colour; parenthetical asides; puns and alliteration; "
                "an unreliable, faintly vain narrator; memory and time folding into the present; "
                "a butterfly or two. Never quote Nabokov's actual sentences. "
                "Return ONLY valid JSON, no markdown."
            )},
            {"role": "user", "content": (
                "Pick the ONE headline below with the most human strangeness in it. Write a prose "
                "piece of 300-380 words about it, as if Nabokov had glimpsed it in a morning paper "
                "in some hotel and could not let it go. It should be readable aloud.\n\n"
                f"Headlines:\n{numbered}\n\n"
                'Return JSON: {"headline": the original headline, "title": an elegant title, '
                '"piece": the prose with paragraphs separated by \\n\\n, '
                '"specimen": a fictional latin butterfly name inspired by the story, '
                '"image_prompt": one sentence describing a specimen plate that alludes to the story}'
            )},
        ],
        temperature=0.9,
        max_tokens=2400,
    )
    content = resp.choices[0].message.content or ""
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        logger.error("No JSON in Groq response: %s", content[:300])
        return None
    data = json.loads(m.group(0))
    if not data.get("piece"):
        return None
    return data


async def _tts(text: str, path: Path):
    await edge_tts.Communicate(text, VOICE, rate="-6%").save(str(path))


def make_audio(piece: dict, path: Path) -> bool:
    spoken = f"{piece['title']}.\n\n{piece['piece']}"
    try:
        asyncio.run(_tts(spoken, path))
        return path.exists() and path.stat().st_size > 1000
    except Exception as e:
        logger.error("TTS failed: %s", e)
        return False


def build_html(p: dict, date_str: str, image: str, audio_name: str | None) -> str:
    e = html.escape
    paras = "".join(f"<p>{e(x.strip())}</p>" for x in p["piece"].split("\n\n") if x.strip())
    img = f'<img class="plate" src="{image}" alt="{e(p["specimen"])}">' if image else ""
    audio = (f'<div class="listen"><span>Listen</span>'
             f'<audio controls preload="none" src="{audio_name}"></audio></div>') if audio_name else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Daily Nabokov — {e(date_str)}</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=IM+Fell+English+SC&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:#f4ecdc; --ink:#2b2118; --dim:#7a6a55; --rule:#c9b48f; --accent:#6b2d2d; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#16120d; --ink:#e8dcc4; --dim:#9c8b70; --rule:#4a3d2a; --accent:#c98f6a; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font:21px/1.7 'Cormorant Garamond', Georgia, serif; }}
  main {{ max-width:680px; margin:0 auto; padding:48px 20px 80px; }}
  .mast {{ text-align:center; border-bottom:1px solid var(--rule); padding-bottom:22px; margin-bottom:34px; }}
  .mast h1 {{ font:400 40px/1.1 'IM Fell English SC', serif; margin:0; letter-spacing:.04em; }}
  .mast .date {{ color:var(--dim); font-style:italic; margin-top:6px; font-size:17px; }}
  .plate {{ width:100%; display:block; border:1px solid var(--rule); margin-bottom:8px; filter:sepia(.25); }}
  .specimen {{ text-align:center; font-style:italic; color:var(--dim); font-size:16px; margin-bottom:34px; }}
  h2 {{ font-weight:600; font-size:32px; line-height:1.2; margin:0 0 6px; }}
  .source {{ color:var(--dim); font-size:15px; margin-bottom:26px; }}
  .source b {{ font-weight:600; }}
  .listen {{ display:flex; align-items:center; gap:14px; margin:0 0 30px; padding:12px 0;
            border-top:1px solid var(--rule); border-bottom:1px solid var(--rule); }}
  .listen span {{ font-family:'IM Fell English SC', serif; color:var(--accent); }}
  .listen audio {{ flex:1; min-width:0; height:36px; }}
  p {{ margin:0 0 1.1em; text-align:justify; hyphens:auto; }}
  p:first-of-type::first-letter {{ float:left; font:400 64px/0.85 'IM Fell English SC', serif;
            padding:6px 8px 0 0; color:var(--accent); }}
  footer {{ margin-top:50px; padding-top:18px; border-top:1px solid var(--rule);
           text-align:center; color:var(--dim); font-size:15px; }}
  footer a {{ color:var(--accent); }}
</style>
</head>
<body>
<main>
  <div class="mast">
    <h1>The Daily Nabokov</h1>
    <div class="date">{e(date_str)}</div>
  </div>
  {img}
  <div class="specimen">{e(p["specimen"])}</div>
  <h2>{e(p["title"])}</h2>
  <div class="source">after the headline: <b>{e(p["headline"])}</b></div>
  {audio}
  {paras}
  <footer>
    A pastiche, written by machine in admiration of V.N. · not his words ·
    <a href="/archive/nabokov/index.php">Archive</a>
  </footer>
</main>
</body>
</html>"""


def upload(files: dict[str, Path], archive_files: dict[str, Path]):
    host, user, pwd = os.getenv("FTP_HOST"), os.getenv("FTP_USER"), os.getenv("FTP_PASS")
    base = os.getenv("FTP_PATH", "/public_html/").rstrip("/")
    if not all([host, user, pwd]):
        logger.warning("FTP credentials not set — skipping upload")
        return
    ftp = _ftp_connect(host, user, pwd)
    ftp.cwd(base)
    for remote, local in files.items():
        with open(local, "rb") as f:
            ftp.storbinary(f"STOR {remote}", f)
        logger.info("Uploaded https://jonestech.xyz/%s", remote)
    _ftp_mkdirs(ftp, base + "/archive/nabokov")
    for remote, local in archive_files.items():
        with open(local, "rb") as f:
            ftp.storbinary(f"STOR {remote}", f)
        logger.info("Archived https://jonestech.xyz/archive/nabokov/%s", remote)
    ftp.quit()


def main(dry_run: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    date_str = now.strftime("%A %-d %B %Y")
    stamp = now.strftime("%Y-%m-%d")

    heads = gather_headlines()
    logger.info("Got %d headlines", len(heads))
    if not heads:
        logger.error("No headlines — aborting, live page untouched")
        return

    piece = None
    for attempt in range(3):
        try:
            piece = write_piece(heads)
        except Exception as e:
            logger.error("Groq attempt %d failed: %s", attempt + 1, e)
        if piece:
            break
        time.sleep(5)
    if not piece:
        logger.error("No piece written — aborting, live page untouched")
        return
    logger.info("Piece: %s", piece["title"])

    image = generate_image_b64(f"{PLATE_STYLE}, {piece.get('image_prompt', '')}")

    mp3 = OUT_DIR / f"Nabokov-{stamp}.mp3"
    has_audio = make_audio(piece, mp3)
    logger.info("Audio: %s", "ok" if has_audio else "skipped")

    # Live page lives at site root; archive copies live one level down, so audio paths differ.
    live = OUT_DIR / "Nabokov.html"
    live.write_text(build_html(piece, date_str, image, "Nabokov.mp3" if has_audio else None), encoding="utf-8")
    dated = OUT_DIR / f"Nabokov-{stamp}.html"
    dated.write_text(build_html(piece, date_str, image, mp3.name if has_audio else None), encoding="utf-8")
    logger.info("Saved %s", live)

    if dry_run:
        logger.info("Dry run — skipping upload")
        return

    files = {"Nabokov.html": live}
    archive = {dated.name: dated, "index.php": Path(__file__).parent / "nabokov_archive.php"}
    if has_audio:
        files["Nabokov.mp3"] = mp3
        archive[mp3.name] = mp3
    upload(files, archive)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    main(ap.parse_args().dry_run)
