# Heartbeat Tasks

<!--
This file is checked periodically by your nanobot agent. When nanobot gateway starts with gateway.heartbeat.enabled=true, it automatically registers a protected heartbeat cron job that reads this file.

If this file has no tasks (only headers and comments), the agent will skip it. Completed tasks should be deleted, not kept — heartbeat only reads "Active Tasks".
-->

## Active Tasks

<!-- Add your periodic tasks below this line -->

- Run the strategy monitor: `python3 nanobot/skills/market-strategy/strategy_monitor.py --json --quiet`. Parse the JSON output and review `actions_triggered`. For each triggered action:
  - **ratio_arb**: Run `python3 nanobot/skills/dex-arb/ratio_matcher.py --account <account>`
  - **price_index_update**: Refresh DEX price index via `market-intel` manager.
  - Deliver a summary of all generated execution steps to the user.
