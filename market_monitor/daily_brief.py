"""
Daily Magazine Briefing — Wired-style HTML digest.

Pulls together:
  - Market overnight movers (from existing monitor)
  - Trump / AI / Chip news (Google News RSS)
  - Groq-written "One Big Read" feature
  - Saves to Side Hustler public folder as daily.html
  - Emails via Gmail
  - Pushover ping when ready

Usage:
    python daily_brief.py
    python daily_brief.py --dry-run   # build HTML only, no email/pushover
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import ftplib
import requests
from openai import OpenAI

# ── load .env ──────────────────────────────────────────────────────────────────
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# ── local imports ──────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from fetcher import fetch_all_asian_indices, fetch_watchlist, get_latest_session, ASIAN_INDICES
from detector import detect_movers, compute_atr
from correlations import get_correlated_eu_stocks, get_all_watchlist_symbols
from mailer import send_briefing

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── config ─────────────────────────────────────────────────────────────────────
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
PUSHOVER_USER  = "uwb6u3d6hqvcynmthjbwa1g6wyxhzo"
PUSHOVER_TOKEN = "afgjsjzi2gx7uitk9ty6275mq9ddd4"
OUTPUT_PATH    = Path(os.getenv("OUTPUT_PATH", "/tmp/daily.html"))
RSS_BASE       = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
UNSPLASH_API        = "https://api.unsplash.com/photos/random?query={query}&orientation=landscape&client_id={key}"

SECTION_IMAGES = {
    "The Trump Effect": "politics washington",
    "AI & Tech":        "artificial intelligence technology",
    "Chip World":       "semiconductor microchip technology",
    "Global Markets":   "stock market finance trading",
}

def get_unsplash_image(query: str) -> str:
    """Fetch a random relevant image URL from Unsplash API."""
    if not UNSPLASH_ACCESS_KEY:
        return ""
    try:
        r = requests.get(
            UNSPLASH_API.format(query=requests.utils.quote(query), key=UNSPLASH_ACCESS_KEY),
            timeout=8
        )
        r.raise_for_status()
        return r.json()["urls"]["regular"]
    except Exception as e:
        logger.warning("Unsplash failed for '%s': %s", query, e)
        return ""

groq = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

NEWS_FEEDS = [
    {"section": "The Trump Effect",  "icon": "🇺🇸", "query": "Trump+tariffs+OR+Trump+trade+OR+Trump+economy+OR+\"Trump+says\""},
    {"section": "AI & Tech",         "icon": "🤖", "query": "AI+breakthrough+OR+OpenAI+OR+Anthropic+OR+\"new+AI+model\"+OR+Gemini"},
    {"section": "Chip World",        "icon": "⚡", "query": "NVIDIA+OR+ASML+OR+AMD+OR+semiconductor+earnings+OR+chip+ban+OR+export+controls"},
    {"section": "Global Markets",    "icon": "🌍", "query": "stock+market+OR+Fed+rates+OR+inflation+OR+\"market+rally\"+OR+\"market+crash\""},
    {"section": "China & Asia",      "icon": "🐉", "query": "China+economy+OR+China+tech+OR+China+trade+OR+\"Belt+and+Road\"+OR+Yuan"},
    {"section": "Energy & Climate",  "icon": "🔋", "query": "oil+price+OR+energy+stocks+OR+\"clean+energy\"+OR+\"electric+vehicles\"+OR+\"battery+technology\""},
    {"section": "Apple Silicon",     "icon": "🍎", "query": "\"Apple+Silicon\"+OR+\"Mac+Mini\"+OR+\"Mac+Studio\"+OR+\"M4\"+OR+\"M5\"+OR+\"Apple+chip\"+launch+OR+release+OR+announced"},
]

# ── IPO watchlist ──────────────────────────────────────────────────────────────
IPO_WATCHLIST = [
    {"name": "OpenAI",      "sector": "AI",         "valuation": "$157B", "status": "Rumoured",  "note": "Biggest potential IPO in history"},
    {"name": "Anthropic",   "sector": "AI",         "valuation": "$61B",  "status": "Rumoured",  "note": "Amazon & Google backed"},
    {"name": "SpaceX",      "sector": "Aerospace",  "valuation": "$350B", "status": "Starlink?", "note": "Starlink spin-off more likely than full IPO"},
    {"name": "Stripe",      "sector": "Fintech",    "valuation": "$65B",  "status": "Rumoured",  "note": "Long-delayed, pressure from investors"},
    {"name": "Databricks",  "sector": "Data/AI",    "valuation": "$62B",  "status": "Rumoured",  "note": "AI data layer, NVIDIA partner"},
    {"name": "Klarna",      "sector": "Fintech",    "valuation": "$15B",  "status": "Filed",     "note": "BNPL leader, NYSE filing submitted"},
    {"name": "Chime",       "sector": "Fintech",    "valuation": "$25B",  "status": "Rumoured",  "note": "US challenger bank"},
    {"name": "Canva",       "sector": "Design/AI",  "valuation": "$26B",  "status": "Rumoured",  "note": "Profitable, no rush but watching"},
]

STATUS_COLORS = {
    "Filed":     "#00e676",
    "Imminent":  "#ff3c00",
    "Rumoured":  "#f59e0b",
    "Starlink?": "#00e5ff",
}

ASIA_PACIFIC_FEED = {
    "section": "Asia Pacific", "icon": "🌏",
    "query": "Japan+economy+OR+South+Korea+tech+OR+Australia+mining+OR+Singapore+OR+Asia+Pacific+markets+OR+Nikkei+OR+ASX"
}

SECTION_IMAGES["China & Asia"]     = "china asia technology"
SECTION_IMAGES["Energy & Climate"] = "solar energy wind power"
SECTION_IMAGES["Asia Pacific"]     = "tokyo japan asia skyline"

# ── rss fetch ──────────────────────────────────────────────────────────────────
def get_og_image(url: str) -> str:
    """Follow redirects and extract og:image from an article URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        # follow redirects to get real article URL
        r = requests.get(url, timeout=8, headers=headers, allow_redirects=True)
        final_url = r.url
        # if still on Google, try to extract the real URL from the page
        if "google.com" in final_url:
            match = re.search(r'href="(https?://(?!google)[^"]+)"', r.text)
            if match:
                r = requests.get(match.group(1), timeout=8, headers=headers, allow_redirects=True)
        # find og:image meta tag
        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', r.text, re.IGNORECASE)
        if not match:
            match = re.search(r'<meta[^>]+content=["\'](https?://[^"\']+)["\'][^>]+property=["\']og:image["\']', r.text, re.IGNORECASE)
        if match:
            img = match.group(1)
            if not any(x in img for x in ['pixel', 'tracker', '1x1', 'blank']):
                return img
    except Exception:
        pass
    return ""

def fetch_rss(query: str, max_age_hours: int = 20, limit: int = 6) -> list[dict]:
    url = RSS_BASE.format(query=query)
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        now = datetime.now(timezone.utc)
        for item in root.findall(".//item"):
            if len(items) >= limit:
                break
            title  = item.findtext("title", "")
            link   = item.findtext("link", "")
            guid   = item.findtext("guid", link)
            pub    = item.findtext("pubDate", "")
            source = item.findtext("source", "")
            try:
                pub_dt    = parsedate_to_datetime(pub)
                age_hours = (now - pub_dt).total_seconds() / 3600
                if age_hours > max_age_hours:
                    continue
                pub_str = pub_dt.strftime("%-I:%M %p")
            except Exception:
                pub_str = ""
            # strip source from title (Google News appends " - Source Name")
            clean_title = re.sub(r"\s*-\s*[^-]+$", "", title).strip()
            items.append({"title": clean_title, "link": link, "pub": pub_str, "source": source})
        return items
    except Exception as e:
        logger.error("RSS failed for %s: %s", query, e)
        return []

# ── market data ────────────────────────────────────────────────────────────────
def get_market_data() -> dict:
    try:
        asian_data   = fetch_all_asian_indices(lookback_days=30)
        asian_movers = detect_movers(asian_data, ASIAN_INDICES)
        correlated   = get_correlated_eu_stocks(asian_movers)
        eu_symbols   = get_all_watchlist_symbols()
        eu_raw       = fetch_watchlist(eu_symbols, lookback_days=5)
        eu_data      = {}
        for sym, df in eu_raw.items():
            session = get_latest_session(df)
            if session:
                session["atr"] = compute_atr(df)
                eu_data[sym] = session
        return {"asian_movers": asian_movers, "correlated": correlated, "eu_data": eu_data}
    except Exception as e:
        logger.error("Market data failed: %s", e)
        return {"asian_movers": [], "correlated": [], "eu_data": {}}

# ── groq helpers ───────────────────────────────────────────────────────────────

def groq_article_takes(headlines: list[str], section: str) -> list[str]:
    """Return a one-line market prediction/analysis for each headline."""
    if not headlines:
        return []
    try:
        numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a sharp market analyst. Be direct, contrarian when warranted, and specific. No fluff."},
                {"role": "user", "content": f"""For each headline in the {section} section, write ONE punchy sentence: a market implication, prediction, or contrarian take. Be specific — mention stocks, sectors or price impacts where relevant.

Headlines:
{numbered}

Return a JSON array of strings, one per headline, same order. Return ONLY the JSON array."""}
            ],
            temperature=0.5,
            max_tokens=400,
        )
        content = resp.choices[0].message.content.strip()
        content = re.sub(r"^```[\w]*\n?", "", content).strip()
        content = re.sub(r"\n?```$", "", content).strip()
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            takes = json.loads(match.group(0))
            return [str(t) for t in takes]
    except Exception as e:
        logger.warning("Article takes failed: %s", e)
    return [""] * len(headlines)

def groq_summarise(headlines: list[str], section: str) -> str:
    if not headlines:
        return ""
    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a sharp financial journalist. Be concise, insightful, no fluff."},
                {"role": "user", "content": f"Write a 2-sentence editor's summary of these {section} headlines:\n" + "\n".join(f"- {h}" for h in headlines)}
            ],
            temperature=0.4, max_tokens=120,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Groq summarise failed: %s", e)
        return ""

def groq_big_read(all_headlines: list[str]) -> dict:
    if not all_headlines:
        return {"title": "", "body": ""}
    try:
        headlines_str = "\n".join(f"- {h}" for h in all_headlines[:20])
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a Wired magazine staff writer. Return ONLY valid JSON with no markdown, no code fences, no extra text."},
                {"role": "user", "content": f"From these headlines pick the most important story and write a Wired-style feature. Return ONLY this JSON structure with no other text:\n{{\"title\": \"short punchy headline\", \"standfirst\": \"one bold sentence\", \"body\": \"three paragraphs separated by double newline\"}}\n\nHeadlines:\n{headlines_str}"}
            ],
            temperature=0.5, max_tokens=600,
        )
        content = resp.choices[0].message.content.strip()

        def extract_field(key):
            # match "key": "value" allowing multiline values
            pattern = rf'"{key}"\s*:\s*"((?:[^"\\]|\\.|\n)*)"'
            m = re.search(pattern, content, re.DOTALL)
            if m:
                return m.group(1).replace('\n', ' ').replace('\r', '').strip()
            return ""

        return {
            "title":      extract_field("title"),
            "standfirst": extract_field("standfirst"),
            "body":       extract_field("body"),
        }
    except Exception as e:
        logger.error("Groq big read failed: %s", e)
        return {"title": "Markets in Motion", "standfirst": "", "body": ""}

AI_TECH_WATCHLIST = [
    {"sym": "TSM",   "name": "TSMC",           "asia_link": "Taiwan Semiconductor Index — direct proxy"},
    {"sym": "NVDA",  "name": "Nvidia",          "asia_link": "TSMC-fabbed; tracks Taiwan semi + Nikkei tech"},
    {"sym": "AMD",   "name": "AMD",             "asia_link": "TSMC-fabbed; Taiwan exposure"},
    {"sym": "AVGO",  "name": "Broadcom",        "asia_link": "Asia semiconductor supply chain"},
    {"sym": "ARM",   "name": "Arm Holdings",    "asia_link": "SoftBank-owned; Nikkei correlated"},
    {"sym": "SMCI",  "name": "Super Micro",     "asia_link": "Taiwan/Japan server supply chain"},
    {"sym": "MRVL",  "name": "Marvell Tech",    "asia_link": "TSMC + Samsung fab dependent"},
    {"sym": "QCOM",  "name": "Qualcomm",        "asia_link": "Samsung fab + Asia mobile market"},
    {"sym": "MSFT",  "name": "Microsoft",       "asia_link": "Azure Asia-Pacific growth"},
    {"sym": "GOOGL", "name": "Alphabet",        "asia_link": "Asia ad revenue + TPU supply chain"},
    {"sym": "META",  "name": "Meta",            "asia_link": "Asia hardware + Reality Labs supply"},
    {"sym": "PLTR",  "name": "Palantir",        "asia_link": "AI gov contracts — sentiment play"},
]

def groq_ai_correlation(asian_movers: list) -> dict:
    """Generate AI stock signals based on Asian market movements. Returns JSON-serialisable dict."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not asian_movers:
        return {
            "generated_at": now_utc,
            "asian_summary": "No significant Asian movers overnight.",
            "stocks": []
        }

    mover_str = "; ".join(
        f"{m.get('name','?')} ({m.get('pct_change',0):+.1f}%, vol ×{m.get('volume_ratio',1):.1f})"
        for m in asian_movers[:8]
    )

    stock_list = "\n".join(
        f"- {s['sym']} ({s['name']}): {s['asia_link']}"
        for s in AI_TECH_WATCHLIST
    )

    try:
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": (
                    "You are a professional equity analyst specialising in AI/semiconductor stocks. "
                    "Be specific, direct, and actionable. No fluff. Never say 'it's important to note' or similar."
                )},
                {"role": "user", "content": f"""Asian markets just closed with these moves:
{mover_str}

For each of the following AI/tech stocks, give a signal and analysis based on today's Asian session:
{stock_list}

Return a JSON object with this exact structure (no markdown, no code fences):
{{
  "asian_summary": "1 sentence summary of what Asian markets did and what it means for US tech open",
  "stocks": [
    {{
      "sym": "NVDA",
      "signal": "bullish" | "bearish" | "neutral",
      "confidence": "high" | "medium" | "low",
      "asia_driver": "which Asian index/event is moving this stock today",
      "analysis": "2 sentences: what the Asian move means for this stock at US open and why",
      "watch": "1 specific price level or condition to watch today"
    }}
  ]
}}

Cover all {len(AI_TECH_WATCHLIST)} stocks. Return ONLY the JSON object."""}
            ],
            temperature=0.4,
            max_tokens=1800,
        )
        content = resp.choices[0].message.content.strip()
        content = re.sub(r"^```[\w]*\n?", "", content).strip()
        content = re.sub(r"\n?```$", "", content).strip()
        data = json.loads(content)
        data["generated_at"] = now_utc
        return data
    except Exception as e:
        logger.error("AI correlation Groq call failed: %s", e)
        return {
            "generated_at": now_utc,
            "asian_summary": mover_str,
            "stocks": [{"sym": s["sym"], "name": s["name"], "signal": "neutral",
                        "confidence": "low", "asia_driver": s["asia_link"],
                        "analysis": "Analysis unavailable.", "watch": "—"}
                       for s in AI_TECH_WATCHLIST]
        }


def groq_market_take(movers: list) -> str:
    if not movers:
        return "Markets quiet overnight."
    try:
        mover_str = ", ".join(f"{m.get('name','?')} ({m.get('pct_change',0):+.1f}%)" for m in movers[:6])
        resp = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a markets desk analyst. Two sentences max."},
                {"role": "user", "content": f"Give a sharp overnight take on these Asian movers: {mover_str}"}
            ],
            temperature=0.3, max_tokens=80,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return ""

# ── html builder ───────────────────────────────────────────────────────────────
def build_html(market: dict, news_sections: list, big_read: dict, date_str: str, ap_section: dict = None) -> str:

    # market mover cards
    def mover_card(m):
        pct   = m.get("pct_change", 0)
        color = "#00e676" if pct >= 0 else "#ff5252"
        arrow = "▲" if pct >= 0 else "▼"
        return f"""
        <div class="mover-card">
          <div class="mover-name">{m.get('name', m.get('symbol','?'))}</div>
          <div class="mover-pct" style="color:{color}">{arrow} {abs(pct):.1f}%</div>
        </div>"""

    asian_cards = "".join(mover_card(m) for m in market["asian_movers"][:8]) or "<p style='color:#666'>No significant movers overnight.</p>"

    # eu watchlist table rows
    def eu_row(sym, d):
        pct   = d.get("pct_change", 0)
        color = "#00e676" if pct >= 0 else "#ff5252"
        arrow = "▲" if pct >= 0 else "▼"
        close = d.get("close", 0)
        return f"""
        <tr>
          <td class="sym">{sym}</td>
          <td>{d.get('name', sym)}</td>
          <td style="color:{color}">{arrow} {abs(pct):.1f}%</td>
          <td class="price">{close:.2f}</td>
        </tr>"""

    eu_rows = "".join(eu_row(sym, d) for sym, d in list(market["eu_data"].items())[:12]) or "<tr><td colspan='4' style='color:#666;padding:16px'>No data available.</td></tr>"

    # correlated alerts
    corr_items = ""
    for c in market["correlated"][:4]:
        corr_items += f"<li>📡 <strong>{c.get('eu_stock','?')}</strong> — watch on {c.get('driver','?')} move</li>"
    corr_block = f"<ul class='corr-list'>{corr_items}</ul>" if corr_items else ""

    # news sections
    def news_section(section_data, summary):
        items_html = ""
        for item in section_data["items"]:
            take_html = f'<div class="news-take">⚡ {item["take"]}</div>' if item.get("take") else ""
            items_html += f"""
            <div class="news-item-wrap">
              <a class="news-item" href="{item['link']}" target="_blank">
                <span class="news-title">{item['title']}</span>
                <span class="news-time">{item['pub']}</span>
              </a>
              {take_html}
            </div>"""
        summary_html = f'<div class="ai-label">⚡ AI Analysis</div><p class="section-summary">{summary}</p>' if summary else ""
        keywords = SECTION_IMAGES.get(section_data['section'], "news business")
        img_url  = get_unsplash_image(keywords)
        return f"""
        <div class="section">
          {f'<img class="section-img" src="{img_url}" alt="{section_data["section"]}">' if img_url else ""}
          <div class="section-header">
            <span class="section-icon">{section_data['icon']}</span>
            <h2>{section_data['section']}</h2>
          </div>
          {summary_html}
          <div class="news-list">{items_html}</div>
        </div>"""

    news_html = "".join(news_section(s, s.get("summary", "")) for s in news_sections)

    # big read
    big_read_html = ""
    if big_read.get("title"):
        body_paras = "".join(f"<p>{p.strip()}</p>" for p in big_read.get("body","").split("\n\n") if p.strip())
        br_img = ""  # Big Read: no hero image, let the typography carry it
        big_read_html = f"""
        <div class="big-read">
          {f'<img class="big-read-img" src="{br_img}" alt="{big_read["title"]}">' if br_img else ""}
          <div class="big-read-label">ONE BIG READ &nbsp;<span class="ai-label">⚡ AI Written</span></div>
          <h2 class="big-read-title">{big_read['title']}</h2>
          <p class="big-read-standfirst">{big_read.get('standfirst','')}</p>
          <div class="big-read-body">{body_paras}</div>
        </div>"""

    market_take = market.get("take", "")
    market_take_html = f'<div class="ai-label">⚡ AI Analysis</div><p class="market-take">"{market_take}"</p>' if market_take else ""

    # ── sidebar ──
    sidebar_movers = "".join(f"""
      <div class="sidebar-mover">
        <span class="sidebar-mover-name">{m.get('name', m.get('symbol','?'))}</span>
        <span class="sidebar-mover-pct" style="color:{'#00e676' if m.get('pct_change',0)>=0 else '#ff5252'}">
          {'▲' if m.get('pct_change',0)>=0 else '▼'} {abs(m.get('pct_change',0)):.1f}%
        </span>
      </div>""" for m in market["asian_movers"][:8]) or "<p style='color:#666;font-size:12px'>No movers overnight.</p>"

    sidebar_watchlist = "".join(f"""
      <tr>
        <td class="sym">{sym}</td>
        <td style="font-size:11px;color:#ccc">{d.get('name',sym)[:16]}</td>
        <td style="color:{'#00e676' if d.get('pct_change',0)>=0 else '#ff5252'};text-align:right;font-weight:600">
          {'▲' if d.get('pct_change',0)>=0 else '▼'}{abs(d.get('pct_change',0)):.1f}%
        </td>
        <td class="price">{d.get('close',0):.2f}</td>
      </tr>""" for sym, d in list(market["eu_data"].items())[:20])

    ap_items_html = ""
    if ap_section and ap_section.get("items"):
        for item in ap_section["items"][:6]:
            take = f'<div class="ap-take">⚡ {item["take"]}</div>' if item.get("take") else ""
            ap_items_html += f"""
            <div class="ap-item">
              <div class="ap-title"><a href="{item['link']}" target="_blank">{item['title']}</a></div>
              <div class="ap-time">{item['pub']}</div>
              {take}
            </div>"""

    # IPO watchlist card
    ipo_items_html = ""
    for ipo in IPO_WATCHLIST:
        color = STATUS_COLORS.get(ipo["status"], "#888")
        ipo_items_html += f"""
        <div class="ipo-item">
          <div class="ipo-top">
            <span class="ipo-name">{ipo['name']}</span>
            <span class="ipo-val">{ipo['valuation']}</span>
          </div>
          <div class="ipo-meta">
            <span class="ipo-status" style="color:{color}">{ipo['status']}</span>
            <span class="ipo-sector">{ipo['sector']}</span>
          </div>
          <div class="ipo-note">{ipo['note']}</div>
        </div>"""

    sidebar_html = f"""
    <div class="sidebar">
      <div class="sidebar-card">
        <div class="sidebar-label">🌏 Asian Overnight</div>
        {sidebar_movers}
        {market_take_html}
      </div>
      <div class="sidebar-card">
        <div class="sidebar-label">🌐 Global Tech</div>
        <table class="sidebar-watchlist">
          <tbody>{sidebar_watchlist}</tbody>
        </table>
      </div>
      <div class="sidebar-card">
        <div class="sidebar-label">🚀 IPO Watch</div>
        {ipo_items_html}
      </div>
      {f'''<div class="sidebar-card">
        <div class="sidebar-label">🌏 Asia Pacific News</div>
        {ap_items_html}
      </div>''' if ap_items_html else ""}
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Brief — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&family=Playfair+Display:ital,wght@0,700;0,900;1,400&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0a0a0a;
    --surface: #111;
    --surface2: #1a1a1a;
    --border: #222;
    --text: #e8e8e8;
    --text-dim: #888;
    --accent: #ff3c00;
    --accent2: #00e5ff;
    --green: #00e676;
    --red: #ff5252;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    font-size: 15px;
    line-height: 1.6;
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 24px 60px;
  }}

  .page-layout {{
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: 32px;
    align-items: start;
  }}

  .main-col {{ min-width: 0; }}

  .sidebar {{
    position: sticky;
    top: 20px;
  }}

  /* MASTHEAD */
  .masthead {{
    border-bottom: 3px solid var(--accent);
    padding: 40px 0 20px;
    margin-bottom: 40px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }}

  .masthead-title {{
    font-family: 'Playfair Display', serif;
    font-size: 52px;
    font-weight: 900;
    letter-spacing: -2px;
    line-height: 1;
    color: #fff;
  }}

  .masthead-title span {{ color: var(--accent); }}

  .masthead-meta {{
    text-align: right;
    color: var(--text-dim);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }}

  .masthead-date {{
    font-size: 14px;
    color: var(--text);
    font-weight: 600;
    display: block;
    margin-bottom: 4px;
  }}

  /* MARKET STRIP */
  .market-strip {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 40px;
  }}

  .strip-label {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 16px;
  }}

  .movers-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 16px;
  }}

  .mover-card {{
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 16px;
    min-width: 120px;
  }}

  .mover-name {{
    font-size: 11px;
    color: var(--text-dim);
    font-weight: 600;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
  }}

  .mover-pct {{
    font-size: 18px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }}

  .market-take {{
    font-style: italic;
    color: var(--text-dim);
    font-size: 14px;
    border-left: 3px solid var(--accent);
    padding-left: 14px;
    margin-top: 16px;
  }}

  /* WATCHLIST TABLE */
  .watchlist {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 20px;
    font-size: 13px;
  }}

  .watchlist th {{
    text-align: left;
    color: var(--text-dim);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
  }}

  .watchlist td {{
    padding: 10px 12px;
    border-bottom: 1px solid #1a1a1a;
  }}

  .watchlist .sym {{
    font-family: monospace;
    font-weight: 700;
    color: var(--accent2);
  }}

  .watchlist .price {{
    font-variant-numeric: tabular-nums;
    color: var(--text-dim);
  }}

  .corr-list {{
    list-style: none;
    margin-top: 16px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }}

  .corr-list li {{
    background: rgba(0,229,255,0.06);
    border: 1px solid rgba(0,229,255,0.15);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
  }}

  /* BIG READ */
  .big-read {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 36px;
    margin-bottom: 40px;
    border-left: 4px solid var(--accent);
  }}

  .big-read-label {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 14px;
  }}

  .big-read-title {{
    font-family: 'Playfair Display', serif;
    font-size: 32px;
    font-weight: 900;
    line-height: 1.2;
    margin-bottom: 14px;
    color: #fff;
  }}

  .big-read-standfirst {{
    font-size: 17px;
    font-weight: 500;
    color: #bbb;
    margin-bottom: 20px;
    line-height: 1.5;
  }}

  .big-read-body p {{
    margin-bottom: 14px;
    color: #ccc;
    font-size: 14px;
    line-height: 1.75;
  }}

  /* NEWS SECTIONS */
  .section {{
    margin-bottom: 40px;
  }}

  .section-img {{
    width: 100%;
    height: 200px;
    object-fit: cover;
    border-radius: 8px;
    margin-bottom: 14px;
    display: block;
    background: var(--surface2);
  }}

  .big-read-img {{
    width: 100%;
    height: 280px;
    object-fit: cover;
    border-radius: 8px;
    margin-bottom: 20px;
    display: block;
  }}

  .section-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }}

  .section-icon {{ font-size: 20px; }}

  .section-header h2 {{
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-dim);
  }}

  .ai-label {{
    display: inline-block;
    background: rgba(124,58,237,0.15);
    border: 1px solid rgba(124,58,237,0.4);
    color: #a78bfa;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 4px;
    margin-bottom: 6px;
  }}

  .section-summary {{
    font-size: 13px;
    color: #bbb;
    font-style: italic;
    margin-bottom: 14px;
    padding: 12px 14px;
    background: rgba(124,58,237,0.07);
    border-radius: 6px;
    border-left: 3px solid rgba(124,58,237,0.4);
  }}

  .news-list {{
    display: flex;
    flex-direction: column;
    gap: 0;
  }}

  .news-item-wrap {{
    border-bottom: 1px solid #1a1a1a;
    padding-bottom: 10px;
    margin-bottom: 10px;
  }}

  .news-item-wrap:last-child {{
    border-bottom: none;
  }}

  .news-item {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 16px;
    padding: 11px 14px;
    border-radius: 7px;
    text-decoration: none;
    color: var(--text);
    transition: background 0.15s;
  }}

  .news-item:hover {{
    background: var(--surface);
  }}

  .news-title {{
    font-size: 14px;
    font-weight: 500;
    line-height: 1.4;
    flex: 1;
  }}

  .news-time {{
    font-size: 11px;
    color: var(--text-dim);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }}

  .news-take {{
    font-size: 12px;
    color: #a78bfa;
    font-style: italic;
    margin-top: 4px;
    padding-left: 2px;
    line-height: 1.4;
  }}

  /* FOOTER */
  .footer {{
    border-top: 1px solid var(--border);
    padding-top: 20px;
    margin-top: 40px;
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: var(--text-dim);
  }}

  .grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 40px;
  }}

  /* SIDEBAR */
  .sidebar-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
  }}

  .sidebar-label {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 14px;
  }}

  .sidebar-mover {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 7px 0;
    border-bottom: 1px solid #1a1a1a;
    font-size: 13px;
  }}

  .sidebar-mover:last-child {{ border-bottom: none; }}

  .sidebar-mover-name {{ color: var(--text-dim); font-size: 12px; }}

  .sidebar-mover-pct {{
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    font-size: 14px;
  }}

  .sidebar-watchlist {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    margin-top: 4px;
  }}

  .sidebar-watchlist td {{
    padding: 6px 4px;
    border-bottom: 1px solid #1a1a1a;
  }}

  .sidebar-watchlist tr:last-child td {{ border-bottom: none; }}

  .sidebar-watchlist .sym {{
    font-family: monospace;
    font-weight: 700;
    color: var(--accent2);
    font-size: 11px;
  }}

  .sidebar-watchlist .price {{
    font-variant-numeric: tabular-nums;
    color: var(--text-dim);
    text-align: right;
  }}

  .ap-item {{
    padding: 9px 0;
    border-bottom: 1px solid #1a1a1a;
    font-size: 13px;
  }}

  .ap-item:last-child {{ border-bottom: none; }}

  .ap-title {{ font-weight: 500; line-height: 1.4; margin-bottom: 3px; }}
  .ap-title a {{ color: var(--text); text-decoration: none; }}
  .ap-title a:hover {{ color: var(--accent2); }}
  .ap-time {{ font-size: 11px; color: var(--text-dim); }}
  .ap-take {{ font-size: 11px; color: #a78bfa; font-style: italic; margin-top: 3px; }}

  /* IPO WATCH */
  .ipo-item {{
    padding: 9px 0;
    border-bottom: 1px solid #1a1a1a;
  }}
  .ipo-item:last-child {{ border-bottom: none; }}
  .ipo-top {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 6px;
    margin-bottom: 3px;
  }}
  .ipo-name {{
    font-weight: 700;
    font-size: 13px;
    color: #fff;
  }}
  .ipo-val {{
    font-size: 12px;
    font-weight: 700;
    color: var(--accent2);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }}
  .ipo-meta {{
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 3px;
  }}
  .ipo-status {{
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 1px 6px;
    border-radius: 3px;
    border: 1px solid currentColor;
  }}
  .ipo-sector {{
    font-size: 10px;
    color: var(--text-dim);
  }}
  .ipo-note {{
    font-size: 11px;
    color: #666;
    font-style: italic;
  }}

  @media (max-width: 900px) {{
    .page-layout {{ grid-template-columns: 1fr; }}
    .sidebar {{ position: static; }}
  }}

  @media (max-width: 600px) {{
    .masthead {{ flex-direction: column; gap: 12px; }}
    .masthead-meta {{ text-align: left; }}
    .masthead-title {{ font-size: 36px; }}
  }}
</style>
</head>
<body>

<div class="masthead">
  <div class="masthead-title">DAILY<span>.</span>BRIEF</div>
  <div class="masthead-meta">
    <span class="masthead-date">{date_str}</span>
    Markets · AI · Tech · Politics
  </div>
</div>

<div class="page-layout">

  <!-- MAIN COLUMN -->
  <div class="main-col">
    {big_read_html}
    {news_html}
  </div>

  <!-- SIDEBAR -->
  {sidebar_html}

</div>

<div class="footer">
  <span>Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</span>
  <span>Daily Brief · Your personal market intelligence</span>
</div>

</body>
</html>"""

# ── ftp upload ─────────────────────────────────────────────────────────────────
def ftp_upload(local_path: Path, remote_filename: str = "daily.html", attempts: int = 3):
    host = os.getenv("FTP_HOST", "")
    user = os.getenv("FTP_USER", "")
    pwd  = os.getenv("FTP_PASS", "")
    path = os.getenv("FTP_PATH", "/public_html/")

    if not all([host, user, pwd]):
        logger.warning("FTP credentials not set — skipping upload")
        return False

    def _store(ftp_cls, secure):
        with ftp_cls(host, timeout=60) as ftp:
            ftp.login(user, pwd)
            if secure:
                ftp.prot_p()  # switch to secure data connection
            ftp.cwd(path)
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_filename}", f)

    # Retry on transient timeouts; within each attempt, try secure FTP_TLS
    # first and fall back to plain FTP (mirrors aiworld.py's resilience).
    for attempt in range(1, attempts + 1):
        try:
            _store(ftplib.FTP_TLS, secure=True)
            logger.info("✅ Uploaded to https://jonestech.xyz/%s", remote_filename)
            return True
        except Exception as e:
            logger.warning("FTP_TLS attempt %d/%d failed (%s), trying plain FTP...",
                           attempt, attempts, e)
            try:
                _store(ftplib.FTP, secure=False)
                logger.info("✅ Uploaded via plain FTP to https://jonestech.xyz/%s", remote_filename)
                return True
            except Exception as e2:
                logger.warning("Plain FTP attempt %d/%d failed: %s", attempt, attempts, e2)
                if attempt < attempts:
                    time.sleep(5 * attempt)  # linear backoff before retrying

    logger.error("FTP upload failed after %d attempts — site not updated", attempts)
    return False

# ── pushover ───────────────────────────────────────────────────────────────────
def send_pushover(title: str, message: str):
    try:
        requests.post("https://api.pushover.net/1/messages.json", data={
            "token": PUSHOVER_TOKEN, "user": PUSHOVER_USER,
            "title": title, "message": message, "priority": 0,
            "url": "https://jonestech.xyz/daily.html", "url_title": "Read now"
        }, timeout=10)
        logger.info("Pushover sent")
    except Exception as e:
        logger.error("Pushover failed: %s", e)

# ── main ───────────────────────────────────────────────────────────────────────
def main(dry_run: bool = False):
    date_str = datetime.now().strftime("%A %-d %B %Y")
    logger.info("📰 Building Daily Brief — %s", date_str)

    # 1. Market data
    logger.info("Fetching market data...")
    market = get_market_data()
    market["take"] = groq_market_take(market["asian_movers"])

    # 2. News feeds
    all_headlines = []
    news_sections = []
    for feed in NEWS_FEEDS:
        logger.info("Fetching: %s", feed["section"])
        items = fetch_rss(feed["query"])
        headlines = [i["title"] for i in items]
        all_headlines.extend(headlines)
        summary = groq_summarise(headlines, feed["section"])
        takes   = groq_article_takes(headlines, feed["section"])
        # attach takes to items
        for i, item in enumerate(items):
            item["take"] = takes[i] if i < len(takes) else ""
        news_sections.append({**feed, "items": items, "summary": summary})

    # 3. Asia Pacific sidebar section
    logger.info("Fetching Asia Pacific news...")
    ap_items = fetch_rss(ASIA_PACIFIC_FEED["query"], limit=6)
    ap_takes  = groq_article_takes([i["title"] for i in ap_items], "Asia Pacific")
    for i, item in enumerate(ap_items):
        item["take"] = ap_takes[i] if i < len(ap_takes) else ""
    ap_section = {**ASIA_PACIFIC_FEED, "items": ap_items}

    # 4. AI correlation JSON for dashboard
    logger.info("Generating AI correlation analysis...")
    ai_corr = groq_ai_correlation(market["asian_movers"])
    ai_corr_path = OUTPUT_PATH.parent / "ai_correlation.json"
    ai_corr_path.write_text(json.dumps(ai_corr, indent=2), encoding="utf-8")
    logger.info("✅ AI correlation JSON saved")

    # 4b. One Big Read
    logger.info("Writing One Big Read...")
    big_read = groq_big_read(all_headlines)

    # 5. Build HTML
    logger.info("Building HTML...")
    html = build_html(market, news_sections, big_read, date_str, ap_section=ap_section)

    # 5. Save
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    logger.info("✅ Saved to %s", OUTPUT_PATH)

    if dry_run:
        logger.info("Dry run — skipping email, FTP and Pushover")
        return

    # 6. FTP upload to website
    logger.info("Uploading to jonestech.xyz...")
    ftp_upload(OUTPUT_PATH)
    ftp_upload(ai_corr_path, remote_filename="ai_correlation.json")

    # 7. Email — send full HTML
    gmail_user = os.getenv("GMAIL_USER", "")
    if gmail_user:
        plain = f"Daily Brief — {date_str}\n\nOpen in browser for best experience."
        send_briefing(f"📰 Daily Brief — {date_str}", plain, body_html=html)

    # 8. Pushover
    mover_count = len(market["asian_movers"])
    send_pushover(
        f"📰 Daily Brief — {date_str}",
        f"{mover_count} overnight mover{'s' if mover_count != 1 else ''}. {big_read.get('title', 'Read your briefing.')}"
    )

    logger.info("🎉 Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
