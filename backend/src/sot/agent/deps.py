from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sot.consensus.contracts import ProposalCreator
from sot.identity.contracts import Actor
from sot.session.contracts import CiteCreator
from sot.shared.ids import BranchId, DocumentId, WorkspaceId


@dataclass(slots=True)
class BranchLineage:
    expected_version: int

    def advance_to(self, version: int) -> None:
        if version <= self.expected_version:
            raise ValueError("branch version must increase")
        self.expected_version = version


# The document is put in front of the agent rather than fetched by it. An
# edit names the place it changes by quoting it, so an agent that has not read
# the document cannot write one — and a tool it may forget to call is the same
# as no tool at all. Long documents are cut, and the cut is declared, because
# an anchor into text the agent never saw would be a guess.
DOCUMENT_CONTEXT_LIMIT = 20_000


@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    """The document as it stands, at the revision this run is writing against."""

    document_id: DocumentId
    title: str
    revision: int
    content: str
    truncated: bool = False

    @classmethod
    def of(
        cls, document_id: DocumentId, title: str, revision: int, content: str
    ) -> "DocumentSnapshot":
        cut = len(content) > DOCUMENT_CONTEXT_LIMIT
        return cls(
            document_id,
            title,
            revision,
            content[:DOCUMENT_CONTEXT_LIMIT] if cut else content,
            cut,
        )


@dataclass(frozen=True, slots=True)
class CompletedTurnReference:
    turn_id: UUID
    ordinal: int
    history_index: int
    role: Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class AgentDeps:
    actor: Actor
    workspace_id: WorkspaceId
    branch_id: BranchId
    lineage: BranchLineage
    cite_creator: CiteCreator
    proposal_creator: ProposalCreator
    turn_references: tuple[CompletedTurnReference, ...] = ()
    # Absent only for a session with no document attached to it.
    document: DocumentSnapshot | None = None
