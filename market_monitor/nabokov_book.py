"""
Build a PDF book from every archived edition of The Daily Nabokov.

Usage:
    python nabokov_book.py                 # writes ../books/The-Daily-Nabokov.pdf
    python nabokov_book.py --out some.pdf
"""

import argparse
import base64
import html
import io
import re
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image as PILImage
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer)
from reportlab.platypus.tableofcontents import TableOfContents

ARCHIVE = "https://jonestech.xyz/archive/nabokov/"
FONTS = Path("/System/Library/Fonts/Supplemental")
PAGE = (6 * inch, 9 * inch)
INK, DIM, ACCENT, PAPER = HexColor("#2b2118"), HexColor("#7a6a55"), HexColor("#6b2d2d"), HexColor("#f4ecdc")

pdfmetrics.registerFont(TTFont("Serif", FONTS / "Georgia.ttf"))
pdfmetrics.registerFont(TTFont("Serif-Italic", FONTS / "Georgia Italic.ttf"))
pdfmetrics.registerFont(TTFont("Serif-Bold", FONTS / "Georgia Bold.ttf"))
pdfmetrics.registerFontFamily("Serif", normal="Serif", italic="Serif-Italic", bold="Serif-Bold", boldItalic="Serif-Bold")

S = {
    "body": ParagraphStyle("body", fontName="Serif", fontSize=10.5, leading=15.5, textColor=INK,
                           alignment=TA_JUSTIFY, firstLineIndent=14),
    "first": ParagraphStyle("first", fontName="Serif", fontSize=10.5, leading=15.5, textColor=INK, alignment=TA_JUSTIFY),
    "title": ParagraphStyle("title", fontName="Serif-Bold", fontSize=17, leading=21, textColor=INK, spaceAfter=4),
    "date": ParagraphStyle("date", fontName="Serif-Italic", fontSize=9, leading=12, textColor=DIM, spaceAfter=2),
    "source": ParagraphStyle("source", fontName="Serif-Italic", fontSize=8.5, leading=12, textColor=DIM, spaceAfter=12),
    "specimen": ParagraphStyle("specimen", fontName="Serif-Italic", fontSize=9, leading=12, textColor=DIM,
                               alignment=TA_CENTER, spaceBefore=5, spaceAfter=14),
    "center": ParagraphStyle("center", fontName="Serif", fontSize=10.5, leading=16, textColor=INK, alignment=TA_CENTER),
    "small": ParagraphStyle("small", fontName="Serif-Italic", fontSize=9, leading=14, textColor=DIM, alignment=TA_CENTER),
    "h": ParagraphStyle("h", fontName="Serif-Bold", fontSize=14, leading=18, textColor=INK, alignment=TA_CENTER, spaceAfter=18),
    "toc": ParagraphStyle("toc", fontName="Serif", fontSize=10, leading=17, textColor=INK),
}


def clean(text: str) -> str:
    """HTML text -> reportlab markup: escape, turn *x* into italics, swap glyphs Georgia lacks."""
    t = html.unescape(text).replace("‑", "-").replace(" ", " ").strip()
    t = html.escape(t, quote=False)
    return re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", t)


def fetch_editions() -> list[dict]:
    # The server sends no charset header, so decode as UTF-8 explicitly.
    index = requests.get(ARCHIVE + "index.php", timeout=30).content.decode("utf-8")
    editions = []
    for name in sorted(set(re.findall(r"Nabokov-\d{4}-\d{2}-\d{2}\.html", index))):
        page = requests.get(ARCHIVE + name, timeout=60).content.decode("utf-8")
        main = re.search(r"<main>(.*?)<footer>", page, re.S).group(1)
        img = re.search(r'<img class="plate" src="data:image/[a-z]+;base64,([^"]+)"', main)
        editions.append({
            "date": datetime.strptime(name[8:18], "%Y-%m-%d"),
            "title": clean(re.search(r"<h2>(.*?)</h2>", main, re.S).group(1)),
            "headline": clean(re.search(r'class="source">.*?<b>(.*?)</b>', main, re.S).group(1)),
            "specimen": clean(re.search(r'class="specimen">(.*?)</div>', main, re.S).group(1)),
            "paras": [clean(p) for p in re.findall(r"<p>(.*?)</p>", main, re.S)],
            "image": base64.b64decode(img.group(1)) if img else None,
        })
        print("fetched", name)
    return editions


def plate(data: bytes, width: float) -> Image:
    im = PILImage.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((1100, 1100))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    buf.seek(0)
    return Image(buf, width=width, height=width * im.height / im.width)


class Book(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if getattr(flowable, "toc_text", None):
            self.notify("TOCEntry", (0, flowable.toc_text, self.page))


def build(editions: list[dict], out: Path):
    w, h = PAGE
    margin = 0.75 * inch
    frame = Frame(margin, margin, w - 2 * margin, h - 2 * margin, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def paper(c, _doc):
        c.setFillColor(PAPER)
        c.rect(0, 0, w, h, stroke=0, fill=1)

    def numbered(c, doc):
        paper(c, doc)
        c.setFont("Serif-Italic", 8.5)
        c.setFillColor(DIM)
        c.drawCentredString(w / 2, 0.45 * inch, str(doc.page))

    def cover(c, doc):
        paper(c, doc)
        c.setStrokeColor(ACCENT)
        c.setLineWidth(0.8)
        c.rect(0.4 * inch, 0.4 * inch, w - 0.8 * inch, h - 0.8 * inch)
        c.rect(0.46 * inch, 0.46 * inch, w - 0.92 * inch, h - 0.92 * inch)

    first, last = editions[0]["date"], editions[-1]["date"]
    span = f"{first:%-d %B} – {last:%-d %B %Y}" if first != last else f"{first:%-d %B %Y}"
    doc = Book(str(out), pagesize=PAGE, title="The Daily Nabokov", author="jonestech.xyz",
               subject=f"Collected editions, {span}")
    doc.addPageTemplates([PageTemplate("cover", [frame], onPage=cover),
                          PageTemplate("plain", [frame], onPage=paper),
                          PageTemplate("body", [frame], onPage=numbered)])

    story = [Spacer(1, 1.6 * inch)]
    if editions[0]["image"]:
        story.append(plate(editions[0]["image"], 2.6 * inch))
    story += [Spacer(1, 0.45 * inch),
              Paragraph("The Daily Nabokov", ParagraphStyle("ct", fontName="Serif-Bold", fontSize=27, leading=32, textColor=INK, alignment=TA_CENTER)),
              Spacer(1, 10),
              Paragraph("Specimens pinned from the morning papers", S["small"]),
              Spacer(1, 6),
              Paragraph(f"Volume I &nbsp;·&nbsp; {span}", S["small"]),
              NextPageTemplate("plain"), PageBreak(),
              Spacer(1, 2.4 * inch),
              Paragraph("Each morning a machine reads the news, chooses the one headline with the most human "
                        "strangeness in it, and writes about it in the manner of Vladimir Nabokov. A second "
                        "machine paints the specimen plate.", S["center"]),
              Spacer(1, 16),
              Paragraph("These are pastiches, written in admiration. None of the words are his, "
                        "and the details around each headline are invented.", S["small"]),
              Spacer(1, 1.6 * inch),
              Paragraph(f"jonestech.xyz &nbsp;·&nbsp; collected {datetime.now():%-d %B %Y}", S["small"]),
              PageBreak(),
              Paragraph("Contents", S["h"])]
    toc = TableOfContents()
    toc.levelStyles = [S["toc"]]
    story += [toc, NextPageTemplate("body"), PageBreak()]

    for e in editions:
        head = Paragraph(e["title"], S["title"])
        head.toc_text = e["title"]
        if e["image"]:
            story += [plate(e["image"], 3.3 * inch), Paragraph(e["specimen"], S["specimen"])]
        story += [Paragraph(f"{e['date']:%A %-d %B %Y}", S["date"]), head,
                  Paragraph(f"after the headline: {e['headline']}", S["source"])]
        story += [Paragraph(p, S["first" if i == 0 else "body"]) for i, p in enumerate(e["paras"])]
        story.append(PageBreak())

    doc.multiBuild(story)
    print(f"wrote {out} ({len(editions)} editions)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).parent.parent / "books" / "The-Daily-Nabokov.pdf")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    build(fetch_editions(), args.out)
