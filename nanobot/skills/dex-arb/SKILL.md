---
name: dex-arb
description: "Cross-Pool Arbitrage — Balances BTWTY.BTC vs XBTSX.BTC price ratios via two-hop pool swaps"
triggers:
  - ratio
  - arbitrage
  - arb
  - equilibrium
  - BTWTY.BTC
  - XBTSX.BTC
  - ratio matcher
  - price disparity
---

# Cross-Pool Arbitrage (Ratio Matcher)

Balances the price of two BTC-pegged assets on BitShares DEX by calculating the
exact trade size to bring both pools to equilibrium and generating a two-hop swap
transaction.

**Pools:**
- **Pool A (1.19.539):** BTS / BTWTY.BTC
- **Pool B (1.19.58):** BTS / XBTSX.BTC

Both BTWTY.BTC and XBTSX.BTC represent BTC at a 1:1 value model. When one becomes
overvalued relative to the other, this tool sells the expensive version for BTS, then
buys the cheap version — a risk-neutral rebalance.

## Skill Location

```
/app/nanobot/skills/dex-arb/
```

Key files:
- `ratio_matcher.py` — Main execution engine
- `config.json` — Pool IDs, asset IDs, decimals

## Usage

**Default account is `johnr`** — if the user does not specify an account, always use `johnr`.

```bash
cd /app/nanobot/skills/dex-arb

# Automatic equilibrium calculation (recommended)
python3 ratio_matcher.py --account johnr --output-dir /home/nanobot/.bob/workspace

# Dry run — print simulation without writing files
python3 ratio_matcher.py --account johnr --dry-run

# Manual trade size
python3 ratio_matcher.py --account johnr --amount 0.0001 --output-dir /home/nanobot/.bob/workspace

# With deeplink
python3 ratio_matcher.py --account johnr --output-dir /home/nanobot/.bob/workspace --emit-deeplink
```

### Parameters

| Flag | Required | Description |
|---|---|---|
| `--account` | No | Account name or ID (default: `johnr`) |
| `--output-dir` | **Yes** | Directory for output files |
| `--amount` | No | Manual swap amount in BTC (skips equilibrium calc) |
| `--slippage` | No | Slippage tolerance (default: 1% / 0.01) |
| `--force` | No | Generate outputs even if trade is unprofitable |
| `--emit-deeplink` | No | Also write a deeplink `.txt` file |
| `--dry-run` | No | Print calculations without writing files |

### Output Files

- `ratio_<account>.json` — Transaction bundle (always)
- `deeplink_ratio_<account>.txt` — Beet wallet deep link (with `--emit-deeplink`)

## How It Works

1. Fetch live reserves for both pools
2. Compare BTS/BTC price ratios — identify which is overvalued
3. Use binary search to find the exact swap size that equalizes ratios
4. Simulate the two-hop trade (sell overpriced BTC → BTS → buy underpriced BTC)
5. Validate profitability and account balances
6. Generate atomic 2-operation transaction bundle

## Safety

- **Balance capping:** Auto-caps trade size to available account balance
- **Profitability check:** Refuses to write outputs if trade is unprofitable (unless `--force`)
- **Slippage buffer:** Uses existing BTS balance to cover inter-hop slippage gap
