#!/usr/bin/env python3
"""Health check for the Mac mini. launchd runs it every 15 minutes.

It checks the memoir apps, Remote Control, the mini's Tailscale name and certificate, and
today's daily pages. It sends a Pushover alert to Jason's phone only when something breaks,
reminds him every 6 hours while it stays broken, and sends "fixed" once it recovers.
Nothing is sent between 23:00 and 07:00; anything still broken goes out after 07:00.

The Pushover keys are read from ~/thechain/market_monitor/.env (PUSHOVER_USER and
PUSHOVER_TOKEN). They are never written in this file, because the repo is public.
Run with --test to send one test alert, or --dry-run to print the checks without sending.
"""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
ENV = HOME / "thechain" / "market_monitor" / ".env"
STATE = HOME / ".health_state.json"
LOG = HOME / "Library" / "Logs" / "health-check.log"
GH = str(HOME / "bin" / "gh")
TS = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
REPO = "jonestechxyz/market-monitor"
NAME = "jasons-mac-mini.tail0333b8.ts.net"
CERT = HOME / "Side hustler1" / "certs" / f"{NAME}.crt"
DAILIES = ["aiworld", "use", "signal", "nabokov", "aiart", "fork", "madworld"]
REMIND_HOURS = 6
QUIET = (23, 7)  # no alerts from 23:00 to 07:00


def run(cmd, timeout=30):
    # The Tailscale command only behaves as a command line when it thinks a shell started it;
    # from launchd it tries to open the app instead. SHLVL is what it looks for.
    env = dict(os.environ, SHLVL=os.environ.get("SHLVL", "1"))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, p.stdout.strip()
    except Exception as e:  # timeouts, missing programs
        return 1, str(e)


def check_memoir():
    problems = {}
    for port, label in ((8443, "Memoir dictation app"), (9443, "Memoir book editor")):
        code, out = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "15",
                         f"https://{NAME}:{port}/"])
        if out != "200":
            problems[f"memoir-{port}"] = f"{label} isn't answering on your phone's address (got {out or 'no reply'})."
    return problems


def check_remote_control():
    code, pid = run(["pgrep", "-f", "claude remote-control --name Website-mini"])
    if code != 0 or not pid:
        return {"rc": "Remote Control (Website-mini) isn't running. Restart it with the commands in ~/rc/README.txt."}
    pid = pid.splitlines()[0]
    code, _ = run(["lsof", "-a", "-p", pid, "-iTCP", "-sTCP:ESTABLISHED"])
    if code != 0:
        # ~/rc/check.sh restarts it after two failed checks, so only report a lasting drop.
        return {"rc": "Remote Control (Website-mini) is running but not connected."}
    return {}


def check_tailscale():
    code, out = run([TS, "status", "--json"])
    try:
        dns = json.loads(out)["Self"]["DNSName"].rstrip(".")
    except Exception:
        return {"tailscale": "Tailscale isn't running on the mini."}
    if dns != NAME:
        return {"tailscale": f"The mini's Tailscale name changed to {dns.split('.')[0]}, so the phone can't find the memoir. Rename it back to jasons-mac-mini."}
    return {}


def check_cert():
    code, out = run(["openssl", "x509", "-enddate", "-noout", "-in", str(CERT)])
    try:
        end = dt.datetime.strptime(out.split("=", 1)[1], "%b %d %H:%M:%S %Y %Z")
    except Exception:
        return {"cert": "Can't read the memoir apps' security certificate."}
    days = (end - dt.datetime.utcnow()).days
    if days < 14:
        return {"cert": f"The memoir certificate runs out in {days} days. Renew it with tailscale cert (see memory) and restart the apps."}
    return {}


def check_dailies(now):
    # Pages start at 05:00 and are all started by 05:35; give them until 07:00.
    if now.hour < 7:
        return {}
    today = dt.datetime.utcnow().strftime("%Y-%m-%d")
    names = DAILIES + (["market_monitor"] if now.isoweekday() <= 5 else [])
    problems = {}
    for wf in names:
        code, out = run([GH, "run", "list", "-R", REPO, f"--workflow={wf}.yml", "--limit", "5",
                         "--json", "createdAt,status,conclusion"])
        if code != 0:
            problems["github"] = "Can't check today's daily pages on GitHub (the mini's gh sign-in may have expired)."
            break
        runs = [r for r in json.loads(out or "[]") if r["createdAt"].startswith(today)]
        if any(r["conclusion"] == "success" or r["status"] != "completed" for r in runs):
            continue
        why = "failed" if runs else "didn't start"
        problems[f"daily-{wf}"] = f"Today's {wf} page {why}. The mini retries at 09:40 and 13:00."
    return problems


def env():
    out = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def push(title, message):
    e = env()
    code, out = run(["curl", "-s", "--max-time", "20",
                     "--form-string", f"token={e['PUSHOVER_TOKEN']}",
                     "--form-string", f"user={e['PUSHOVER_USER']}",
                     "--form-string", f"title={title}",
                     "--form-string", f"message={message}",
                     "https://api.pushover.net/1/messages.json"])
    return code == 0 and '"status":1' in out


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M} {msg}\n")


def main():
    now = dt.datetime.now()
    if "--test" in sys.argv:
        ok = push("Mac mini test", "Health alerts are set up. You'll only hear from me when something breaks.")
        print("sent" if ok else "FAILED")
        return

    problems = {}
    for check in (check_memoir, check_remote_control, check_tailscale, check_cert):
        problems.update(check())
    problems.update(check_dailies(now))

    if "--dry-run" in sys.argv:
        print(json.dumps(problems, indent=1) if problems else "all fine")
        return

    try:
        state = json.loads(STATE.read_text())
    except Exception:
        state = {}
    quiet = now.hour >= QUIET[0] or now.hour < QUIET[1]
    stamp = now.timestamp()

    new = {}
    for key, msg in problems.items():
        last = state.get(key, {}).get("alerted")
        due = last is None or stamp - last > REMIND_HOURS * 3600
        new[key] = {"msg": msg, "alerted": last}
        if due and not quiet:
            new[key]["send"] = True
    fixed = [state[k]["msg"] for k in state if k not in problems and state[k].get("alerted")]

    to_send = [k for k in new if new[k].pop("send", False)]
    if to_send:
        body = "\n".join("- " + new[k]["msg"] for k in to_send)
        if push(f"Mac mini: {len(to_send)} problem{'s' if len(to_send) > 1 else ''}", body):
            for k in to_send:
                new[k]["alerted"] = stamp
            log("alerted: " + ", ".join(to_send))
        else:
            log("ERROR sending alert for: " + ", ".join(to_send))
    if fixed and not quiet:
        if push("Mac mini: fixed", "\n".join("- " + m for m in fixed)):
            log(f"fixed: {len(fixed)}")
    elif fixed:
        # Keep them until the morning so the "fixed" message still goes out.
        for k in state:
            if k not in problems and state[k].get("alerted"):
                new[k] = state[k]
    STATE.write_text(json.dumps(new))


if __name__ == "__main__":
    main()
