from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from uuid import UUID

from sot.domain.errors import DomainError
from sot.domain.models import (
    Branch,
    Cite,
    Document,
    Proposal,
    Revision,
    Session,
    Toss,
    Turn,
)


@dataclass(slots=True)
class MemorySOTRepository:
    documents: dict[UUID, Document] = field(default_factory=dict)
    revisions: dict[UUID, Revision] = field(default_factory=dict)
    sessions: dict[UUID, Session] = field(default_factory=dict)
    branches: dict[UUID, Branch] = field(default_factory=dict)
    turns: dict[UUID, Turn] = field(default_factory=dict)
    cites: dict[UUID, Cite] = field(default_factory=dict)
    tosses: dict[UUID, Toss] = field(default_factory=dict)
    proposals: dict[UUID, Proposal] = field(default_factory=dict)
    approvals: dict[UUID, set[str]] = field(default_factory=dict)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        snapshot = deepcopy(
            (
                self.documents,
                self.revisions,
                self.sessions,
                self.branches,
                self.turns,
                self.cites,
                self.tosses,
                self.proposals,
                self.approvals,
            )
        )
        try:
            yield
        except Exception:
            (
                self.documents,
                self.revisions,
                self.sessions,
                self.branches,
                self.turns,
                self.cites,
                self.tosses,
                self.proposals,
                self.approvals,
            ) = snapshot
            raise

    async def save_document(self, document: Document) -> None:
        self.documents[document.id] = document

    async def get_document(self, document_id: UUID) -> Document | None:
        return self.documents.get(document_id)

    async def list_documents(self) -> tuple[Document, ...]:
        return tuple(sorted(self.documents.values(), key=lambda item: item.created_at))

    async def save_revision(self, revision: Revision) -> None:
        self.revisions[revision.id] = revision

    async def get_revision(self, revision_id: UUID) -> Revision | None:
        return self.revisions.get(revision_id)

    async def list_revisions(self, document_id: UUID) -> tuple[Revision, ...]:
        return tuple(
            sorted(
                (
                    revision
                    for revision in self.revisions.values()
                    if revision.document_id == document_id
                ),
                key=lambda revision: revision.number,
            )
        )

    async def save_session(self, session: Session) -> None:
        self.sessions[session.id] = session

    async def get_session(self, session_id: UUID) -> Session | None:
        return self.sessions.get(session_id)

    async def list_sessions(self, document_id: UUID) -> tuple[Session, ...]:
        return tuple(
            sorted(
                (
                    session
                    for session in self.sessions.values()
                    if session.document_id == document_id
                ),
                key=lambda item: item.created_at,
            )
        )

    async def save_branch(self, branch: Branch) -> None:
        self.branches[branch.id] = branch

    async def get_branch(self, branch_id: UUID) -> Branch | None:
        return self.branches.get(branch_id)

    async def list_branches(self, session_id: UUID) -> tuple[Branch, ...]:
        return tuple(
            sorted(
                (
                    branch
                    for branch in self.branches.values()
                    if branch.session_id == session_id
                ),
                key=lambda item: item.created_at,
            )
        )

    async def append_turns(self, turns: tuple[Turn, ...]) -> None:
        existing = {(turn.branch_id, turn.ordinal) for turn in self.turns.values()}
        incoming = {(turn.branch_id, turn.ordinal) for turn in turns}
        if existing & incoming or len(incoming) != len(turns):
            raise DomainError("turn_ordinal_conflict", "Turn ordinal already exists")
        self.turns.update((turn.id, turn) for turn in turns)

    async def list_turns(self, branch_id: UUID) -> tuple[Turn, ...]:
        return tuple(
            sorted(
                (turn for turn in self.turns.values() if turn.branch_id == branch_id),
                key=lambda turn: turn.ordinal,
            )
        )

    async def get_turns(self, turn_ids: tuple[UUID, ...]) -> tuple[Turn, ...]:
        return tuple(
            self.turns[turn_id] for turn_id in turn_ids if turn_id in self.turns
        )

    async def save_cite(self, cite: Cite) -> None:
        self.cites[cite.id] = cite

    async def get_cite(self, cite_id: UUID) -> Cite | None:
        return self.cites.get(cite_id)

    async def list_cites(self, branch_id: UUID) -> tuple[Cite, ...]:
        return tuple(
            sorted(
                (cite for cite in self.cites.values() if cite.branch_id == branch_id),
                key=lambda item: item.created_at,
            )
        )

    async def save_toss(self, toss: Toss) -> None:
        if any(item.token == toss.token for item in self.tosses.values()):
            raise DomainError("toss_token_conflict", "Toss token already exists")
        self.tosses[toss.id] = toss

    async def get_toss(self, toss_id: UUID) -> Toss | None:
        return self.tosses.get(toss_id)

    async def get_toss_by_token(self, token: str) -> Toss | None:
        return next(
            (toss for toss in self.tosses.values() if toss.token == token), None
        )

    async def save_proposal(self, proposal: Proposal) -> None:
        self.proposals[proposal.id] = proposal

    async def get_proposal(self, proposal_id: UUID) -> Proposal | None:
        return self.proposals.get(proposal_id)

    async def list_proposals(self, branch_id: UUID) -> tuple[Proposal, ...]:
        return tuple(
            sorted(
                (
                    proposal
                    for proposal in self.proposals.values()
                    if proposal.branch_id == branch_id
                ),
                key=lambda item: item.created_at,
            )
        )

    async def add_approval(self, proposal_id: UUID, actor_id: str) -> None:
        approvers = self.approvals.setdefault(proposal_id, set())
        if actor_id in approvers:
            raise DomainError("approval_duplicate", "Actor already approved")
        approvers.add(actor_id)

    async def list_approvals(self, proposal_id: UUID) -> tuple[str, ...]:
        return tuple(sorted(self.approvals.get(proposal_id, set())))


__all__ = ["MemorySOTRepository"]
