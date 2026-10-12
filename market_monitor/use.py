"""
A Use a Day — one practical thing to do with an AI model, the exact prompt,
and a small free model that can do it offline. The day's prompt is actually run
on that model through a local Ollama, and its unedited reply is printed.

Usage:
    python use.py
    python use.py --dry-run   # build locally, no FTP upload
"""

import argparse
import html
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import requests

from madworld import _ftp_connect, _ftp_mkdirs, generate_image_b64, groq

logger = logging.getLogger(__name__)

OUT_DIR = Path(os.getenv("USE_OUT", "/tmp/use"))
ARCHIVE = "https://jonestech.xyz/archive/use/"
OLLAMA = os.getenv("OLLAMA_HOST", "http://localhost:11434")
PLACEHOLDER = "[YOUR TEXT]"

# Fixed, verified facts about the model the page recommends and the daily job tests on.
TIERS = {
    "small": {"name": "Gemma 3", "tag": "gemma3:4b", "size": "3.4 GB", "runs_on": "most laptops from the last few years"},
}

CATEGORIES = ["subcontract agreements", "tender documents and invitations to bid", "variations and change orders",
              "delay notices and extension-of-time claims", "payment applications and valuations",
              "specifications and scope of works", "supplier and subcontractor quotes",
              "method statements and risk assessments", "site diaries and daily reports",
              "meeting minutes and action lists", "long email chains with a client or designer",
              "requests for information (RFIs) and their answers", "defect and snag lists",
              "inspection and safety reports", "programme narratives and progress reports",
              "handover, warranty and maintenance documents"]

ART_STYLE = ("vintage construction-manual illustration, two-colour risograph print in teal and orange on cream paper, "
             "clean isometric line drawing, no text, no letters")


def past_titles(today: str) -> list[str]:
    """Titles of earlier editions. Today's own file is left out so a re-run replaces it and keeps its number."""
    try:
        page = requests.get(ARCHIVE + "index.php", timeout=20).content.decode("utf-8")
        rows = re.findall(r'href="(Use-[\d-]+\.html)".*?class="t">(.*?)</div>', page, re.S)
        return [html.unescape(t) for f, t in reversed(rows) if today not in f]
    except Exception as e:
        logger.warning("Could not read archive (%s) — assuming no past editions", e)
        return []


def write_use(category: str, done: list[str]) -> dict | None:
    avoid = "\n".join(f"- {t}" for t in done[-80:]) or "(none yet)"
    resp = groq.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": (
                "You write a daily column for people who work in construction in Europe: site managers, small "
                "contractors, subcontractors, estimators and project engineers. They know building thoroughly "
                "and are NOT comfortable with technology. Each column is one genuinely useful thing to do with "
                "an AI assistant running privately on their own computer, because project documents are "
                "confidential and cannot be uploaded to an online service. Write like a sharp colleague "
                "explaining over coffee: short sentences, plain words, proper construction terms. Call it "
                "'the AI', never 'the model' or 'LLM'. Never use these words: prompt, model, offline, "
                "parameters, tokens, output, input, generate, hallucinate, placeholder, data. European "
                "setting: euros, metric units, dates as day-month-year. Do not name or quote any law, "
                "regulation or standard contract clause number. Be honest about what the AI gets wrong. "
                "Return ONLY valid JSON."
            )},
            {"role": "user", "content": (
                f"Today's kind of document: {category}.\n"
                f"Already covered, do not repeat or closely resemble:\n{avoid}\n\n"
                "Pick one specific thing the AI can do with that kind of document that most people on a "
                "building project have NO IDEA is possible. The reader should think 'that would have saved me "
                "last month'. It must protect money, time or their position in a dispute: catching a risk "
                "before signing, finding what is missing, lining up evidence, spotting a contradiction, or "
                "preparing a firm reply. The person pastes in text from the document and the AI does what a "
                "careful commercial manager would do with it.\n"
                "The level to aim for (do not copy these, invent a fresh one):\n"
                "- Find every deadline in a subcontract that you could lose money by missing\n"
                "- Check a subcontractor's quote against the scope and list what they have left out\n"
                "- Pull the dated facts out of a site diary to support a delay claim\n"
                "- Find where two answers to the same question contradict each other\n"
                "- Turn rambling meeting minutes into who owes what by when, with the exact words quoted\n"
                "- Read a variation instruction and list what is unclear before you price it\n"
                "REJECT anything a person could do themselves in two minutes: plain summaries, tidying text, "
                "simple lists. It must not need the internet, current prices, drawings or exact sums. Never "
                "present the AI as a substitute for a lawyer, engineer or quantity surveyor: it helps the "
                "reader find things and prepare, and a person checks the result.\n\n"
                "Return JSON with keys:\n"
                '"title": the task as a short instruction, under 12 words, naming the document and the payoff\n'
                '"why": two short sentences: the problem this causes on real projects, and what this gets them\n'
                f'"prompt": the exact words to paste to the AI. Make it a GOOD request, the kind most people '
                f"never think to write: tell the AI who to act as, exactly what to look for, to quote the exact "
                f"words it is relying on, and to say plainly when something is not in the text. Plain English. "
                f'It must contain {PLACEHOLDER} exactly once where the person\'s own text goes\n'
                '"trick": one or two short sentences explaining the one thing in those words that makes the '
                'answer much better, so the reader learns something they can reuse. It must describe '
                'something the words above really say (for example the role given, the instruction to quote, '
                'or the instruction to say when nothing is found). Do not describe a technique they do not use\n'
                f'"example_input": a realistic 90-150 word extract of that kind of document, as someone would '
                f"paste in place of {PLACEHOLDER}: made up, European, with invented company names, and "
                f"containing the kind of problem the task is meant to find\n"
                '"steps": 3 short steps for what to do with the answer once you have it, including what to '
                'check against the full document and who should see it. Do not explain how to copy and paste\n'
                '"watch_out": 2 or 3 specific mistakes the AI tends to make on this particular task, in plain words\n'
                '"privacy": one short sentence on why this particular kind of document should stay on your own computer\n'
                '"image_prompt": one sentence describing a simple construction-site or site-office scene that illustrates the task'
            )},
        ],
        temperature=0.8,
        max_tokens=2800,
    )
    content = resp.choices[0].message.content or ""
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        logger.error("No JSON in Groq response: %s", content[:300])
        return None
    d = json.loads(m.group(0))
    # The writer sometimes double-escapes line breaks, leaving a literal backslash-n in the text.
    for k in ("prompt", "example_input"):
        if isinstance(d.get(k), str):
            d[k] = d[k].replace("\\n", "\n").strip()
    if d.get("prompt", "").count(PLACEHOLDER) != 1 or not d.get("example_input") or not d.get("title"):
        logger.error("Use failed validation (placeholder count %s)", d.get("prompt", "").count(PLACEHOLDER))
        return None
    if d.get("tier") not in TIERS:
        d["tier"] = "small"
    return d


def run_on_model(tag: str, prompt: str) -> tuple[str, float] | None:
    """Run the prompt on the recommended model via Ollama. Returns (reply, seconds), or None if unavailable."""
    try:
        requests.get(OLLAMA + "/api/tags", timeout=5).raise_for_status()
    except Exception:
        logger.warning("Ollama is not running — the page will have no sample answer")
        return None
    try:
        subprocess.run(["ollama", "pull", tag], check=True, timeout=900, capture_output=True)
        t0 = time.time()
        r = requests.post(OLLAMA + "/api/generate", timeout=600, json={
            "model": tag, "prompt": prompt, "stream": False, "options": {"temperature": 0.3, "num_predict": 450}})
        r.raise_for_status()
        reply = r.json().get("response", "").strip()
        return (reply, time.time() - t0) if reply else None
    except Exception as e:
        logger.error("Model run failed: %s", e)
        return None


def build_html(d: dict, number: int, date_str: str, image: str, sample: tuple[str, float] | None) -> str:
    e = html.escape
    tier = TIERS[d["tier"]]
    steps = "".join(f"<li>{e(s)}</li>" for s in d["steps"])
    watch = "".join(f"<li>{e(s)}</li>" for s in d["watch_out"])
    img = f'<img class="art" src="{image}" alt="">' if image else ""
    sample_html = ""
    if sample:
        sample_html = f"""
  <section>
    <h3>We tried it. Here is what the AI said</h3>
    <p class="note">We used a made-up example and the free AI named above, running on an ordinary computer. This is its answer, exactly as it came back.</p>
    <details><summary>See the example we used</summary><div class="box plain">{e(d["example_input"])}</div></details>
    <div class="box reply">{e(sample[0])}</div>
  </section>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
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
  .mast span {{ font-size:13px; color:var(--dim); }}
  .no {{ font:700 13px 'Space Grotesk', sans-serif; letter-spacing:.14em; color:var(--orange); text-transform:uppercase; margin:26px 0 4px; }}
  h1 {{ font:700 clamp(30px,7vw,44px)/1.08 'Space Grotesk', sans-serif; margin:0 0 14px; letter-spacing:-.02em; }}
  .why {{ font-size:20px; margin:0 0 22px; }}
  .art {{ width:100%; display:block; border:1px solid var(--rule); margin:0 0 26px; }}
  h3 {{ font:700 13px 'Space Grotesk', sans-serif; letter-spacing:.14em; text-transform:uppercase; color:var(--teal); margin:30px 0 8px; }}
  .box {{ background:var(--box); border:1px solid var(--rule); border-left:4px solid var(--teal); padding:14px 16px;
         font:14.5px/1.55 'JetBrains Mono', ui-monospace, monospace; white-space:pre-wrap; overflow-wrap:anywhere; }}
  .box.plain, .box.reply {{ font:16px/1.55 'Source Serif 4', Georgia, serif; }}
  .box.reply {{ border-left-color:var(--orange); }}
  .copy {{ margin-top:8px; background:var(--teal); color:var(--bg); border:0; border-radius:4px; padding:8px 16px;
          font:700 13px 'Space Grotesk', sans-serif; letter-spacing:.06em; cursor:pointer; }}
  .note {{ color:var(--dim); font-size:15px; font-style:italic; margin:0 0 10px; }}
  details {{ margin:0 0 10px; }} summary {{ cursor:pointer; color:var(--teal); font-size:15px; margin-bottom:8px; }}
  ol, ul {{ margin:0; padding-left:22px; }} li {{ margin:6px 0; }}
  .warn {{ border:1px solid var(--orange); padding:4px 16px 10px; }}
  .warn h3 {{ color:var(--orange); margin-top:14px; }}
  .run {{ display:grid; gap:6px; }}
  .meta {{ color:var(--dim); font-size:15px; }}
  footer {{ margin-top:44px; padding-top:14px; border-top:1px solid var(--rule); color:var(--dim); font-size:14px; }}
  footer a {{ color:var(--teal); }}
</style>
</head>
<body>
<main>
  <div class="mast"><b>A Use a Day</b><span>{e(date_str)}</span></div>
  <p class="meta" style="margin:8px 0 0">One useful thing to do with AI on a building project, without sending your documents anywhere.</p>
  <div class="no">No. {number} · {e(d.get("category", ""))}</div>
  <h1>{e(d["title"])}</h1>
  <p class="why">{e(d["why"])}</p>
  {img}
  <section>
    <h3>What to say to the AI</h3>
    <div class="box plain" id="prompt">{e(d["prompt"])}</div>
    <button class="copy" data-copy="prompt">Copy these words</button>
    <p class="meta">Where it says {e(PLACEHOLDER)}, paste in the text from your own document. {e(d["privacy"])}</p>
  </section>
  <section>
    <h3>Why these words work</h3>
    <p>{e(d.get("trick", ""))}</p>
  </section>
  <section>
    <h3>Where to run it: on your own computer</h3>
    <p>Project documents are confidential, so do not paste them into an online AI such as ChatGPT unless your company has agreed to it. A free app called LM Studio runs an AI on your own computer instead. After the first download it needs no internet, and nothing you paste leaves the machine.</p>
    <details><summary>Set it up once (about 15 minutes)</summary>
      <div class="run">
        <div>1. Go to lmstudio.ai, download LM Studio and open it.</div>
        <div>2. Use its search to find <b>{e(tier["name"])}</b> and download it ({e(tier["size"])}, once only).</div>
        <div>3. Open the chat, choose that AI at the top, paste the words above and press Return.</div>
      </div>
      <p class="meta">{e(tier["name"])} works on {e(tier["runs_on"])}. If your computer has 16 GB of memory or more, a larger one such as Gemma 3 12B reads long documents more carefully. For a long document, paste one section at a time.</p>
    </details>
  </section>
  {sample_html}
  <section>
    <h3>What to do with the answer</h3>
    <ol>{steps}</ol>
  </section>
  <section class="warn">
    <h3>Watch out</h3>
    <ul>{watch}</ul>
  </section>
  <footer>Written by an AI and tried out on a second one. The example is made up. Have a person check anything that matters.
    <a href="/archive/use/index.php">See them all</a></footer>
</main>
<script>
  document.querySelectorAll('.copy').forEach(b => b.onclick = async () => {{
    await navigator.clipboard.writeText(document.getElementById(b.dataset.copy).textContent);
    const t = b.textContent; b.textContent = 'Copied'; setTimeout(() => b.textContent = t, 1500);
  }});
</script>
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


def main(dry_run: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    done = past_titles(f"{now:%Y-%m-%d}")
    category = CATEGORIES[now.timetuple().tm_yday % len(CATEGORIES)]
    logger.info("Use No. %d — area: %s", len(done) + 1, category)

    d = None
    for attempt in range(3):
        try:
            d = write_use(category, done)
        except Exception as e:
            logger.error("Groq attempt %d failed: %s", attempt + 1, e)
        if d:
            break
        time.sleep(5)
    if not d:
        logger.error("No use written — aborting, live page untouched")
        return
    d["category"] = category
    logger.info("Use: %s", d["title"])

    sample = run_on_model(TIERS[d["tier"]]["tag"], d["prompt"].replace(PLACEHOLDER, d["example_input"]))
    logger.info("Sample answer: %s", f"{len(sample[0])} chars in {sample[1]:.0f}s" if sample else "none")

    image = generate_image_b64(d.get("image_prompt", ""), style=ART_STYLE)
    page = build_html(d, len(done) + 1, now.strftime("%A %-d %B %Y"), image, sample)
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
    main(ap.parse_args().dry_run)
