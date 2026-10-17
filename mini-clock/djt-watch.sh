#!/bin/bash
# Starts the DJT Truth Social watcher on GitHub. launchd runs this every 15 minutes, because
# GitHub's own 15-minute timer only managed about 6 runs a day. Logs only problems.
GH="$HOME/bin/gh"; REPO=jonestechxyz/market-monitor
busy=$("$GH" run list -R $REPO --workflow=djt_watcher.yml --limit 3 --json status \
       -q '[.[] | select(.status!="completed")] | length')
if ! [[ "$busy" =~ ^[0-9]+$ ]]; then echo "$(date) ERROR checking djt_watcher"; exit 0; fi
# Skip if the last one is still queued or running.
[ "$busy" = "0" ] && { "$GH" workflow run djt_watcher.yml -R $REPO >/dev/null || echo "$(date) ERROR starting djt_watcher"; }
