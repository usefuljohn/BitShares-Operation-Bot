---
name: market-strategy
description: "Autonomous Strategy Monitor — Collects DEX state, evaluates trigger conditions, and recommends credit-fund, cascade, or straddle actions"
always: true
triggers:
  - strategy
  - monitor
  - patrol
  - autonomous
  - status check
  - market conditions
---

# Autonomous Strategy Monitor

Periodically collects BitShares DEX state (credit offer balances, prices, SOFR rate)
and evaluates trigger conditions to recommend autonomous actions.

## Skill Location

All files for this skill are located at:
```
/app/nanobot/skills/market-strategy/
```

Key files:
- `strategy_monitor.py` — Main state collector and rule evaluator
- `strategy_rules.json` — Configurable thresholds and trigger conditions
- `strategy_state.json` — Last-run state snapshot (auto-generated, used for delta comparison)

## Usage

```bash
cd /app/nanobot/skills/market-strategy

# Full JSON report (for agent/heartbeat consumption)
python3 strategy_monitor.py --json --quiet

# Human-readable summary
python3 strategy_monitor.py
```

## How It Works

1. **Refreshes** `recent_price_index.json` via the market-intel `price_index_manager` (single source of truth for all prices)
2. **Fetches** live SOFR rate from Pyth Network
3. **Queries** credit offer balances and account state from BitShares RPC
4. **Loads** the previous snapshot from `strategy_state.json`
5. **Evaluates** trigger conditions from `strategy_rules.json`
6. **Writes** updated snapshot for next comparison
7. **Outputs** a report with `actions_triggered` array

## Trigger Conditions

### Credit-Fund
| Trigger | Condition |
|---|---|
| Offer depleted | Any monitored offer balance < min_deal_amount |
| SOFR drift | SOFR changed >0.1% (absolute) from last run |
| BTC price movement | BTC/USD moved >5% from last snapshot |
| BTS price movement | BTS/USD moved >5% from last snapshot |

### Cascade
| Trigger | Condition |
|---|---|
| Price threshold | BTS market price ≤ configured target_price |

### Straddle
| Trigger | Condition |
|---|---|
| BTC movement | BTC/USD moved >5% from last snapshot |
| XRP movement | XRP/USD moved >5% from last snapshot |
| XAUT movement | XAUT/USD moved >5% from last snapshot |

## Heartbeat Integration

This skill is designed to run as a **HEARTBEAT.md** task. The heartbeat reads the
`actions_triggered` array and dispatches to the appropriate sub-agent:
- `credit_fund` → Credit Funder sub-agent runs `liquidityengine.py`
- `cascade` → Credit Funder sub-agent runs `cascade.py`
- `straddle_refresh` → DEX Trader / Market Analyst runs `straddle.py`

All actions generate `.json` transaction bundles by default. Deeplinks available upon request.
