"""
A Use a Day — one repetitive paperwork job on a building project, and a practical
way to make the computer do it. Written for people who know construction, not software.

Usage:
    python use.py
    python use.py --dry-run                       # build locally, no FTP upload
    python use.py --featured use_featured/x.json  # publish a hand-written edition instead of a generated one
"""

import argparse
import html
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

from madworld import _ftp_connect, _ftp_mkdirs, generate_image_b64, groq

logger = logging.getLogger(__name__)

OUT_DIR = Path(os.getenv("USE_OUT", "/tmp/use"))
ARCHIVE = "https://jonestech.xyz/archive/use/"

JOBS = ["certificates, declarations and other one-per-asset documents", "drawing and document registers",
        "transmittals and document issue sheets", "snag and defect lists", "site photos and photo reports",
        "handover packs and operation and maintenance manuals", "subcontractor quotes and tender comparisons",
        "invoices, payment applications and purchase orders", "timesheets, labour returns and plant hire records",
        "meeting minutes and action tracking", "requests for information and technical queries",
        "inspection and test records", "delivery notes and material tracking", "programme and progress reporting",
        "specifications, schedules and comparing document versions", "emails, filing and naming files consistently"]

# The menu of ways to automate. Each morning several are brainstormed side by side and the most surprising wins;
# anything used in the past week is off the table, so the column cannot settle into one trick.
TECHNIQUES = {
    "photo-reading": "the phone camera plus an AI on your own computer reading what is in photos: labels, nameplates, "
                     "delivery notes, handwritten forms, gauges",
    "photo-metadata": "the date, time and GPS position hidden inside every phone photo",
    "qr-codes": "QR codes printed and stuck up on site, each opening the right document or form for that spot",
    "public-data": "free public records joined to your own: official weather history, public holidays, daylight hours",
    "self-checking-sheets": "spreadsheet rules that flag problems by themselves: colour warnings, cross-checks between "
                            "sheets, totals that must agree",
    "combine-many-files": "Excel pulling dozens of separate files from a folder into one table, refreshed with one click",
    "compare-versions": "comparing two versions of a document or spreadsheet and showing only what changed",
    "local-ai-reading": "an AI running on your own computer reading long documents and pulling out specific items, "
                        "quoting the page",
    "voice-to-records": "speaking notes into the phone and having them turned into structured, dated records",
    "phone-shortcuts": "a one-tap shortcut on the phone that does several steps at once, such as photo, time, place "
                       "and note saved together",
    "calendar-reminders": "turning dates buried in documents into calendar reminders that warn you in advance",
    "maps-and-plans": "placing things on a site plan or map automatically (snags, deliveries, photos) so patterns show",
    "pdf-tools": "free tools that split, merge, stamp, number or pull pages out of PDFs in bulk",
    "email-rules": "email rules and saved replies that sort, file and answer routine mail by themselves",
    "model-quantities": "pulling quantities and schedules straight out of the 3D building model with a free viewer",
}
OVERDONE = ("filling a Word or Excel template once per row of a list (mail merge)",
            "renaming, sorting or filing files using a lookup list")

LISTS = ("how", "need", "watch_out")
REQUIRED = ("title", "why", "idea", "before", "after", "person", "explain", "effort") + LISTS

ART_STYLE = ("vintage construction-manual illustration, two-colour risograph print in teal and orange on cream paper, "
             "clean isometric line drawing, no text, no letters")


def past_editions(today: str) -> list[dict]:
    """Earlier editions, oldest first, as {title, idea, technique}. Today's own file is left out so a re-run
    replaces it and keeps its number. Only the last ten pages are opened to read their idea and technique."""
    try:
        page = requests.get(ARCHIVE + "index.php", timeout=20).content.decode("utf-8")
        rows = [(f, html.unescape(t)) for f, t in reversed(re.findall(r'href="(Use-[\d-]+\.html)".*?class="t">(.*?)</div>', page, re.S))
                if today not in f]
    except Exception as e:
        logger.warning("Could not read archive (%s) — assuming no past editions", e)
        return []
    out = []
    for i, (f, title) in enumerate(rows):
        d = {"title": title, "idea": "", "technique": ""}
        if i >= len(rows) - 10:
            try:
                s = requests.get(ARCHIVE + f, timeout=20).content.decode("utf-8")
                m = re.search(r'<meta name="use-technique" content="([^"]*)"', s)
                d["technique"] = m.group(1) if m else ""
                m = re.search(r"The idea</h3>\s*<p>(.*?)</p>", s, re.S)
                d["idea"] = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""
            except Exception:
                pass
        out.append(d)
    return out


def chat_json(system: str, user: str, max_tokens: int, temperature: float) -> dict | None:
    resp = groq.chat.completions.create(model="openai/gpt-oss-120b", temperature=temperature, max_tokens=max_tokens,
                                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    content = resp.choices[0].message.content or ""
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        logger.error("No JSON in Groq response: %s", content[:300])
        return None
    return json.loads(m.group(0))


def pick_idea(job: str, past: list[dict], second_try: bool = False) -> dict | None:
    """Brainstorm several ideas, each with a different technique, and judge them. Returns the winner."""
    recent = {p["technique"] for p in past[-7:] if p["technique"]}
    allowed = {k: v for k, v in TECHNIQUES.items() if k not in recent}
    menu = "\n".join(f"- {k}: {v}" for k, v in allowed.items())
    history = "\n".join(f"- {p['title']}" + (f" ({p['idea'][:160]})" if p["idea"] else "") for p in past[-40:]) or "(none yet)"
    d = chat_json(
        "You are the sharpest operations person in a European construction company: you know site paperwork inside out "
        "and you know what ordinary computers and phones can quietly do. You hunt for automations that make experienced "
        "site managers say 'I had no idea you could do that'. Return ONLY valid JSON.",
        f"Area of paperwork today: {job}.\n\n"
        f"Ideas already published (do not repeat their job OR their method):\n{history}\n\n"
        f"These methods are overdone and are BANNED: {'; '.join(OVERDONE)}.\n\n"
        f"Techniques you may use today:\n{menu}\n\n"
        "Step 1: brainstorm 8 different ideas in today's area. Each must use a DIFFERENT technique from the list. Each must "
        "solve a real, specific, recurring pain on European building projects, using free or common tools and nothing "
        "that sends project documents to an online service.\n"
        "Step 2: judge them hard. Score each 1-10 for SURPRISE (would a typical site manager already know this trick?) "
        "and 1-10 for PAYOFF (hours or money saved, disputes won, mistakes caught). Be strict: a mail merge or a "
        "spreadsheet lookup scores 2 for surprise.\n"
        "Step 3: choose the idea with the best combined score that is honestly doable by a non-technical person with "
        "at most one small program someone sets up once.\n\n"
        'Return JSON: {"ideas":[{"title":"...","technique":"<one of the technique keys>","pitch":"one sentence",'
        '"surprise":n,"payoff":n}], "choice": <index of the chosen idea>, "why_chosen": "one sentence"}',
        1800, 1.0 if second_try else 0.95)
    if not d or not d.get("ideas"):
        return None
    ideas = d["ideas"]
    for i, x in enumerate(ideas):
        logger.info("  idea %d [%s] s%s p%s: %s", i, x.get("technique"), x.get("surprise"), x.get("payoff"), x.get("title"))
    if max((x.get("surprise") or 0) for x in ideas) < 7 and not second_try:
        logger.info("No idea scored 7+ for surprise: brainstorming again")
        return pick_idea(job, past, second_try=True)
    try:
        best = ideas[int(d.get("choice", 0))]
    except (ValueError, IndexError):
        best = max(ideas, key=lambda x: (x.get("surprise") or 0) + (x.get("payoff") or 0))
    if best.get("technique") not in allowed:
        logger.warning("Chosen idea used a technique outside today's menu (%s)", best.get("technique"))
    logger.info("Chosen: %s — %s", best.get("title"), d.get("why_chosen", ""))
    return best


def normalise(d: dict) -> dict | None:
    """Tidy the writer's JSON: real line breaks, lists as lists. Returns None if anything required is missing."""
    for k in ("before", "after"):
        if isinstance(d.get(k), list):  # sometimes arrives as a list of lines
            d[k] = "\n".join(str(x) for x in d[k])
        if isinstance(d.get(k), str):
            d[k] = d[k].replace("\\n", "\n").strip()
    for k in ("title", "why", "idea", "person", "explain", "effort"):
        if d.get(k) is not None and not isinstance(d[k], str):
            d[k] = " ".join(str(x) for x in d[k]) if isinstance(d[k], list) else str(d[k])
    for k in LISTS:
        v = d.get(k) or []
        if isinstance(v, str):
            v = re.split(r"\n+|(?<=[.!?])\s+(?=\d+[.)]\s)", v.replace("\\n", "\n"))
            if len(v) == 1:  # unnumbered run of sentences
                v = re.split(r"(?<=[.!?])\s+(?=[A-Z])", v[0])
        d[k] = [re.sub(r"^\s*(\d+[.)]|[-•*])\s*", "", str(s)).strip() for s in v if str(s).strip()]
    missing = [k for k in REQUIRED if not d.get(k)]
    if missing:
        logger.error("Edition failed validation, missing: %s", ", ".join(missing))
        return None
    return d


def write_use(job: str, chosen: dict) -> dict | None:
    technique = TECHNIQUES.get(chosen.get("technique", ""), chosen.get("technique", ""))
    d = chat_json(
        "You write a daily column for people who work in construction in Europe: site managers, small contractors, "
        "document controllers, estimators and project engineers. They know building thoroughly and are NOT comfortable "
        "with technology. Write like a sharp colleague explaining over coffee: short sentences, plain words, proper "
        "construction terms. Never use these words: prompt, model, LLM, parameters, tokens, output, input, generate, "
        "API, script, code, database, workflow, leverage. Say 'a small program' if one is needed, and 'the AI' for an "
        "AI assistant. European setting: euros, metric units, dates as day-month-year. Do not name or quote any law, "
        "regulation or contract clause number. Project documents are confidential, so nothing may send them to an "
        "online service. Only describe features you are sure exist in free or common tools; where a step needs a small "
        "program someone sets up once, say so plainly. Be honest about limits. Return ONLY valid JSON.",
        f"Today's date: {datetime.now():%d-%m-%Y}. Area of paperwork: {job}.\n"
        f"Today's idea, already chosen: {chosen.get('title')}. {chosen.get('pitch', '')}\n"
        f"The technique it uses: {technique}.\n\n"
        "Write this idea up as today's column. Make the surprising part obvious: the reader should finish thinking "
        "'I had no idea you could do that'.\n\n"
        "Return JSON with keys:\n"
        '"title": under 12 words, naming the job and the payoff, starting with a verb\n'
        '"why": two short sentences on the job as it is done by hand today and what it costs\n'
        '"idea": two or three short sentences giving the idea in plain words, so a director would get it\n'
        '"how": a list of exactly 4 short steps describing how it works, from what you start with to the result. '
        'Describe what happens, not which buttons to press\n'
        '"need": a list of 2 to 4 things you need to have ready\n'
        '"before": a tiny made-up example of what goes in: 3 or 4 short lines, invented European names\n'
        '"after": what comes out for that example: 3 or 4 short lines. The example must be consistent: dates, totals and statuses must agree with each other and with today\'s date\n'
        '"person": one or two sentences on what a person must still check or decide\n'
        '"watch_out": a list of 2 or 3 specific ways this goes wrong in practice\n'
        '"explain": one sentence the reader could say to their boss or client to explain the idea\n'
        '"effort": exactly one of "an afternoon", "a day or two", "a proper project"\n'
        '"image_prompt": one sentence describing a simple site or site-office scene that illustrates the idea',
        2800, 0.7)
    if not d:
        return None
    d["technique"] = chosen.get("technique", "")
    return normalise(d)


def build_html(d: dict, number: int, date_str: str, image: str) -> str:
    e = html.escape
    li = lambda items: "".join(f"<li>{e(s)}</li>" for s in items)
    img = f'<img class="art" src="{e(image)}" alt="">' if image else ""
    try_it = (f'<p><a class="try" href="{e(d["try_url"])}">{e(d.get("try_label", "Try it"))}</a></p>'
              if d.get("try_url") else "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="use-technique" content="{e(d.get("technique", ""))}">
<title>{e(d["title"])} — A Use a Day No. {number}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Source+Serif+4:ital,wght@0,400;0,600;1,400&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:#f6f1e4; --ink:#1e2a2a; --dim:#667370; --rule:#d4cbb4; --teal:#12706a; --orange:#d9622b; --box:#fffaf0; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#101615; --ink:#e7e3d6; --dim:#93a09c; --rule:#2b3634; --teal:#4cc2b8; --orange:#f08a52; --box:#18201f; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font:18px/1.6 'Source Serif 4', Georgia, serif; }}
  main {{ max-width:700px; margin:0 auto; padding:32px 18px 70px; }}
  .mast {{ display:flex; justify-content:space-between; align-items:baseline; gap:12px; border-bottom:3px solid var(--teal);
          padding-bottom:8px; font-family:'Space Grotesk', sans-serif; }}
  .mast b {{ font-size:15px; letter-spacing:.16em; text-transform:uppercase; color:var(--teal); }}
  .mast span, .meta {{ font-size:14px; color:var(--dim); }}
  .no {{ font:700 13px 'Space Grotesk', sans-serif; letter-spacing:.14em; color:var(--orange); text-transform:uppercase; margin:26px 0 4px; }}
  h1 {{ font:700 clamp(30px,7vw,44px)/1.08 'Space Grotesk', sans-serif; margin:0 0 14px; letter-spacing:-.02em; }}
  .why {{ font-size:20px; margin:0 0 22px; }}
  .art {{ width:100%; display:block; border:1px solid var(--rule); margin:0 0 6px; }}
  h3 {{ font:700 13px 'Space Grotesk', sans-serif; letter-spacing:.14em; text-transform:uppercase; color:var(--teal); margin:30px 0 8px; }}
  p {{ margin:0 0 10px; }}
  ol, ul {{ margin:0; padding-left:22px; }} li {{ margin:6px 0; }}
  .pair {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
  .box {{ background:var(--box); border:1px solid var(--rule); border-top:4px solid var(--teal); padding:10px 12px;
         font:13.5px/1.5 'JetBrains Mono', ui-monospace, monospace; white-space:pre-wrap; overflow-wrap:anywhere; min-width:0; }}
  .box.out {{ border-top-color:var(--orange); }}
  .box b {{ display:block; font:700 11px 'Space Grotesk', sans-serif; letter-spacing:.12em; text-transform:uppercase; color:var(--dim); margin-bottom:6px; }}
  .warn {{ border:1px solid var(--orange); padding:4px 16px 10px; }} .warn h3 {{ color:var(--orange); margin-top:14px; }}
  .say {{ border-left:4px solid var(--teal); padding:4px 0 4px 16px; font-size:21px; font-style:italic; }}
  .effort {{ display:inline-block; font:700 13px 'Space Grotesk', sans-serif; letter-spacing:.08em; text-transform:uppercase;
            border:1px solid var(--teal); color:var(--teal); border-radius:14px; padding:3px 12px; }}
  .try {{ display:inline-block; background:var(--teal); color:var(--bg); text-decoration:none; border-radius:4px; padding:12px 20px;
         font:700 15px 'Space Grotesk', sans-serif; letter-spacing:.04em; }}
  footer {{ margin-top:44px; padding-top:14px; border-top:1px solid var(--rule); color:var(--dim); font-size:14px; }}
  footer a {{ color:var(--teal); }}
  @media (max-width:520px) {{ .pair {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<main>
  <div class="mast"><b>A Use a Day</b><span>{e(date_str)}</span></div>
  <p class="meta" style="margin:8px 0 0">One repetitive job on a building project, and how to make the computer do it.</p>
  <div class="no">No. {number} · {e(d.get("category", ""))}</div>
  <h1>{e(d["title"])}</h1>
  <p class="why">{e(d["why"])}</p>
  {img}
  <section>
    <h3>The idea</h3>
    <p>{e(d["idea"])}</p>
    {try_it}
  </section>
  <section>
    <h3>How it works</h3>
    <ol>{li(d["how"])}</ol>
  </section>
  <section>
    <h3>A small example</h3>
    <div class="pair">
      <div class="box"><b>What goes in</b>{e(d["before"])}</div>
      <div class="box out"><b>What comes out</b>{e(d["after"])}</div>
    </div>
    <p class="meta" style="margin-top:6px">Made up, to show the shape of it.</p>
  </section>
  <section>
    <h3>What you need</h3>
    <ul>{li(d["need"])}</ul>
    <p style="margin-top:10px"><span class="effort">Effort to set up: {e(d["effort"])}</span></p>
  </section>
  <section>
    <h3>What a person still does</h3>
    <p>{e(d["person"])}</p>
  </section>
  <section class="warn">
    <h3>Watch out</h3>
    <ul>{li(d["watch_out"])}</ul>
  </section>
  <section>
    <h3>How to explain it</h3>
    <p class="say">{e(d["explain"])}</p>
  </section>
  <footer>{e(d.get("credit", "An idea written by an AI. It has not been built or tested, so treat it as a starting point."))}
    Project documents stay on your own computer. <a href="/archive/use/index.php">See them all</a></footer>
</main>
<script src="/use-chat.js?v=2" defer></script>
</body>
</html>"""


def upload(live: Path, dated: Path):
    host, user, pwd = os.getenv("FTP_HOST"), os.getenv("FTP_USER"), os.getenv("FTP_PASS")
    base = os.getenv("FTP_PATH", "/public_html/").rstrip("/")
    if not all([host, user, pwd]):
        logger.warning("FTP credentials not set — skipping upload")
        return
    ftp = _ftp_connect(host, user, pwd)
    ftp.cwd(base)
    with open(live, "rb") as f:
        ftp.storbinary("STOR Use.html", f)
    logger.info("Uploaded https://jonestech.xyz/Use.html")
    _ftp_mkdirs(ftp, base + "/archive/use")
    for remote, local in {dated.name: dated, "index.php": Path(__file__).parent / "use_archive.php"}.items():
        with open(local, "rb") as f:
            ftp.storbinary(f"STOR {remote}", f)
    logger.info("Archived https://jonestech.xyz/archive/use/%s", dated.name)
    ftp.quit()


def main(dry_run: bool = False, featured: Path | None = None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    past = past_editions(f"{now:%Y-%m-%d}")
    job = JOBS[now.timetuple().tm_yday % len(JOBS)]
    logger.info("Use No. %d — area: %s", len(past) + 1, job)

    d = None
    if featured:
        d = normalise(json.loads(featured.read_text(encoding="utf-8")))
    else:
        for attempt in range(3):
            try:
                chosen = pick_idea(job, past)
                d = write_use(job, chosen) if chosen else None
            except Exception as e:
                logger.error("Groq attempt %d failed: %s", attempt + 1, e)
            if d:
                break
            time.sleep(5)
    if not d:
        logger.error("No edition written — aborting, live page untouched")
        return
    d.setdefault("category", job)
    logger.info("Use: %s", d["title"])

    image = d.get("image_url") or generate_image_b64(d.get("image_prompt", ""), style=ART_STYLE)
    page = build_html(d, len(past) + 1, now.strftime("%A %-d %B %Y"), image)
    live, dated = OUT_DIR / "Use.html", OUT_DIR / f"Use-{now:%Y-%m-%d}.html"
    live.write_text(page, encoding="utf-8")
    dated.write_text(page, encoding="utf-8")
    logger.info("Saved %s", live)

    if dry_run:
        logger.info("Dry run — skipping upload")
        return
    upload(live, dated)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--featured", type=Path)
    args = ap.parse_args()
    main(args.dry_run, args.featured)
