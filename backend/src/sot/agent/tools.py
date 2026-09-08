from typing import Literal, TypedDict

from pydantic_ai import ModelRetry, RunContext

from sot.agent.deps import AgentDeps
from sot.consensus.contracts import DocumentEdit
from sot.session.contracts import TurnId
from sot.shared.errors import InvalidInput


class SessionCiteResult(TypedDict):
    citeId: str
    branchVersion: int


class SOTUpdateResult(TypedDict):
    proposalId: str
    status: Literal["open"]
    branchVersion: int


class SOTReadResult(TypedDict):
    documentId: str
    title: str
    revision: int
    content: str


async def session_cite(
    ctx: RunContext[AgentDeps], turn_ids: tuple[TurnId, ...], summary: str
) -> SessionCiteResult:
    """Preserve selected completed conversation turns as an immutable cite."""
    deps = ctx.deps
    result = await deps.cite_creator.create_from_agent(
        actor=deps.actor,
        workspace_id=deps.workspace_id,
        branch_id=deps.branch_id,
        expected_branch_version=deps.lineage.expected_version,
        turn_ids=turn_ids,
        summary=summary,
    )
    deps.lineage.advance_to(result.branch_version)
    return {"citeId": str(result.resource_id), "branchVersion": result.branch_version}


async def sot_read(ctx: RunContext[AgentDeps]) -> SOTReadResult:
    """Read the shared document in full, as it stands right now.

    The current text is already in your instructions; call this when you need
    it again — after proposing an edit, when the copy you were given was cut
    short, or when you suspect someone has merged something since this
    conversation started.
    """
    deps = ctx.deps
    if deps.document is None or deps.document_reader is None:
        raise ModelRetry("This session is not attached to a document.")
    view = await deps.document_reader.execute(
        deps.actor, deps.workspace_id, deps.document.document_id
    )
    return {
        "documentId": str(view.document.id),
        "title": view.document.title,
        "revision": view.current_revision.number,
        "content": view.current_revision.content,
    }


class DocumentEditInput(TypedDict):
    find: str
    replace: str


async def sot_update(
    ctx: RunContext[AgentDeps], edits: list[DocumentEditInput]
) -> SOTUpdateResult:
    """Propose edits to the shared document. Cannot publish main.

    Each edit replaces `find` with `replace`. `find` must appear exactly once
    in the current document, so include enough surrounding text to name one
    place; use an empty `find` to append a new section. Change only what the
    decision changes.
    """
    deps = ctx.deps
    try:
        result = await deps.proposal_creator.create_from_agent(
            actor=deps.actor,
            workspace_id=deps.workspace_id,
            branch_id=deps.branch_id,
            expected_branch_version=deps.lineage.expected_version,
            edits=tuple(DocumentEdit(e["find"], e["replace"]) for e in edits),
            tool_call_id=ctx.tool_call_id,
        )
    except InvalidInput as rejected:
        # An anchor that matches nothing, an anchor that matches twice, an
        # update too long to review: all of them are this call being wrong,
        # and all of them the model can fix by writing a smaller, better
        # aimed edit. Anything else (a conflict, a permission) is not.
        raise ModelRetry(rejected.message) from rejected
    deps.lineage.advance_to(result.branch_version)
    return {
        "proposalId": str(result.resource_id),
        "status": "open",
        "branchVersion": result.branch_version,
    }


__all__ = ["session_cite", "sot_read", "sot_update"]
