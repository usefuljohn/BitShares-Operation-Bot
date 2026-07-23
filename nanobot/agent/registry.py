"""
AgentRegistry — Routes user intent to the appropriate sub-agent profile.

The registry holds all registered AgentProfiles and provides:
  - Keyword-based routing (fast, no LLM call)
  - A compact summary for the orchestrator's system prompt (LLM-based routing)
"""

import logging
from typing import Optional

from nanobot.agent.profiles import AgentProfile, ALL_PROFILES

logger = logging.getLogger("AgentRegistry")


class AgentRegistry:
    """Registry of sub-agent profiles with intent routing."""

    def __init__(self, profiles: dict[str, AgentProfile] | None = None):
        self._profiles = dict(profiles or ALL_PROFILES)

    def get(self, agent_id: str) -> AgentProfile | None:
        """Look up a profile by agent_id."""
        return self._profiles.get(agent_id)

    def all_ids(self) -> list[str]:
        """Return all registered agent IDs."""
        return list(self._profiles.keys())

    def route_by_keywords(self, text: str) -> AgentProfile | None:
        """Simple keyword-based routing. Returns the best-matching profile or None.

        Scores each profile by how many of its trigger keywords appear in the
        input text. Returns the highest-scoring profile, or None if no triggers
        match at all.
        """
        text_lower = text.lower()
        best_profile = None
        best_score = 0

        for profile in self._profiles.values():
            score = sum(1 for trigger in profile.triggers if trigger in text_lower)
            if score > best_score:
                best_score = score
                best_profile = profile

        return best_profile

    def build_routing_summary(self) -> str:
        """Build a compact routing summary for the orchestrator's system prompt.

        This gives the orchestrator LLM enough information to decide which
        sub-agent should handle a request, without exposing tool schemas.
        """
        lines = ["Available sub-agents you can dispatch to:\n"]
        for profile in self._profiles.values():
            lines.append(
                f"- **{profile.agent_id}** ({profile.display_name}): "
                f"{profile.persona.split('.')[0]}."
            )
            top_triggers = profile.triggers[:8]
            lines.append(f"  Triggers: {', '.join(top_triggers)}")
            lines.append("")

        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._profiles)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._profiles
