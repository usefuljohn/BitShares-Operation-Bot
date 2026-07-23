---
name: market-intel
description: "Market Intelligence — Fetches prices from Pyth Network and Kibana, calculates ratios, and manages the shared price index"
triggers:
  - tradfi
  - prices
  - gold ratio
  - market data
  - feed prices
  - kibana
  - 7 day average
  - price index
  - market analysis
---

# Market Intelligence

Provides informational market data tools — price feeds, ratios, and the shared
price index that other skills depend on. This skill is **strictly informational**
and does NOT generate transactions.

> **Note:** Straddle order generation has been moved to the `dex-straddle` skill.

## 1. TradFi Market Prices & Ratios (`tradfi_manager.py`)
Fetches live prices for over 20 assets (Crypto, ETFs, Stocks, Commodities) from the Pyth Network and calculates custom relationships (e.g., Gold/Silver ratio, BTC/Gold).

```bash
cd /app/nanobot/skills/market-intel
python3 tradfi_manager.py
```
*Outputs JSON with all assets and ratios.*

## 2. Feed Prices (`feed_price_manager.py`)
Queries the latest BitShares feed price and 7-day average using Kibana.

```bash
cd /app/nanobot/skills/market-intel

# Default (HONEST.USD and RUBLE)
python3 feed_price_manager.py

# Specific assets
python3 feed_price_manager.py --assets BTS HONEST.USD
```
*Outputs JSON with current and 7-day average prices.*

## 3. Price Index Daemon (`price_index_manager.py`)
Maintains the `recent_price_index.json` file. Run this in the background or via cron to keep prices fresh. The strategy monitor (`market-strategy`) also refreshes this automatically every 30 minutes.

```bash
cd /app/nanobot/skills/market-intel
python3 price_index_manager.py
```

The price index is a shared data contract consumed by:
- `straddle.py` (`dex-straddle` skill) — for midpoint price resolution
- `ops.py` (`dex-ops` skill) — for `--slippage` auto-pricing on limit orders
- `strategy_monitor.py` (`market-strategy` skill) — for delta comparisons
