# Skills Directory

Skills are self-contained capability modules that sub-agents can access. Each skill
provides a `SKILL.md` file that describes its purpose, usage, and file layout.

## Skill Taxonomy

### DEX Domain — Blockchain Operations & Transaction Generation

| Skill | Description |
|---|---|
| `dex-ops` | General BitShares operations — transfers, limit orders, asset queries |
| `dex-pools` | LP yield calculations, pool stats, TVL tracking |
| `dex-router` | Multi-hop path finding between assets via liquidity pools |
| `dex-arb` | Cross-pool ratio arbitrage (BTWTY.BTC vs XBTSX.BTC equilibrium balancing) |

### Market Domain — Intelligence & Strategy

| Skill | Description |
|---|---|
| `market-intel` | Pyth Network prices, BitShares feed prices, price index management |
| `market-strategy` | Autonomous strategy monitor — state collector, trigger engine, heartbeat integration |

### System Domain — Infrastructure

| Skill | Description |
|---|---|
| `cron` | Schedule reminders and recurring tasks |
| `memory` | Two-layer memory system with dream-managed knowledge files |
| `tmux` | Remote-control tmux sessions for interactive CLIs |
| `summarize` | Summarize or extract text/transcripts from URLs, podcasts, and local files |
| `my` | Agent runtime state inspection and configuration |