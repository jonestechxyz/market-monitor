"""
AIWorld.html — "The Marvel & The Panic": a daily global dispatch on what the
world is actually doing with AI, in the spirit of the BBC's "Tomorrow's World".

Text-forward, no images, more meat: scans AI news from around the world
(China, South Korea, Japan, Europe, India, the Gulf, the US and beyond),
then uses Groq to write a longer lead dispatch plus richer, multi-paragraph
entries split into THE MARVEL (where it's going right) and THE PANIC (where
it's going wrong) — each with a region dateline and a source link.

Usage:
    python aiworld.py
    python aiworld.py --dry-run   # build HTML only, no FTP upload
"""

import argparse
import ftplib
import json
import logging
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
OUTPUT_PATH  = Path(os.getenv("OUTPUT_PATH", "/tmp/AIWorld.html"))
RSS_BASE     = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

# Wide, deliberately GLOBAL net — regions first, then cross-cutting use-cases.
NEWS_QUERIES = [
    # ── regional coverage ──
    "China AI OR DeepSeek OR Baidu OR Alibaba OR Huawei AI",
    "South Korea AI OR Samsung AI OR Naver AI OR Korea robot",
    "Japan AI OR robotics OR SoftBank AI OR Japan automation",
    "India AI OR Bengaluru AI startup OR India AI mission",
    "Europe AI OR EU AI Act OR DeepMind OR Mistral AI",
    "UK AI OR Britain AI startup OR NHS AI",
    "Middle East AI OR UAE AI OR Saudi Arabia AI OR G42",
    "Taiwan AI OR TSMC AI chip OR Singapore AI",
    "Africa AI OR Latin America AI OR Brazil AI",
    # ── cross-cutting use-cases ──
    "AI medicine OR AI diagnosis OR AI drug discovery",
    "AI science OR AI research OR AI breakthrough lab",
    "AI scam OR deepfake fraud OR AI disinformation",
    "AI jobs OR AI layoffs OR AI replacing workers",
    "AI education OR AI accessibility OR AI translation",
    "AI energy OR AI climate OR AI agriculture",
    "AI military OR AI surveillance OR AI weapons",
]

# ── rss fetch ──────────────────────────────────────────────────────────────────
def fetch_rss(query: str, max_age_hours: int = 48, limit: int = 7) -> list[dict]:
    url = RSS_BASE.format(query=urllib.parse.quote(query))
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        now = datetime.now(timezone.utc)
        for item in root.findall(".//item"):
            if len(items) >= limit:
                break
            title = item.findtext("title", "")
            link  = item.findtext("link", "")
            pub   = item.findtext("pubDate", "")
            try:
                pub_dt    = parsedate_to_datetime(pub)
                age_hours = (now - pub_dt).total_seconds() / 3600
                if age_hours > max_age_hours:
                    continue
            except Exception:
                pass
            m = re.search(r"\s*-\s*([^-]+)$", title)
            src_name = m.group(1).strip() if m else ""
            clean_title = re.sub(r"\s*-\s*[^-]+$", "", title).strip()
            if clean_title:
                items.append({"title": clean_title, "link": link, "source": src_name})
        return items
    except Exception as e:
        logger.error("RSS failed for %s: %s", query, e)
        return []

# ── groq ───────────────────────────────────────────────────────────────────────
def groq_brief(items: list[dict]) -> dict:
    """Ask Groq to write a lead dispatch + richer marvel/panic entries."""
    if not items:
        return {}
    numbered = "\n".join(f"{i+1}. {it['title']}" for i, it in enumerate(items))
    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the editor of 'AI World — The Marvel & The Panic', a daily "
                        "global dispatch written in the spirit of the BBC's 'Tomorrow's World': "
                        "curious, clear and demonstrative. You explain HOW a technology actually "
                        "works, WHO is doing it and WHERE, WHY it matters, and WHAT happens next. "
                        "You have a genuinely international eye — you actively surface what is "
                        "happening in China, South Korea, Japan, India, Europe, the Gulf and the "
                        "wider world, not just Silicon Valley. You write substantial, meaty prose "
                        "with specifics and zero filler. No hype words, no 'game-changer', no "
                        "'revolutionary'. Return ONLY valid JSON, no markdown, no code fences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "From these headlines, build today's dispatch. Favour stories with a "
                        "clear country/region and a concrete, real-world use of AI. Spread the "
                        "coverage geographically — do not let it all be US/UK.\n\n"
                        "Produce JSON with this exact shape:\n"
                        "{\n"
                        '  "lead": {"source_index": n, "region": "City, COUNTRY", '
                        '"title": "...", "body": ["para1", "para2", "para3"]},\n'
                        '  "marvel": [ up to 4 of {"source_index": n, "region": "City, COUNTRY", '
                        '"title": "...", "body": ["para1", "para2"]} ],\n'
                        '  "panic":  [ up to 4 of {"source_index": n, "region": "City, COUNTRY", '
                        '"title": "...", "body": ["para1", "para2"]} ]\n'
                        "}\n\n"
                        "Rules:\n"
                        "- LEAD = the single most significant or interesting AI development today; "
                        "give it 3 solid paragraphs explaining what it is, how it works, and why "
                        "it matters globally.\n"
                        "- MARVEL = genuinely useful / impressive / hopeful uses; each 2 paragraphs.\n"
                        "- PANIC = worrying / risky / cautionary developments; each 2 paragraphs.\n"
                        "- Each paragraph 2-4 sentences, specific and informative.\n"
                        "- region is a short dateline like 'Shenzhen, China' or 'Seoul, South Korea'.\n"
                        "- source_index is the headline number the entry is based on.\n"
                        "- Cover at least 4 different countries across the whole dispatch.\n\n"
                        f"Headlines:\n{numbered}\n\n"
                        "Return ONLY the JSON object."
                    ),
                },
            ],
            temperature=0.65,
            max_tokens=4000,
        )
        content = resp.choices[0].message.content.strip()
        content = re.sub(r"^```[\w]*\n?", "", content).strip()
        content = re.sub(r"\n?```$", "", content).strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            data["marvel"] = (data.get("marvel") or [])[:4]
            data["panic"]  = (data.get("panic") or [])[:4]
            return data
    except Exception as e:
        logger.error("Groq brief failed: %s", e)
    return {}

def attach_link(entry: dict, items: list[dict]) -> dict:
    """Map a single entry's source_index back to the real article link + source."""
    try:
        idx = int(entry.get("source_index", 0)) - 1
        if 0 <= idx < len(items):
            entry["link"] = items[idx].get("link", "")
            entry["source"] = items[idx].get("source", "")
    except (ValueError, TypeError):
        pass
    entry.setdefault("link", "")
    entry.setdefault("source", "")
    return entry

# ── html builder ────────────────────────────────────────────────────────────────
def _paras(body) -> str:
    if isinstance(body, str):
        body = [body]
    return "".join(f"<p>{p}</p>" for p in (body or []) if p)

def _source(entry: dict) -> str:
    link = entry.get("link", "")
    if not link:
        return ""
    label = entry.get("source") or "Read the source"
    return f'<a class="src" href="{link}" target="_blank" rel="noopener">{label} ↗</a>'

def _entry(e: dict) -> str:
    region = (e.get("region") or "").upper()
    return f"""
      <article class="entry">
        <div class="dateline">{region}</div>
        <div class="entry-main">
          <h3 class="entry-title">{e.get('title','')}</h3>
          <div class="entry-body">{_paras(e.get('body'))}</div>
          {_source(e)}
        </div>
      </article>"""

def build_html(data: dict, date_str: str) -> str:
    lead = data.get("lead") or {}
    marvel = data.get("marvel") or []
    panic  = data.get("panic") or []
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lead_html = ""
    if lead:
        lead_html = f"""
  <section class="lead">
    <div class="dateline lead-dateline">{(lead.get('region') or '').upper()}</div>
    <h2 class="lead-title">{lead.get('title','')}</h2>
    <div class="lead-body">{_paras(lead.get('body'))}</div>
    {_source(lead)}
  </section>"""

    marvel_html = "".join(_entry(e) for e in marvel) or '<p class="empty">No marvels surfaced today.</p>'
    panic_html  = "".join(_entry(e) for e in panic)  or '<p class="empty">No panics surfaced today.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI World — The Marvel &amp; The Panic — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --paper: #f4f1ea;
    --ink: #1b1a17;
    --ink-soft: #4a4740;
    --rule: #cbc6ba;
    --marvel: #0a7d6b;
    --panic: #b22222;
    --link: #8a5a00;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--paper);
    color: var(--ink);
    font-family: 'Newsreader', Georgia, serif;
    font-size: 18px;
    line-height: 1.62;
    max-width: 940px;
    margin: 0 auto;
    padding: 0 26px 90px;
  }}
  /* ── MASTHEAD ── */
  .masthead {{ text-align: center; padding: 52px 0 22px; border-bottom: 3px double var(--ink); }}
  .eyebrow {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 11px; letter-spacing: 0.28em; text-transform: uppercase;
    color: var(--ink-soft); margin-bottom: 16px;
  }}
  .masthead h1 {{ font-family: 'Newsreader', serif; font-weight: 600; font-size: clamp(34px, 6.5vw, 62px); line-height: 1.04; letter-spacing: -0.5px; }}
  .masthead h1 .m {{ color: var(--marvel); font-style: italic; }}
  .masthead h1 .p {{ color: var(--panic); font-style: italic; }}
  .masthead .date {{ font-family: 'Space Grotesk', sans-serif; font-size: 13px; letter-spacing: 0.06em; color: var(--ink-soft); margin-top: 16px; }}
  .standfirst {{
    max-width: 660px; margin: 22px auto 0; font-size: 18px; font-style: italic;
    color: var(--ink-soft); line-height: 1.55;
  }}
  /* ── DATELINE ── */
  .dateline {{
    font-family: 'Space Grotesk', sans-serif; font-weight: 700;
    font-size: 11px; letter-spacing: 0.16em; text-transform: uppercase;
    color: var(--ink-soft);
  }}
  /* ── LEAD ── */
  .lead {{ padding: 38px 0 34px; border-bottom: 1px solid var(--rule); }}
  .lead-dateline {{ margin-bottom: 12px; }}
  .lead-title {{ font-weight: 600; font-size: clamp(26px, 4.6vw, 40px); line-height: 1.12; letter-spacing: -0.4px; margin-bottom: 18px; }}
  .lead-body p {{ margin-bottom: 16px; }}
  .lead-body p:first-of-type::first-letter {{
    font-size: 3.4em; line-height: 0.78; float: left;
    padding: 6px 10px 0 0; font-weight: 600; color: var(--ink);
  }}
  /* ── SECTIONS ── */
  .section {{ padding-top: 40px; }}
  .section-head {{ display: flex; align-items: baseline; gap: 14px; border-bottom: 2px solid var(--ink); padding-bottom: 8px; margin-bottom: 8px; }}
  .section-head h2 {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 17px; letter-spacing: 0.12em; text-transform: uppercase; }}
  .section.marvel h2 {{ color: var(--marvel); }}
  .section.panic h2 {{ color: var(--panic); }}
  .section-head .tag {{ font-family: 'Newsreader', serif; font-style: italic; font-size: 15px; color: var(--ink-soft); }}
  /* ── ENTRY ── */
  .entry {{ display: grid; grid-template-columns: 150px 1fr; gap: 24px; padding: 26px 0; border-bottom: 1px solid var(--rule); }}
  .entry .dateline {{ padding-top: 5px; }}
  .section.marvel .entry .dateline {{ color: var(--marvel); }}
  .section.panic .entry .dateline {{ color: var(--panic); }}
  .entry-title {{ font-weight: 600; font-size: 23px; line-height: 1.2; margin-bottom: 12px; }}
  .entry-body p {{ margin-bottom: 12px; }}
  .src {{
    font-family: 'Space Grotesk', sans-serif; font-size: 12px; letter-spacing: 0.04em;
    color: var(--link); text-decoration: none; display: inline-block; margin-top: 4px;
  }}
  .src:hover {{ text-decoration: underline; }}
  .empty {{ font-style: italic; color: var(--ink-soft); padding: 20px 0; }}
  /* ── FOOTER ── */
  .footer {{
    margin-top: 56px; border-top: 3px double var(--ink); padding-top: 20px;
    font-family: 'Space Grotesk', sans-serif; font-size: 12px; letter-spacing: 0.05em;
    color: var(--ink-soft); text-align: center;
  }}
  .footer a {{ color: var(--ink-soft); }}
  @media (max-width: 620px) {{
    .entry {{ grid-template-columns: 1fr; gap: 8px; }}
    .entry .dateline {{ padding-top: 0; }}
  }}
</style>
</head>
<body>

<header class="masthead">
  <div class="eyebrow">In the spirit of Tomorrow's World · A daily global dispatch on AI</div>
  <h1>The <span class="m">Marvel</span> &amp; The <span class="p">Panic</span></h1>
  <div class="date">{date_str}</div>
  <p class="standfirst">What the world is actually doing with artificial intelligence today — how it works, who is building it, and why it matters — from Shenzhen to Seoul to Silicon Valley.</p>
</header>
{lead_html}

<section class="section marvel">
  <div class="section-head"><h2>The Marvel</h2><span class="tag">where it's going right</span></div>
  {marvel_html}
</section>

<section class="section panic">
  <div class="section-head"><h2>The Panic</h2><span class="tag">where it's going wrong</span></div>
  {panic_html}
</section>

<footer class="footer">
  Compiled {generated} &nbsp;·&nbsp; Curation &amp; copy by Groq (Llama 3.3) &nbsp;·&nbsp; Headlines via Google News &nbsp;·&nbsp; jonestech.xyz
</footer>

</body>
</html>"""

# ── ftp upload ─────────────────────────────────────────────────────────────────
def ftp_upload(local_path: Path, remote_filename: str = "AIWorld.html"):
    host = os.getenv("FTP_HOST", "")
    user = os.getenv("FTP_USER", "")
    pwd  = os.getenv("FTP_PASS", "")
    path = os.getenv("FTP_PATH", "/public_html/")
    if not all([host, user, pwd]):
        logger.warning("FTP credentials not set — skipping upload")
        return False
    try:
        with ftplib.FTP_TLS(host, timeout=60) as ftp:
            ftp.login(user, pwd)
            ftp.prot_p()
            ftp.cwd(path)
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_filename}", f)
        logger.info("✅ Uploaded to https://jonestech.xyz/%s", remote_filename)
        return True
    except Exception as e:
        logger.warning("FTP_TLS failed (%s), trying plain FTP...", e)
        try:
            with ftplib.FTP(host, timeout=60) as ftp:
                ftp.login(user, pwd)
                ftp.cwd(path)
                with open(local_path, "rb") as f:
                    ftp.storbinary(f"STOR {remote_filename}", f)
            logger.info("✅ Uploaded via plain FTP to https://jonestech.xyz/%s", remote_filename)
            return True
        except Exception as e2:
            logger.error("FTP upload failed: %s", e2)
            return False

# ── main ────────────────────────────────────────────────────────────────────────
def main(dry_run: bool = False):
    date_str = datetime.now().strftime("%A %-d %B %Y")
    logger.info("✦ Building AIWorld dispatch — %s", date_str)

    # 1. Collect headlines (with links) from all feeds
    all_items = []
    for query in NEWS_QUERIES:
        logger.info("Fetching: %s", query[:50])
        all_items.extend(fetch_rss(query, limit=7))

    # Deduplicate by title
    seen, items = set(), []
    for it in all_items:
        key = it["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            items.append(it)
    logger.info("Got %d unique headlines", len(items))

    # 2. Groq writes the dispatch
    logger.info("Asking Groq to write the dispatch...")
    data = groq_brief(items[:70])
    if data.get("lead"):
        attach_link(data["lead"], items)
    data["marvel"] = [attach_link(e, items) for e in data.get("marvel", [])]
    data["panic"]  = [attach_link(e, items) for e in data.get("panic", [])]
    logger.info("Lead: %s | %d marvel | %d panic",
                bool(data.get("lead")), len(data.get("marvel", [])), len(data.get("panic", [])))

    # 3. Build HTML
    logger.info("Building HTML...")
    html = build_html(data, date_str)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    logger.info("✅ Saved to %s", OUTPUT_PATH)

    if dry_run:
        logger.info("Dry run — skipping FTP upload")
        return

    # 4. FTP upload
    logger.info("Uploading to jonestech.xyz...")
    ftp_upload(OUTPUT_PATH)
    logger.info("🎉 AIWorld done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
