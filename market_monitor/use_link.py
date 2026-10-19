"""
Add a "Try it" link to an A Use a Day edition that has since been built for real.

Usage:
    python use_link.py 2026-10-21 /tool.html
    python use_link.py 2026-10-21 /tool.html --label "Open it on your phone" --credit "Built and tested on an iPhone."

Downloads that day's archived page, puts the button under "The idea" (replacing any earlier one),
optionally replaces the footer note, and uploads it again. If it is today's edition, the live
page is updated too.
"""

import argparse
import html
import io
import os
import re
import sys
from datetime import datetime

from madworld import _ftp_connect

TRY = re.compile(r'(<h3>The idea</h3>\s*<p>.*?</p>)(\s*<p><a class="try"[^>]*>.*?</a></p>)?', re.S)
FOOTER = re.compile(r'(<footer>)(.*?)(\s*Your documents stay)', re.S)


def main(date: str, url: str, label: str, credit: str | None, dry_run: bool):
    host, user, pwd = os.getenv("FTP_HOST"), os.getenv("FTP_USER"), os.getenv("FTP_PASS")
    base = os.getenv("FTP_PATH", "/public_html/").rstrip("/")
    if not all([host, user, pwd]):
        sys.exit("FTP_HOST, FTP_USER and FTP_PASS must be set")
    name = f"Use-{date}.html"
    ftp = _ftp_connect(host, user, pwd)
    ftp.cwd(base + "/archive/use")
    buf = io.BytesIO()
    ftp.retrbinary(f"RETR {name}", buf.write)
    page = buf.getvalue().decode("utf-8")

    e = html.escape
    button = f'\n    <p><a class="try" href="{e(url)}">{e(label)}</a></p>'
    page, n = TRY.subn(lambda m: m.group(1) + button, page, count=1)
    if not n:
        sys.exit(f"Couldn't find 'The idea' section in {name}")
    if credit:
        page = FOOTER.sub(lambda m: m.group(1) + e(credit) + m.group(3), page, count=1)

    if dry_run:
        print(page)
        return
    ftp.storbinary(f"STOR {name}", io.BytesIO(page.encode("utf-8")))
    print(f"Updated https://jonestech.xyz/archive/use/{name}")
    if date == f"{datetime.now():%Y-%m-%d}":
        ftp.cwd(base)
        ftp.storbinary("STOR Use.html", io.BytesIO(page.encode("utf-8")))
        print("Updated https://jonestech.xyz/Use.html (today's edition)")
    ftp.quit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="the edition's date, YYYY-MM-DD")
    ap.add_argument("url", help="where the built tool lives, e.g. /tool.html")
    ap.add_argument("--label", default="Try the working version")
    ap.add_argument("--credit", help="new footer note, e.g. 'Built and tested on an iPhone.'")
    ap.add_argument("--dry-run", action="store_true", help="print the page instead of uploading")
    a = ap.parse_args()
    main(a.date, a.url, a.label, a.credit, a.dry_run)
