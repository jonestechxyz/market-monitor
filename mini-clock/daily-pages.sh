#!/bin/bash
# The one clock for the jonestech daily pages (GitHub's own timers are switched off).
# launchd runs this at 05:00, 09:40 and 13:00 Copenhagen time. It starts every daily that
# hasn't succeeded (and isn't running) today, 5 minutes apart so they don't all hit Groq's
# per-minute limit together. The later runs only catch up anything that failed.
GH="$HOME/bin/gh"; REPO=jonestechxyz/market-monitor; TODAY=$(date -u +%F)
WORKFLOWS="aiworld.yml use.yml signal.yml nabokov.yml aiart.yml fork.yml madworld.yml"
# The market monitor is weekdays only, and goes first so it's out before the EU open.
[ "$(date +%u)" -le 5 ] && WORKFLOWS="market_monitor.yml $WORKFLOWS"
started=0
for wf in $WORKFLOWS; do
  ok=$("$GH" run list -R $REPO --workflow=$wf --limit 5 --json createdAt,status,conclusion \
       -q "[.[] | select(.createdAt|startswith(\"$TODAY\")) | select(.conclusion==\"success\" or .status!=\"completed\")] | length")
  if ! [[ "$ok" =~ ^[0-9]+$ ]]; then echo "$(date) ERROR checking $wf"; continue; fi
  if [ "$ok" = "0" ]; then
    [ "$started" -gt 0 ] && sleep 300
    "$GH" workflow run $wf -R $REPO && echo "$(date) triggered $wf" && started=$((started + 1))
  else echo "$(date) $wf already done"; fi
done
