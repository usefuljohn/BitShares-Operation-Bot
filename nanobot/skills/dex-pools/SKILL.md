---
name: dex-pools
description: Calculate BitShares Liquidity Pool yields and APR.
metadata: {"nanobot":{"emoji":"📈","requires":{"bins":["python3"]}}}
---

# BitShares Liquidity Pool Yield Tracker

This skill provides a tool to fetch and calculate yield data for BitShares Liquidity Pools. It tracks the Price Per Share (PPS) index over time to estimate APR.

## Usage

Run the script using `python3` from the skill directory.

### Fetch current yield for default pools (BTS/CNY, BTS/USD, BTS/GOLD)
```bash
python3 /path/to/skill/fetch_pool.py
```

### Fetch and log data for specific pools
```bash
python3 /path/to/skill/fetch_pool.py 1.19.0 1.19.48 --log
```

### Parameters
- `pools`: List of pool IDs (e.g., `1.19.0`, `1.19.48`).
- `--log`: Append current data to the historical CSV for future APR calculations.
- `--log-file`: Path to a custom CSV file (defaults to `lp_yield_history.csv` in the skill directory).

## Data Location
The historical data is stored in `lp_yield_history.csv` within the skill directory. APR calculations require at least two data points for a given pool.
