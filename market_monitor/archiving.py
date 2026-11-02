"""
Shared archiving for the daily pages: a link to past editions on every page, a dated copy of each
edition, an archive page per series, and one hub page at /archive/ listing every series.

    html = archiving.add_link(html, "signal")        # before writing the page
    archiving.publish("signal", local_path)          # after the live page is uploaded
"""

import ftplib
import io
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
HERE = Path(__file__).parent

# folder: (name shown to readers, live page, prefix of the dated copies)
SERIES = {
    "madworld": ("MAD! World", "MadWorld.html", "MadWorld"),
    "nabokov": ("The Daily Nabokov", "Nabokov.html", "Nabokov"),
    "fork": ("The Fork", "Fork.html", "Fork"),
    "use": ("A Use a Day", "Use.html", "Use"),
    "signal": ("Signal", "Signal.html", "Signal"),
    "aiart": ("Life in 2050", "AiArt.html", "AiArt"),
    "aiworld": ("AI World", "AIWorld.html", "AIWorld"),
    "brief": ("Daily Brief", "daily.html", "Brief"),
}
# These four have their own hand-styled archive pages; the rest use the shared one.
CUSTOM_INDEX = {"madworld", "nabokov", "fork", "use"}

LINK_MARK = "data-archive-link"


def add_link(html: str, series: str) -> str:
    """Put a small 'Past editions · All archives' line at the bottom of the page, once."""
    if LINK_MARK in html:
        return html
    snippet = (f'<p {LINK_MARK} style="text-align:center;margin:28px 0 36px;font:14px/1.5 -apple-system,'
               f'BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;opacity:.8">'
               f'<a href="/archive/{series}/index.php" style="color:inherit">Past editions of {SERIES[series][0]}</a>'
               f' &nbsp;·&nbsp; <a href="/archive/index.php" style="color:inherit">All archives</a></p>\n')
    i = html.rfind("</body>")
    return html[:i] + snippet + html[i:] if i >= 0 else html + snippet


def _connect():
    host, user, pwd = os.getenv("FTP_HOST"), os.getenv("FTP_USER"), os.getenv("FTP_PASS")
    if not all([host, user, pwd]):
        return None, None
    try:
        ftp = ftplib.FTP_TLS(host, timeout=60); ftp.login(user, pwd); ftp.prot_p()
    except Exception:
        ftp = ftplib.FTP(host, timeout=60); ftp.login(user, pwd)
    return ftp, os.getenv("FTP_PATH", "/public_html/").rstrip("/")


def _cd(ftp, path):
    cur = ""
    for part in [p for p in path.split("/") if p]:
        cur += "/" + part
        try:
            ftp.cwd(cur)
        except ftplib.error_perm:
            ftp.mkd(cur); ftp.cwd(cur)


def _put(ftp, name: str, data: bytes):
    ftp.storbinary(f"STOR {name}", io.BytesIO(data))


def install_indexes(ftp, base: str, series: str):
    """The series' archive page (shared template unless it has its own) and the hub page."""
    if series not in CUSTOM_INDEX:
        _cd(ftp, f"{base}/archive/{series}")
        _put(ftp, "index.php", (HERE / "archive_series.php").read_bytes())
    _cd(ftp, f"{base}/archive")
    _put(ftp, "index.php", (HERE / "archive_hub.php").read_bytes())


def publish(series: str, local_path: Path, copy: bool = True):
    """Upload today's dated copy (unless the script already does) and refresh the archive pages."""
    ftp, base = _connect()
    if not ftp:
        logger.warning("FTP credentials not set — archive not updated")
        return
    try:
        if copy:
            _cd(ftp, f"{base}/archive/{series}")
            name = f"{SERIES[series][2]}-{datetime.now():%Y-%m-%d}.html"
            _put(ftp, name, Path(local_path).read_bytes())
            logger.info("Archived https://jonestech.xyz/archive/%s/%s", series, name)
        install_indexes(ftp, base, series)
    except Exception as e:
        logger.warning("Archive update failed: %s", e)
    finally:
        try:
            ftp.quit()
        except Exception:
            pass
