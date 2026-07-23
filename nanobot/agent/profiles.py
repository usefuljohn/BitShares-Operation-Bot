"""
Agent Profiles — Defines the specialist sub-agents and their scoped capabilities.

Each AgentProfile defines:
  - Which tools the sub-agent can access
  - Which skills are injected into its context
  - A concise persona prompt (how it thinks/responds)
  - Trigger keywords for intent routing
"""

from dataclasses import dataclass, field


@dataclass
class AgentProfile:
    """Definition of a specialist sub-agent."""

    agent_id: str
    display_name: str
    persona: str                        # Concise system-level persona for this sub-agent
    skill_names: list[str]              # Skills to load into this sub-agent's context
    tool_names: list[str]               # Tools this sub-agent can use (scoped subset)
    triggers: list[str] = field(default_factory=list)   # Keywords for intent routing
    max_iterations: int = 15            # Tool-calling loop limit


# ─── Profile Definitions ─────────────────────────────────────────────────────

CREDIT_FUNDER = AgentProfile(
    agent_id="credit_funder",
    display_name="Credit Funder",
    persona=(
        "You are BOB's core operator — you manage LP funding for BitShares credit "
        "offers and handle all blockchain operations (transfers, limit orders, credit "
        "offer management, pool routing). The skill files are at "
        "/app/nanobot/skills/dex-credit/. To generate a credit fund transaction, run: "
        "cd /app/nanobot/skills/dex-credit && python liquidityengine.py --account <account> "
        "--output-dir /home/nanobot/.bob/workspace --no-notify "
        "(bit20 is the default account — use it unless the user specifies otherwise). "
        "If the user specifies a particular pool ID, also pass --source <pool_id>. "
        "ALWAYS include --output-dir /home/nanobot/.bob/workspace so the "
        "generated files are accessible. "
        "ALWAYS include --no-notify so the engine does NOT send its own Telegram alert; "
        "the orchestrator will deliver the deeplink via the message tool instead. "
        "CRITICAL: When files are generated, you MUST report the EXACT absolute paths "
        "to the orchestrator (e.g., '/home/nanobot/.bob/workspace/bundle_bit20.json' "
        "and '/home/nanobot/.bob/workspace/deeplink_bit20.txt'). "
        "The orchestrator relies on these specific paths to attach the files to the "
        "Telegram message. "
        "For DEX operations (transfers, limit orders, swaps), use dex-ops/ops.py. "
        "For pool routing, use dex-router/router.py. "
        "For LP yield checks, use dex-pools/fetch_pool.py. "
        "For straddle orders, use dex-straddle/straddle.py. "
        "For ratio arbitrage (BTWTY.BTC vs XBTSX.BTC), use dex-arb/ratio_matcher.py. "
        "For flash-loan leverage cascades, use dex-leverage/cascade.py."
    ),
    skill_names=["dex-credit", "dex-ops", "dex-pools", "dex-router", "dex-leverage", "dex-arb", "dex-straddle"],
    tool_names=[
        "read_file",
        "exec",
    ],
    triggers=[
        "fund", "rebalance", "credit offer", "LP withdraw",
        "pool rebalance", "fund source", "top up", "funding daemon",
        "collateral", "credit update", "withdrawal", "credit fund",
        "trade", "buy", "sell", "swap", "liquidity", "pool", "bitshares",
        "transfer", "send", "order", "limit order", "balance",
        "cascade", "leverage", "flash loan", "bootstrap",
        "straddle", "spread", "dex trader",
        "ratio", "arbitrage", "arb", "equilibrium", "BTWTY.BTC", "XBTSX.BTC",
    ],
    max_iterations=20,
)

MARKET_ANALYST = AgentProfile(
    agent_id="market_analyst",
    display_name="Market Analyst",
    persona=(
        "You provide market intelligence and price data for BOB's credit funding "
        "decisions. You fetch live prices from the Pyth Network, BitShares feed prices "
        "and 7-day averages from Kibana, and maintain the price index. You run the "
        "python scripts in the market-intel skill directory (e.g. tradfi_manager.py, "
        "feed_price_manager.py, price_index_manager.py). You always cd into the "
        "skill directory before executing the scripts. IMPORTANT: There is NO 'tradfi' "
        "executable; you must always use 'python3' to run the scripts. "
        "You also run the SOFR rate calculator at "
        "/app/nanobot/skills/dex-credit/sofr_rate_calculator.py when asked about "
        "interest rates, fee rates, or SOFR. "
        "You are strictly informational and DO NOT execute trades or generate transactions."
    ),
    skill_names=["market-intel", "dex-credit", "market-strategy"],
    tool_names=[
        "read_file",
        "exec",
    ],
    triggers=[
        "tradfi", "prices", "gold ratio", "market data",
        "feed prices", "kibana", "7 day average", "price index",
        "market analysis", "SOFR", "rate", "fee rate", "interest",
        "dashboard", "credit dashboard", "portfolio",
        "gold", "silver", "btc", "bitcoin", "xau", "xag", "price",
        "strategy", "monitor", "autonomous", "patrol", "status check",
    ],
    max_iterations=20,
)

SYSTEM_ADMIN = AgentProfile(
    agent_id="system_admin",
    display_name="System Administrator",
    persona=(
        "You are an expert in system operations, file management, and shell scripting. "
        "You handle complex filesystem tasks, process management via tmux, and "
        "automation scripts. You are responsible for Daemon Management: starting, "
        "stopping, and monitoring background daemons (e.g., price_index_manager.py, "
        "dex-credit/daemon.py) inside tmux sessions. "
        "You also manage BOB's long-term memory and conversation summaries. "
        "You are careful and always check your current state before making changes."
    ),
    skill_names=["tmux", "cron", "memory", "summarize"],
    tool_names=[
        "read_file",
        "write_file",
        "edit_file",
        "ls",
        "exec",
        "cron",
    ],
    triggers=[
        "file", "directory", "folder", "script", "bash", "shell", "tmux",
        "process", "background", "schedule", "cron", "automation",
        "remember", "memory", "fact", "record", "note", "reminder",
        "summarize",
    ],
)


# ─── All Profiles ─────────────────────────────────────────────────────────────

ALL_PROFILES: dict[str, AgentProfile] = {
    p.agent_id: p
    for p in [
        CREDIT_FUNDER,
        MARKET_ANALYST,
        SYSTEM_ADMIN,
    ]
}
