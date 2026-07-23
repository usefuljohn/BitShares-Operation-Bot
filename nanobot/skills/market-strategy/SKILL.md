---
name: market-strategy
description: "Autonomous Strategy Monitor — Collects DEX state, evaluates trigger conditions, and recommends market actions."
---

# Market Strategy Monitor Skill

Evaluates BitShares DEX market state against configurable strategy rules.

## Core Capabilities
- Periodically queries DEX node state and price feed indices via `strategy_monitor.py`.
- Compares price movements against rules defined in `strategy_rules.json`.
- Emits structured reports and triggers for the agent execution loop.
