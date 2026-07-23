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

DEX_OPERATOR = AgentProfile(
    agent_id="dex_operator",
    display_name="DEX Operator",
    persona=(
        "You are BOB's BitShares execution operator — you handle all blockchain operations "
        "(transfers, limit orders, pool swaps, liquidity pool checks, and arbitrage matching). "
        "For DEX operations (transfers, limit orders, swaps), use dex-ops/ops.py. "
        "For pool routing, use dex-router/router.py. "
        "For LP yield checks, use dex-pools/fetch_pool.py. "
        "For ratio arbitrage, use dex-arb/ratio_matcher.py. "
        "Report exact generated file paths and execution outputs."
    ),
    skill_names=["dex-ops", "dex-pools", "dex-router", "dex-arb"],
    tool_names=[
        "read_file",
        "exec",
    ],
    triggers=[
        "trade", "buy", "sell", "swap", "liquidity", "pool", "bitshares",
        "transfer", "send", "order", "limit order", "balance",
        "ratio", "arbitrage", "arb", "equilibrium", "BTWTY.BTC", "XBTSX.BTC",
    ],
    max_iterations=20,
)

MARKET_ANALYST = AgentProfile(
    agent_id="market_analyst",
    display_name="Market Analyst",
    persona=(
        "You provide market intelligence and price data for BOB. You fetch live prices from "
        "the Pyth Network, BitShares feed prices, and maintain the price index using scripts "
        "in the market-intel skill directory (e.g. tradfi_manager.py, feed_price_manager.py, "
        "price_index_manager.py). You also evaluate strategy rules using market-strategy. "
        "You are strictly informational and DO NOT execute trades or generate transactions."
    ),
    skill_names=["market-intel", "market-strategy"],
    tool_names=[
        "read_file",
        "exec",
    ],
    triggers=[
        "tradfi", "prices", "gold ratio", "market data",
        "feed prices", "kibana", "7 day average", "price index",
        "market analysis", "gold", "silver", "btc", "bitcoin", "xau", "xag", "price",
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
        "automation scripts. You manage BOB's long-term memory and conversation summaries. "
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
        DEX_OPERATOR,
        MARKET_ANALYST,
        SYSTEM_ADMIN,
    ]
}
