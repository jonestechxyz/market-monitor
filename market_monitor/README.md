# Asia-EU Market Monitor

A lightweight market monitoring agent that runs every weekday at 06:00 CET, checks
overnight Asian index moves, identifies correlated European stocks, and emails a
formatted briefing with ATR-based entry/stop/target levels.

---

## Project structure

```
market_monitor/
├── fetcher.py          # yfinance data layer
├── detector.py         # mover detection + ATR calculation
├── correlations.py     # hardcoded Asia → EU correlation map
├── formatter.py        # plain-text + JSON briefing builder
├── mailer.py           # Gmail SMTP sender
├── main.py             # orchestrator CLI
├── dashboard.html      # single-file local HTML dashboard
├── briefings/          # auto-created; stores last 5 JSON briefings
└── requirements.txt

.github/
└── workflows/
    └── market_monitor.yml   # GitHub Actions schedule
```

---

## Local setup

### 1. Clone and install

```bash
git clone <your-repo-url>
cd market_monitor
pip install -r requirements.txt
```

### 2. Run a dry-run (no email, no file save)

```bash
python main.py --dry-run
```

Prints the briefing to stdout. Good for testing without credentials.

### 3. Run and save (skip email)

```bash
python main.py --no-email
```

Saves a JSON briefing under `briefings/` and prints the text output.

### 4. Full run (email + save)

Set the required environment variables first (see [Email setup](#email-setup)), then:

```bash
python main.py
```

---

## Email setup

The mailer reads three environment variables:

| Variable        | Description                                             |
|-----------------|---------------------------------------------------------|
| `GMAIL_USER`    | Your Gmail address (e.g. `you@gmail.com`)               |
| `GMAIL_APP_PASS`| A Gmail **App Password** (not your account password)   |
| `BRIEFING_TO`   | Comma-separated recipient addresses                     |

### Generating a Gmail App Password

1. Go to your Google Account → **Security → 2-Step Verification** (must be enabled).
2. Scroll to **App passwords** → create one named "Market Monitor".
3. Copy the 16-character password — you won't see it again.

```bash
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASS="xxxx xxxx xxxx xxxx"
export BRIEFING_TO="you@gmail.com,colleague@example.com"
python main.py
```

---

## GitHub Actions setup

### 1. Add repository secrets

In your repo go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name     | Value                              |
|-----------------|------------------------------------|
| `GMAIL_USER`    | your Gmail address                 |
| `GMAIL_APP_PASS`| your Gmail App Password            |
| `BRIEFING_TO`   | comma-separated recipient list     |

### 2. Push the workflow file

The workflow is at `.github/workflows/market_monitor.yml` and is committed with
the repo. It runs at **05:00 UTC Mon–Fri** (covers both CET 06:00 and CEST 06:00).

You can also trigger it manually from the **Actions** tab → **Asia-EU Market Monitor**
→ **Run workflow**.

### 3. Briefings are committed back automatically

After each run the workflow commits any new JSON files in `market_monitor/briefings/`
back to the repository using the built-in `GITHUB_TOKEN`. This means the HTML
dashboard always has up-to-date data when you serve it locally.

---

## HTML dashboard

Open `dashboard.html` in a browser **via a local server** (not `file://`, because
CORS blocks the JSON fetches):

```bash
# from inside the market_monitor/ directory:
python -m http.server 8743
# then open http://localhost:8743/dashboard.html
```

The dashboard:
- Loads the last 5 briefings from `briefings/*.json`
- Shows Asian movers with price, volume ratio, ATR, session high/low
- Shows EU stocks ranked by estimated impact, with reason and ATR-based entry/stop/target levels
- Falls back to demo data automatically when no briefing files exist (no errors)

---

## Thresholds and tuning

| Parameter             | File              | Default    |
|-----------------------|-------------------|------------|
| Move threshold        | `detector.py`     | 2.5%       |
| Volume spike ratio    | `detector.py`     | 1.5×       |
| ATR period            | `detector.py`     | 14 days    |
| Stop ATR multiplier   | `formatter.py`    | 1.0×       |
| Target ATR multiplier | `formatter.py`    | 2.0×       |
| Briefings retained    | `formatter.py`    | 5          |

---

## Correlation map

`correlations.py` contains a hardcoded map of which EU stocks typically react to
each Asian index move, along with:
- **Reason** — the fundamental link (revenue exposure, dual-listing, supply chain, etc.)
- **Beta estimate** — rough expected EU move per 1% Asian index move

Edit `CORRELATION_MAP` in that file to add, remove, or adjust any entry.
The `EU_WATCHLIST` dict at the top lists all tickers that will be fetched.

---

## Disclaimer

Indicative signals only. Not financial advice. All entry/stop/target levels are
mechanical ATR-based estimates and do not account for macro news, earnings, or
liquidity conditions. Always do your own research before trading.
