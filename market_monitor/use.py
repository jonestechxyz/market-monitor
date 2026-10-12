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

# Fixed, verified facts about the models we recommend. The writing model only picks a tier.
TIERS = {
    "small": {"name": "Llama 3.2", "tag": "llama3.2:3b", "size": "2 GB", "runs_on": "any laptop from the last few years"},
    "medium": {"name": "Gemma 3", "tag": "gemma3:4b", "size": "3.4 GB", "runs_on": "most laptops from the last few years"},
}

CATEGORIES = ["money and bills", "work and email", "home and repairs", "cooking and food", "travel",
              "learning something new", "health paperwork (not diagnosis)", "contracts and small print",
              "writing and editing", "job hunting", "family and school", "tech support for yourself",
              "languages", "planning and decisions"]

ART_STYLE = ("vintage instruction-manual illustration, two-colour risograph print in teal and orange on cream paper, "
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
                "You write a daily column for people who are NOT comfortable with technology: a retired "
                "teacher, a busy parent, a shop owner. Each column is one genuinely useful thing to do with "
                "an AI chat assistant. Write the way a friendly newspaper advice column does: short sentences, "
                "everyday words. Call it 'the AI', never 'the model' or 'LLM'. Never use these words: prompt, "
                "model, offline, parameters, tokens, output, input, generate, hallucinate, placeholder, data. "
                "Be honest about what the AI gets wrong. Return ONLY valid JSON."
            )},
            {"role": "user", "content": (
                f"Today's area: {category}.\n"
                f"Already covered, do not repeat or closely resemble:\n{avoid}\n\n"
                "Pick one specific, practical task from ordinary daily life where the person pastes in some "
                "text of their own (a letter, a bill, an email, a recipe, a leaflet, instructions) and the AI "
                "does something useful with it. Nothing about technology, science papers, coding or AI itself. "
                "It must not need the internet, today's news, or exact sums.\n\n"
                "Return JSON with keys:\n"
                '"title": the task as a short instruction, under 10 words, naming the specific everyday thing '
                '(e.g. "Make sense of a confusing letter from the council", not "Summarise a document")\n'
                '"why": two short sentences on how this helps, in everyday words\n'
                f'"prompt": the exact words to paste to the AI, written as a clear plain-English request, '
                f'containing {PLACEHOLDER} exactly once where the person\'s own text goes\n'
                f'"example_input": a realistic 60-120 word everyday example of what someone would paste in '
                f"place of {PLACEHOLDER} (made up, no real people or companies)\n"
                '"steps": 3 short steps for what to do with the answer once you have it. Do not explain how '
                'to copy and paste\n'
                '"watch_out": 2 or 3 specific mistakes the AI tends to make on this task, in everyday words\n'
                '"privacy": one short sentence on what not to paste in (for example account numbers)\n'
                '"tier": "small" for a simple task, "medium" if it needs more careful reasoning\n'
                '"image_prompt": one sentence describing a simple everyday scene that illustrates the task'
            )},
        ],
        temperature=0.8,
        max_tokens=2000,
    )
    content = resp.choices[0].message.content or ""
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        logger.error("No JSON in Groq response: %s", content[:300])
        return None
    d = json.loads(m.group(0))
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
    <p class="note">We used a made-up example and a small free AI. This is its answer, exactly as it came back.</p>
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
  <p class="meta" style="margin:8px 0 0">One practical thing to do with AI, in plain words.</p>
  <div class="no">No. {number} · {e(d.get("category", ""))}</div>
  <h1>{e(d["title"])}</h1>
  <p class="why">{e(d["why"])}</p>
  {img}
  <section>
    <h3>What to say to the AI</h3>
    <div class="box plain" id="prompt">{e(d["prompt"])}</div>
    <button class="copy" data-copy="prompt">Copy these words</button>
    <p class="meta">Where it says {e(PLACEHOLDER)}, paste in your own. {e(d["privacy"])}</p>
  </section>
  <section>
    <h3>Where to paste it</h3>
    <p>Open any AI chat you already use, such as ChatGPT, Claude, Gemini or Copilot. Paste the words above into the message box and send.</p>
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
  <section>
    <h3>Want to keep it private?</h3>
    <p>You can run a free AI on your own computer. It needs no internet once it is set up, and nothing you type is sent anywhere.</p>
    <details><summary>Show me how (about 10 minutes, a little technical)</summary>
      <div class="run">
        <div>1. Go to ollama.com, download the free Ollama app and open it.</div>
        <div>2. Open the app called Terminal (on a Mac, press Command and Space, type Terminal, press Return). On Windows it is called Command Prompt.</div>
        <div>3. Copy this line, paste it in and press Return:</div>
        <div class="box" id="cmd">ollama run {e(tier["tag"])}</div>
        <div><button class="copy" data-copy="cmd">Copy this line</button></div>
        <div>4. Wait for the download ({e(tier["size"])}, once only). When you see <b>&gt;&gt;&gt;</b>, paste the words from the top of this page.</div>
      </div>
      <p class="meta">This uses a free AI called {e(tier["name"])}. It works on {e(tier["runs_on"])}. A free app called LM Studio does the same job with buttons instead of typing.</p>
    </details>
  </section>
  <footer>Written by an AI and tried out on a second one. The example is made up.
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
    logger.info("Use: %s (tier %s)", d["title"], d["tier"])

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
