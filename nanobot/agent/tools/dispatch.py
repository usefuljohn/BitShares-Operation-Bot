"""Dispatch tool for orchestrator-style delegation to specialist sub-agents."""

from typing import TYPE_CHECKING, Any, Dict

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.context import ContextAware, RequestContext

if TYPE_CHECKING:
    from nanobot.agent.subagent import SubagentManager


class DispatchTool(Tool, ContextAware):
    """Tool for the orchestrator to dispatch tasks to specialist sub-agents."""
    _scopes = {"orchestrator"}

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return ctx.subagent_manager is not None

    @classmethod
    def create(cls, ctx: Any) -> Tool:
        return cls(manager=ctx.subagent_manager)

    def __init__(self, manager: "SubagentManager"):
        self._manager = manager
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"
        self._session_key = "cli:direct"

    def set_context(self, ctx: RequestContext | str, chat_id: str | None = None) -> None:
        """Set the origin context for sub-agent results."""
        if isinstance(ctx, str):
            self._origin_channel = ctx
            self._origin_chat_id = chat_id or ""
            self._session_key = f"{ctx}:{chat_id}"
        else:
            self._origin_channel = ctx.channel
            self._origin_chat_id = ctx.chat_id
            self._session_key = ctx.session_key or f"{ctx.channel}:{ctx.chat_id}"

    @property
    def name(self) -> str:
        return "dispatch"

    @property
    def description(self) -> str:
        return (
            "Dispatch a task to a specialist sub-agent for execution. "
            "Use this whenever a user request requires specialized tools or knowledge — "
            "financial trading, system administration, deep research, or clerical tasks. "
            "The sub-agent will execute the task using its specialized tools and report back with results."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        from nanobot.agent.registry import AgentRegistry
        registry = AgentRegistry()
        
        # Build descriptions for each agent
        agent_descriptions = []
        for profile in registry._profiles.values():
            agent_descriptions.append(f"{profile.agent_id}: {profile.persona.split('.')[0]}")
        
        return {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "enum": registry.all_ids(),
                    "description": "The specialist sub-agent to dispatch to:\n" + "\n".join(agent_descriptions),
                },
                "task": {
                    "type": "string",
                    "description": (
                        "A clear, specific task description for the sub-agent. "
                        "Include all relevant details from the user's request. "
                        "The sub-agent has no conversational context, so everything it needs must be in this string."
                    ),
                },
            },
            "required": ["agent_id", "task"],
        }

    async def execute(self, agent_id: str, task: str, **kwargs: Any) -> str:
        """Dispatch a task to a sub-agent and wait for the result."""
        return await self._manager.dispatch(
            agent_id=agent_id,
            task=task,
            origin_channel=self._origin_channel,
            origin_chat_id=self._origin_chat_id,
            session_key=self._session_key,
        )
