from __future__ import annotations

import secrets
from dataclasses import replace
from uuid import UUID, uuid4

from sot.domain.errors import DomainError
from sot.domain.models import (
    ApprovalResult,
    Branch,
    Cite,
    Document,
    DocumentView,
    NewTurn,
    Proposal,
    ProposalStatus,
    Revision,
    Session,
    SessionDetail,
    SessionView,
    Toss,
    TossView,
    Turn,
    utc_now,
)
from sot.domain.ports import SOTRepository

DEVELOPMENT_USERS = frozenset({"alice", "bob"})


class SOTService:
    def __init__(self, repository: SOTRepository) -> None:
        self._repository = repository

    async def create_document(
        self, *, actor_id: str, title: str, content: str
    ) -> Document:
        self._require_actor(actor_id)
        title = self._require_text(title, "document_title_required")
        content = self._require_text(content, "revision_content_required")
        now = utc_now()
        revision = Revision(
            id=uuid4(),
            document_id=uuid4(),
            number=1,
            content=content,
            proposal_id=None,
            created_by=actor_id,
            created_at=now,
        )
        document = Document(
            id=revision.document_id,
            title=title,
            current_revision_id=revision.id,
            created_by=actor_id,
            created_at=now,
        )
        async with self._repository.transaction():
            await self._repository.save_document(document)
            await self._repository.save_revision(revision)
        return document

    async def bootstrap(self, *, actor_id: str) -> tuple[Document, ...]:
        self._require_actor(actor_id)
        return await self._repository.list_documents()

    async def document_view(self, *, document_id: UUID, actor_id: str) -> DocumentView:
        self._require_actor(actor_id)
        document = await self._document(document_id)
        current = await self.current_revision(document_id)
        return DocumentView(
            document=document,
            current_revision=current,
            revisions=await self._repository.list_revisions(document_id),
            sessions=await self._repository.list_sessions(document_id),
        )

    async def session_detail(self, *, session_id: UUID, actor_id: str) -> SessionDetail:
        self._require_actor(actor_id)
        session = await self._session(session_id)
        branches = await self._repository.list_branches(session_id)
        turns: list[Turn] = []
        cites: list[Cite] = []
        proposals: list[Proposal] = []
        for branch in branches:
            turns.extend(await self._repository.list_turns(branch.id))
            cites.extend(await self._repository.list_cites(branch.id))
            proposals.extend(await self._repository.list_proposals(branch.id))
        return SessionDetail(
            session=session,
            branches=branches,
            turns=tuple(turns),
            cites=tuple(cites),
            proposals=tuple(proposals),
        )

    async def toss_view(self, *, token: str) -> TossView:
        toss = await self._repository.get_toss_by_token(token)
        if toss is None:
            raise DomainError("toss_not_found", "Toss does not exist")
        cite = await self._cite(toss.cite_id)
        turns = await self._repository.get_turns(cite.turn_ids)
        return TossView(toss=toss, cite=cite, turns=turns)

    async def current_revision(self, document_id: UUID) -> Revision:
        document = await self._document(document_id)
        revision = await self._repository.get_revision(document.current_revision_id)
        if revision is None:
            raise DomainError("revision_not_found", "Current revision does not exist")
        return revision

    async def create_session(
        self, *, document_id: UUID, owner_id: str, title: str
    ) -> SessionView:
        self._require_actor(owner_id)
        await self._document(document_id)
        now = utc_now()
        session = Session(
            id=uuid4(),
            document_id=document_id,
            owner_id=owner_id,
            title=self._require_text(title, "session_title_required"),
            created_at=now,
        )
        branch = Branch(
            id=uuid4(),
            session_id=session.id,
            owner_id=owner_id,
            parent_branch_id=None,
            source_toss_id=None,
            created_at=now,
        )
        async with self._repository.transaction():
            await self._repository.save_session(session)
            await self._repository.save_branch(branch)
        return SessionView(session=session, branch=branch)

    async def append_turns(
        self,
        *,
        branch_id: UUID,
        actor_id: str,
        turns: tuple[NewTurn, ...],
    ) -> tuple[Turn, ...]:
        branch = await self._owned_branch(branch_id, actor_id)
        del branch
        if not turns:
            raise DomainError("turns_required", "At least one turn is required")
        existing = await self._repository.list_turns(branch_id)
        now = utc_now()
        created = tuple(
            Turn(
                id=uuid4(),
                branch_id=branch_id,
                ordinal=len(existing) + index,
                role=turn.role,
                content=self._require_text(turn.content, "turn_content_required"),
                created_at=now,
            )
            for index, turn in enumerate(turns, start=1)
        )
        await self._repository.append_turns(created)
        return created

    async def create_cite(
        self,
        *,
        branch_id: UUID,
        actor_id: str,
        turn_ids: tuple[UUID, ...],
        summary: str,
    ) -> Cite:
        await self._owned_branch(branch_id, actor_id)
        if not turn_ids or len(set(turn_ids)) != len(turn_ids):
            raise DomainError(
                "cite_turns_invalid", "Cite turns must be unique and non-empty"
            )
        turns = await self._repository.get_turns(turn_ids)
        if len(turns) != len(turn_ids) or any(
            turn.branch_id != branch_id for turn in turns
        ):
            raise DomainError(
                "cite_turn_mismatch", "Cite turns must belong to the branch"
            )
        cite = Cite(
            id=uuid4(),
            branch_id=branch_id,
            created_by=actor_id,
            turn_ids=turn_ids,
            summary=self._require_text(summary, "cite_summary_required"),
            created_at=utc_now(),
        )
        await self._repository.save_cite(cite)
        return cite

    async def create_toss(self, *, cite_id: UUID, actor_id: str) -> Toss:
        cite = await self._cite(cite_id)
        await self._owned_branch(cite.branch_id, actor_id)
        toss = Toss(
            id=uuid4(),
            cite_id=cite.id,
            token=secrets.token_urlsafe(18),
            created_by=actor_id,
            created_at=utc_now(),
        )
        await self._repository.save_toss(toss)
        return toss

    async def fork_toss(self, *, token: str, actor_id: str) -> Branch:
        self._require_actor(actor_id)
        toss = await self._repository.get_toss_by_token(token)
        if toss is None:
            raise DomainError("toss_not_found", "Toss does not exist")
        cite = await self._cite(toss.cite_id)
        source = await self._branch(cite.branch_id)
        branch = Branch(
            id=uuid4(),
            session_id=source.session_id,
            owner_id=actor_id,
            parent_branch_id=source.id,
            source_toss_id=toss.id,
            created_at=utc_now(),
        )
        await self._repository.save_branch(branch)
        return branch

    async def create_proposal(
        self, *, branch_id: UUID, actor_id: str, content: str
    ) -> Proposal:
        branch = await self._owned_branch(branch_id, actor_id)
        session = await self._session(branch.session_id)
        proposal = Proposal(
            id=uuid4(),
            document_id=session.document_id,
            branch_id=branch.id,
            created_by=actor_id,
            content=self._require_text(content, "proposal_content_required"),
            status=ProposalStatus.OPEN,
            created_at=utc_now(),
        )
        await self._repository.save_proposal(proposal)
        return proposal

    async def approve_proposal(
        self, *, proposal_id: UUID, actor_id: str
    ) -> ApprovalResult:
        self._require_actor(actor_id)
        proposal = await self._proposal(proposal_id)
        if proposal.status is not ProposalStatus.OPEN:
            raise DomainError("proposal_closed", "Proposal is already published")
        async with self._repository.transaction():
            await self._repository.add_approval(proposal.id, actor_id)
            approvers = await self._repository.list_approvals(proposal.id)
            if len(approvers) < 2:
                return ApprovalResult(
                    proposal=proposal, approver_ids=approvers, revision=None
                )
            current = await self.current_revision(proposal.document_id)
            revision = Revision(
                id=uuid4(),
                document_id=proposal.document_id,
                number=current.number + 1,
                content=proposal.content,
                proposal_id=proposal.id,
                created_by=actor_id,
                created_at=utc_now(),
            )
            published = replace(proposal, status=ProposalStatus.PUBLISHED)
            document = await self._document(proposal.document_id)
            await self._repository.save_revision(revision)
            await self._repository.save_proposal(published)
            await self._repository.save_document(
                replace(document, current_revision_id=revision.id)
            )
            return ApprovalResult(
                proposal=published,
                approver_ids=approvers,
                revision=revision,
            )

    async def _document(self, document_id: UUID) -> Document:
        document = await self._repository.get_document(document_id)
        if document is None:
            raise DomainError("document_not_found", "Document does not exist")
        return document

    async def _session(self, session_id: UUID) -> Session:
        session = await self._repository.get_session(session_id)
        if session is None:
            raise DomainError("session_not_found", "Session does not exist")
        return session

    async def _branch(self, branch_id: UUID) -> Branch:
        branch = await self._repository.get_branch(branch_id)
        if branch is None:
            raise DomainError("branch_not_found", "Branch does not exist")
        return branch

    async def _owned_branch(self, branch_id: UUID, actor_id: str) -> Branch:
        self._require_actor(actor_id)
        branch = await self._branch(branch_id)
        if branch.owner_id != actor_id:
            raise DomainError("branch_forbidden", "Branch belongs to another user")
        return branch

    async def _cite(self, cite_id: UUID) -> Cite:
        cite = await self._repository.get_cite(cite_id)
        if cite is None:
            raise DomainError("cite_not_found", "Cite does not exist")
        return cite

    async def _proposal(self, proposal_id: UUID) -> Proposal:
        proposal = await self._repository.get_proposal(proposal_id)
        if proposal is None:
            raise DomainError("proposal_not_found", "Proposal does not exist")
        return proposal

    @staticmethod
    def _require_actor(actor_id: str) -> None:
        if actor_id not in DEVELOPMENT_USERS:
            raise DomainError("actor_unknown", "Actor does not exist")

    @staticmethod
    def _require_text(value: str, code: str) -> str:
        value = value.strip()
        if not value:
            raise DomainError(code, "A non-empty value is required")
        return value


__all__ = ["DEVELOPMENT_USERS", "SOTService"]
