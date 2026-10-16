"""
A Use a Day — one repetitive job from everyday working life, and a practical way to make
the phone or computer do it. Written for busy people who are not technical.

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
import random
import re
import time
from datetime import datetime
from pathlib import Path

import requests

from madworld import _ftp_connect, _ftp_mkdirs, generate_image_b64, groq

logger = logging.getLogger(__name__)

OUT_DIR = Path(os.getenv("USE_OUT", "/tmp/use"))
ARCHIVE = "https://jonestech.xyz/archive/use/"

# The area of work for each day, with real, well-known failures in it. The brainstorm attacks these instead of
# inventing pains of its own, which is how it ended up with clever-sounding nonsense.
JOBS = {
    "problems you spot while out and about that need reporting": [
        "you take a photo of a problem, mean to write it up later, and it is forgotten by evening",
        "a report arrives with no photo, no place and no date, so nobody can act on it",
        "the same fault is reported three times by three people and nobody knows it is one problem"],
    "email overload and things that get lost in the inbox": [
        "an important request sits unread under fifty newsletters until the deadline has passed",
        "an attachment someone needs is buried in a thread from months ago",
        "the same question arrives every week and gets typed out from scratch every time"],
    "meetings, notes and the actions nobody follows up": [
        "actions agreed in a meeting that nobody chases until they are urgent",
        "a decision made in a meeting that later nobody can prove",
        "notes typed up days later from memory, with half the detail gone"],
    "receipts, expenses and invoices": [
        "crumpled receipts found at month end, some unreadable, some lost",
        "the same invoice paid twice, or not at all",
        "an expense claim that takes an evening to put together"],
    "photos and screenshots you can never find again": [
        "thousands of phone photos and no way to find the one of the serial number or the whiteboard",
        "a screenshot of something important lost among memes and boarding passes",
        "no photo proof of when something happened when there is a dispute"],
    "deadlines, renewals and dates buried in documents": [
        "a warranty, insurance policy or certificate expires and nobody noticed",
        "a notice period in a contract missed by a week, costing a year of fees",
        "a free trial or subscription that renews at full price"],
    "forms and typing the same details again and again": [
        "the same name, address and reference number typed into ten forms a week",
        "a form sent back because one box was missed",
        "details copied from a PDF by hand with a typo in the account number"],
    "files, folders and finding the latest version": [
        "three files called final, final2 and final-REAL, and the wrong one sent",
        "a document someone needs lives only on one person's laptop",
        "an hour lost looking for a file everyone knows exists"],
    "checking long documents for the parts that matter": [
        "a 40-page contract signed without anyone noticing the auto-renewal clause",
        "a changed paragraph in a revised document that nobody spots",
        "two documents that disagree, found only after the work is done"],
    "chasing replies, approvals and signatures": [
        "a request for approval that sits for two weeks because nobody chased it",
        "no record of who was asked what and when",
        "work held up waiting for one signature"],
    "covering for someone who is away": [
        "a colleague on holiday and the key email sitting in their inbox",
        "nobody knows what was promised to a customer last week",
        "the same handover notes rewritten every time someone goes away"],
    "daily and weekly reports written from memory": [
        "the weekly report written on Friday afternoon from memory",
        "progress that can't be shown because nothing was recorded at the time",
        "hours spent formatting a report nobody reads closely"],
    "spreadsheets that go wrong quietly": [
        "a formula overwritten by a typed number and every total after it wrong",
        "two copies of the same spreadsheet edited by different people",
        "a list that quietly goes out of date because nobody updates it"],
    "phone calls and voicemails that leave no record": [
        "a promise made on the phone that nobody wrote down",
        "a voicemail with a phone number nobody can make out",
        "no record of who called about what when a complaint comes in"],
    "keeping track of who has what: keys, tools, equipment and loans": [
        "a tool or key lent out and never returned, and nobody knows who has it",
        "equipment due for a check or service that was missed",
        "buying something again because nobody knew the company already owned one"],
    "travel, mileage and time records": [
        "mileage claimed from guesswork weeks later",
        "timesheets filled in on Friday for the whole week",
        "no record of time spent on a job, so it can't be charged"],
}

# The menu of ways to automate. Each morning several are brainstormed side by side and the most surprising wins;
# anything used in the past week is off the table, so the column cannot settle into one trick.
TECHNIQUES = {
    "phone-shortcuts": "a one-tap button on the phone that does several steps at once, such as photo, spoken note, "
                       "place and email in one go",
    "phone-triggers": "the phone doing something by itself when you arrive somewhere, tap an NFC sticker, plug in "
                      "the charger, or at a set time",
    "text-in-photos": "the phone or computer reading the text inside photos and screenshots, so you can search and "
                      "copy it",
    "photo-metadata": "the date, time and place hidden inside every phone photo",
    "qr-and-nfc": "QR codes or NFC stickers on things, each opening the right form or doing a job when scanned",
    "voice-to-records": "speaking notes into the phone and having them turned into tidy, dated written records",
    "local-ai-reading": "an AI running on your own computer reading long documents and pulling out the parts that "
                        "matter, quoting the page",
    "local-ai-watcher": "an AI running on an office computer that checks a folder or inbox on a timer, reads each "
                        "new file and emails the right person what it found",
    "scheduled-mail": "a timed job that reads files or lists overnight and sends each person their own short email: "
                      "what is due, what changed, what is missing",
    "email-rules": "email rules and saved replies that sort, file and answer routine mail by themselves",
    "calendar-reminders": "turning dates buried in documents into calendar reminders that warn you in advance",
    "self-checking-sheets": "spreadsheet rules that flag problems by themselves: colour warnings, cross-checks, "
                            "totals that must agree",
    "combine-many-files": "Excel pulling dozens of separate files from a folder into one table, refreshed with one "
                          "click",
    "compare-versions": "comparing two versions of a document or spreadsheet and showing only what changed",
    "pdf-tools": "free tools that split, merge, stamp, number or fill PDFs in bulk",
    "public-data": "free public information joined to your own: public holidays, weather history, opening hours",
}
OVERDONE = ("filling a Word or Excel template once per row of a list (mail merge)",
            "renaming, sorting or filing files using a lookup list")

# Things these tools really do. Left to itself the AI credits tools with abilities they don't have (a PDF splitter
# "reading the title block"), so ideas are built from this list or from facts just as certain.
TOOL_FACTS = (
    "iPhone Shortcuts (free, built in) chains actions such as Take Photo, Dictate Text, Get Current Location, "
    "Extract Text from Image, Ask for Input, Add New Reminder, Add New Event, Append to Note, Make PDF and Send Email; "
    "with 'Show Compose Sheet' off, Send Email goes without you touching the keyboard",
    "a shortcut can sit on the home screen, or run from Back Tap (double or triple tap on the back of the iPhone, in "
    "Settings > Accessibility > Touch)",
    "iPhone personal automations run a shortcut when you arrive at or leave a place, at a set time, when an NFC "
    "sticker is tapped, when the charger is plugged in, or when an email arrives from a chosen sender",
    "Android does the same with free automation apps such as MacroDroid",
    "the iPhone Photos app and Google Photos find photos by the text inside them (search 'invoice' or a number)",
    "Microsoft PowerToys (free) adds Text Extractor (copy text from anything on screen) and PowerRename (rename "
    "hundreds of files by a rule)",
    "Excel can turn a photo of a printed table into cells (Data > From Picture), and Power Query's 'From Folder' "
    "lists every file in a folder in one table, refreshed in one click",
    "Outlook rules, Quick Steps and templates, and Gmail filters and templates, sort, label, forward and answer mail "
    "by themselves",
    "Whisper runs on your own computer (for example in the free MacWhisper or Buzz) and turns recordings into text",
    "LM Studio runs an AI on an ordinary computer with nothing sent online; a small program can hand it text or an "
    "image and get back what it reads",
    "Windows Task Scheduler (or launchd on a Mac) runs a small program every night or every hour by itself",
    "a small program can watch a folder or a mailbox, and send emails to set people",
    "pdftotext (free) pulls the text out of digitally made PDFs; scanned PDFs need OCR first (OCRmyPDF, free)",
    "ExifTool (free) reads the date, time and GPS position stored in every phone photo",
    "WinMerge (free) and Word's Compare show exactly what changed between two versions of a document",
)
LISTS = ("how", "need", "watch_out")
REQUIRED = ("title", "why", "idea", "before", "after", "person", "explain", "effort") + LISTS

ART_STYLE = ("vintage instruction-manual illustration, two-colour risograph print in teal and orange on cream paper, "
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


def chat_json(system: str, user: str, max_tokens: int, temperature: float, effort: str = "medium") -> dict | None:
    resp = groq.chat.completions.create(model="openai/gpt-oss-120b", temperature=temperature, max_tokens=max_tokens,
                                        reasoning_effort=effort,
                                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    content = resp.choices[0].message.content or ""
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        logger.error("No JSON in Groq response: %s", content[:300])
        return None
    return json.loads(m.group(0))


# Tricks everyone already knows. Ideas built on them read as bland, so the brainstorm is told to avoid them
# and the judge marks them down.
OBVIOUS = ("a QR code that just opens a document or a form", "a shared spreadsheet or register on a shared drive",
           "colour-coding a spreadsheet", "a cloud folder or shared link", "taking photos and filing them by date",
           "a checklist app", "a template", "a plain email reminder", "a to-do list app",
           "a shared calendar")


def brainstorm(job: str, past: list[dict], allowed: dict[str, str]) -> list[dict]:
    """Eight candidate ideas, each starting from a specific costly moment and naming the little-known trick."""
    keys = list(allowed)
    random.shuffle(keys)  # menu order steered which techniques got used, so it changes daily
    menu = "\n".join(f"- {k}: {allowed[k]}" for k in keys)
    pains = JOBS.get(job, [])
    pain_list = "\n".join(f"- {x}" for x in pains) or "(choose your own)"
    history = "\n".join(f"- {p['title']}" + (f" ({p['idea'][:160]})" if p["idea"] else "") for p in past[-40:]) or "(none yet)"
    d = chat_json(
        "You are the person every office, workshop and small business wishes they had: years of real work, then the "
        "one everyone asks how to get the phone or computer to do the boring part. You know the little-known features "
        "hidden in iPhone, Android, Excel, Outlook, Windows and Mac, and free tools, and the everyday moments where "
        "admin quietly costs hours, money or trust. Return ONLY valid JSON.",
        f"Area of everyday work today: {job}.\n\n"
        f"Ideas already published (do not repeat their job OR their method):\n{history}\n\n"
        f"BANNED methods, overdone in this column: {'; '.join(OVERDONE)}.\n"
        f"Everyone already knows these, so an idea that rests on them is worthless: {'; '.join(OBVIOUS)}.\n\n"
        f"Real, costly failures in this area that people know well:\n{pain_list}\n\n"
        f"Techniques to draw on (in no particular order):\n{menu}\n\n"
        "Tool facts you can rely on:\n" + "\n".join(f"- {x}" for x in TOOL_FACTS) + "\n"
        "Never credit a tool with something it cannot do. Build on these facts, or on others you are equally sure of.\n\n"
        "Brainstorm 8 ideas in today's area. Rules:\n"
        "1. Start each idea from a PAIN: preferably one of the failures listed above, or one just as real and well "
        "known. Say who it hurts and roughly what it costs in euros or hours. Do not invent unusual situations.\n"
        "2. Then the TRICK: the specific, little-known capability that fixes it, named precisely enough that someone "
        "could look it up (the feature, the tool, what it does). It must be real and exist today in free or common "
        "tools. Ordinary email and the phone's own apps are fine, but nothing may upload private documents to online AI "
        "or conversion websites. An idea may combine two techniques.\n"
        "3. Every idea must be about today's area, and useful to many kinds of working people, not one trade.\n"
        "4. Allowed and welcome: phone shortcuts and automations, an AI running locally on an ordinary computer (such "
        "as in LM Studio), small programs that run on a timer, read files or inboxes and email results to set people. "
        "Someone sets them up once; after that it just happens.\n"
        "5. At least half the ideas must be something an ordinary person can set up alone in under an hour, with no "
        "program at all, like a one-tap phone shortcut that photographs a problem, takes a spoken note and emails both "
        "to a set address. Use an AI or a small program only where it does something a simple rule or shortcut can't.\n"
        "6. Use only the technique keys listed above. Use at least 6 different techniques across the 8 ideas, and do not start with whichever is listed first.\n"
        "7. The test: if an ordinary office worker could guess how it works from the title, it is not surprising enough. Aim for "
        "'I had no idea my phone or Excel could do that'.\n\n"
        'Return JSON: {"ideas":[{"title":"...","technique":"<technique key>","pain":"one or two sentences",'
        '"trick":"one or two sentences","pitch":"one sentence"}]}',
        6000, 1.0, "medium")
    return [x for x in (d or {}).get("ideas", []) if isinstance(x, dict) and x.get("title")]


def judge(job: str, ideas: list[dict]) -> list[dict]:
    """A separate, sceptical reader scores the ideas; the brainstormer never marks its own work."""
    order = list(range(len(ideas)))
    random.shuffle(order)
    listing = "\n".join(f"[{i}] {ideas[i]['title']}\n    Pain: {ideas[i].get('pain', '')}\n    Trick: {ideas[i].get('trick', '')}"
                         for i in order)
    d = chat_json(
        "You are a hard-bitten office manager who has run teams in offices, workshops and on the road for thirty years "
        "and has no patience for gadgets. Salesmen have shown you every productivity app there is. You score ideas "
        "honestly and harshly. Return ONLY valid JSON.",
        f"Area of everyday work: {job}. Score each idea below.\n\n{listing}\n\n"
        "Score each 1-10 for:\n"
        "- surprise: would you, or a typical office worker, already know this trick? 10 = never heard of it and it is "
        f"clever; 2 = obvious. Anything resting on these scores 3 at most: {'; '.join(OBVIOUS)}.\n"
        "- payoff: hours, money or arguments it saves in a normal working week, judged from the pain described.\n"
        "- real: does the trick truly exist today in free or common tools, and does it keep private documents off "
        "online AI and conversion websites (ordinary email is fine)? Running an AI locally on an ordinary computer "
        "(LM Studio) is normal and fully realistic: do NOT mark it down for that, or for a small "
        "program on a timer that reads files and sends emails, if a capable helper could set it up in a day or two. "
        "Mark down anything vague, made up, needing the cloud, or needing a team of developers.\n"
        "- ease: 10 = anyone sets it up alone in minutes with what is already on their phone or computer; 5 = needs a "
        "helper for a day; 1 = a real software project. Mark down an AI or program doing what a plain rule could do.\n"
        f"- on_topic: is it really about {job}? 10 = squarely, 1 = a different job.\n"
        "- sense: is the pain one you have actually seen at work, and does the fix match how people really work? "
        "10 = happens everywhere, every week; 1 = invented or nonsense, however clever it sounds.\n\n"
        'Return JSON: {"scores":[{"id":n,"surprise":n,"payoff":n,"real":n,"ease":n,"on_topic":n,"sense":n,"comment":"a few words"}]}',
        3500, 0.2, "medium")
    out = []
    for sc in (d or {}).get("scores", []):
        try:
            idea = dict(ideas[int(sc["id"])])
            idea.update({k: int(sc.get(k) or 0) for k in ("surprise", "payoff", "real", "ease", "on_topic", "sense")}, comment=sc.get("comment", ""))
            out.append(idea)
        except (KeyError, ValueError, IndexError, TypeError):
            continue
    return out


def pick_idea(job: str, past: list[dict]) -> dict | None:
    """Brainstorm, have the ideas judged separately, and keep the most surprising one that is real and pays off."""
    recent = {p["technique"] for p in past[-7:] if p["technique"]}
    allowed = {k: v for k, v in TECHNIQUES.items() if k not in recent}
    pool = []
    for round_ in range(2):
        ideas = brainstorm(job, past, allowed)
        scored = judge(job, ideas) if ideas else []
        for x in scored:
            logger.info("  [%s] s%d p%d r%d e%d t%d n%d: %s (%s)", x.get("technique"), x["surprise"], x["payoff"],
                        x["real"], x["ease"], x["on_topic"], x["sense"], x["title"], x["comment"])
        pool += [x for x in scored if x["real"] >= 7 and x["payoff"] >= 5 and x["on_topic"] >= 8 and x["sense"] >= 7]
        if any(x["surprise"] >= 7 for x in pool):
            break
        logger.info("Nothing scored 7+ for surprise while staying real: brainstorming again")
    if not pool:
        return None
    best = max(pool, key=lambda x: (x["surprise"] * 2 + x["payoff"] + x["sense"] + x["ease"], x["real"]))
    if best.get("technique") not in allowed:
        logger.warning("Chosen idea used a technique outside today's menu (%s)", best.get("technique"))
    logger.info("Chosen: %s", best["title"])
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
        "You write a daily column for busy working people in Europe: office staff, small business owners, managers, "
        "tradespeople and people who work out on the road. They know their own jobs well and are NOT comfortable "
        "with technology. Write like a sharp colleague explaining over coffee: short sentences, plain words. "
        "Never use these words: prompt, model, LLM, parameters, tokens, output, input, generate, "
        "API, script, code, database, workflow, leverage. Say 'a small program' if one is needed, and 'the AI' for an "
        "AI assistant. European setting: euros, metric units, dates as day-month-year. Do not name or quote any law, "
        "regulation or contract clause number. Private documents must never be uploaded to online AI or conversion "
        "websites; ordinary email is fine. Only describe features you are sure exist in free or common tools; where a step needs a small "
        "program someone sets up once, say so plainly. Be honest about limits. Return ONLY valid JSON.",
        f"Today's date: {datetime.now():%d-%m-%Y}. Area of everyday work: {job}.\n"
        f"Today's idea, already chosen: {chosen.get('title')}. {chosen.get('pitch', '')}\n"
        f"The pain it fixes: {chosen.get('pain', '')}\n"
        f"The little-known trick: {chosen.get('trick', '')}\n"
        f"The technique it uses: {technique}.\n"
        "Tool facts you can rely on (never claim a tool does more than this):\n" + "\n".join(f"- {x}" for x in TOOL_FACTS) + "\n\n"
        "Write this idea up as today's column. Keep the pain and the trick specific: name the actual feature or tool, "
        "and put the trick up front, because it is the reason anyone reads this. The reader should finish thinking "
        "'I had no idea you could do that'. Never fall back on vague claims like saving time, streamlining, "
        "efficiency, instantly or seamlessly: say what changes, with a number.\n\n"
        "Return JSON with keys:\n"
        '"title": under 12 words that give away the surprising trick, so the headline alone is worth reading\n'
        '"why": two short sentences: the specific moment it goes wrong today, and what that costs in euros or hours\n'
        '"idea": two or three short sentences giving the idea in plain words, so anyone would get it\n'
        '"how": a list of exactly 4 short steps describing how it works, from what you start with to the result. '
        'Describe what happens; name the actual feature or action where that helps someone build it\n'
        '"need": a list of 2 to 4 things you need to have ready\n'
        '"before": a tiny made-up example of what goes in: 3 or 4 short lines, invented European names\n'
        '"after": what comes out for that example: 3 or 4 short lines. The example must be consistent: dates, totals and statuses must agree with each other and with today\'s date\n'
        '"person": one or two sentences on what a person must still check or decide\n'
        '"watch_out": a list of 2 or 3 specific ways this goes wrong in practice\n'
        '"explain": one sentence the reader could say to a colleague or their boss to explain the idea\n'
        '"effort": exactly one of "an afternoon", "a day or two", "a proper project"\n'
        '"image_prompt": one sentence describing a simple everyday work scene that illustrates the idea',
        4000, 0.7)
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
  <p class="meta" style="margin:8px 0 0">One repetitive job, and how to make your phone or computer do it.</p>
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
    Your documents stay on your own devices. <a href="/archive/use/index.php">See them all</a></footer>
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
    job = list(JOBS)[now.timetuple().tm_yday % len(JOBS)]
    logger.info("Use No. %d — area: %s", len(past) + 1, job)
    if os.getenv("GITHUB_EVENT_NAME") == "schedule" and not dry_run:
        try:  # GitHub's cron often fires hours late, after the Mac mini has already run it: keep the morning edition
            if requests.get(ARCHIVE + f"Use-{now:%Y-%m-%d}.html", timeout=20).status_code == 200:
                logger.info("Today's edition is already published — late scheduled run, nothing to do")
                return
        except requests.RequestException:
            pass

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
