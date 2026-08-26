#!/usr/bin/env python3
"""
Pushes a small lab_status.json to jonestech.xyz so the site's nav shows
real activity from the home lab ("LAB: DAILY BRIEF PUBLISHED · SYNC 2H AGO").

Runs after daily_brief.py via cron. The site degrades gracefully when this
hasn't run recently (falls back to a static label), so nothing depends on
the machine being on.
"""
import ftplib
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# load .env the same way daily_brief.py does
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

FTP_HOST = os.environ["FTP_HOST"]
FTP_USER = os.environ["FTP_USER"]
FTP_PASS = os.environ["FTP_PASS"]
FTP_PATH = os.environ.get("FTP_PATH", "/public_html/")


def main() -> int:
    note = sys.argv[1] if len(sys.argv) > 1 else "DAILY BRIEF PUBLISHED"
    payload = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": note,
        "src": "market_monitor",
    }).encode()

    for cls, secure in ((ftplib.FTP_TLS, True), (ftplib.FTP, False)):
        try:
            ftp = cls(FTP_HOST, timeout=30)
            ftp.login(FTP_USER, FTP_PASS)
            if secure:
                ftp.prot_p()
            ftp.cwd(FTP_PATH)
            ftp.storbinary("STOR lab_status.json", io.BytesIO(payload))
            ftp.quit()
            print("lab_status.json uploaded")
            return 0
        except Exception as e:  # noqa: BLE001 — try the plain-FTP fallback
            print(f"upload via {cls.__name__} failed: {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
