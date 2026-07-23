# Heartbeat Tasks

<!--
This file is checked periodically by your nanobot agent. When nanobot gateway starts with gateway.heartbeat.enabled=true, it automatically registers a protected heartbeat cron job that reads this file.

If this file has no tasks (only headers and comments), the agent will skip it. Completed tasks should be deleted, not kept — heartbeat only reads "Active Tasks".
-->

## Active Tasks

<!-- Add your periodic tasks below this line -->

- Run the strategy monitor: `cd /app/nanobot/skills/market-strategy && python3 strategy_monitor.py --json --quiet`. Parse the JSON output and review `actions_triggered`. For each triggered action:
  - **credit_fund**: Run `cd /app/nanobot/skills/dex-credit && python liquidityengine.py --account <account> --source-mode default_source --no-notify` (if trigger is `sofr_drift`, also run `python sofr_rate_calculator.py --json` and include the computed fee_rate via `--fee-rate <rate>`)
  - **straddle_refresh**: Run `cd /app/nanobot/skills/dex-straddle && python3 straddle.py --account <account> --market <market> --spread <spread_pct> --size <size>` for each market listed in the action. For fuel-capable markets (e.g. `BTWTY.BTC/XBTSX.A`), also pass `--fuel-offer <offer_id> --fuel-lp <lp_id>` from the action's `fuel_config` if present.
  - **cascade**: Run `cd /app/nanobot/skills/dex-leverage && python3 cascade.py --account <account> --output-dir /home/nanobot/.bob/workspace`
  - **ratio_arb**: Run `cd /app/nanobot/skills/dex-arb && python3 ratio_matcher.py --account <account>`
  - Deliver a summary of all generated `.json` file paths to the user. Files are written to both `~/.bob/workspace/pending_tx/` and `~/Desktop/BOB-pending/`. If `first_run` is true, report the baseline snapshot was established.
