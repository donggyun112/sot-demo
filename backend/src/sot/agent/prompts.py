from pydantic_ai import RunContext

from sot.agent.deps import AgentDeps

INSTRUCTIONS = (
    "Help people examine a position, surface assumptions, and state "
    "concrete alternatives. Never claim that a draft changed the shared main "
    "document unless an authorized SOT tool confirms publication."
)


def request_context(ctx: RunContext[AgentDeps]) -> str:
    return (
        f"actor={ctx.deps.actor.user_id} workspace={ctx.deps.workspace_id} "
        f"branch={ctx.deps.branch_id}"
    )
