---
name: dex-router
description: Find optimal trading paths between BitShares assets via Liquidity Pools.
metadata: {"nanobot":{"emoji":"🔀","requires":{"bins":["python3"]}}}
---

# BitShares Liquidity Pool Router

This skill provides a tool to find the most efficient multi-hop trading path between any two BitShares assets using Liquidity Pools.

## Usage Context
- **Explicit Requests:** Use this skill when a user asks to "find a path", "route a trade", or "exchange" specific assets via liquidity pools.
- **Implicit Requirements:** Use this skill when a user wants to swap assets where a direct liquidity pool does not exist (e.g., trading between two niche assets that both have pools with BTS but not each other).
- **Fallback:** If a direct trade is not possible or depth is insufficient, use this to find an alternative multi-hop route.

## Output Requirements
When a path is found, the agent should present the result and offer to generate a transaction. The final output for the user should include:
1.  **Transaction JSON:** A structured BitShares transaction object for the exchange.
2.  **Deeplink:** A `rawbitshares://` prefixed link for signing the transaction.
3.  **Notification:** A placeholder for sending the transaction details to a Telegram bot.

*Note: Use `rawbitshares://tx/PLACEHOLDER` for the deeplink and `[TELEGRAM_NOTIFICATION_PENDING]` for the notification status.*

## Requirements
...

The tool requires:
- `networkx`
- `numpy`
- `requests`
- `websocket-client`

Install them with:
```bash
pip install networkx numpy requests websocket-client
```

## Tools

### Find Optimal Path

Use `router.py` to calculate the best path and estimated output.

```bash
python3 /path/to/skill/router.py --from FROM_TOKEN --to TO_TOKEN --amount AMOUNT
```

#### Parameters:
- `--from`: Symbol of the token to trade (e.g., `BTS`).
- `--to`: Symbol of the target token (e.g., `HONEST.MONEY`).
- `--amount`: Amount of the 'from' token (default: 1.0).
- `--mock`: Use mock data for testing (optional).

#### Output Format (JSON):
```json
{
  "status": "success",
  "from": "BTS",
  "to": "HONEST.MONEY",
  "input_amount": 10.0,
  "output_amount": 0.456,
  "path": ["BTS", "XBTSX.USDT", "HONEST.MONEY"],
  "summary": "Trade 10.0 BTS for approx 0.456 HONEST.MONEY"
}
```
