from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sot.consensus.contracts import ProposalView
from sot.consensus.domain import ApprovalDecision, Proposal, ProposalNotFound
from sot.consensus.ports import ProposalRepository
from sot.document.contracts import DocumentReader
from sot.identity.contracts import Actor
from sot.session.contracts import (
    BranchContextReader,
    BranchMutationResult,
    BranchVersionGuard,
    BundleReader,
    SessionApproverReader,
    SessionAuthorizer,
    SessionPermission,
    SessionView,
)
from sot.shared.clock import Clock
from sot.shared.errors import Forbidden, InvalidInput, NotFound
from sot.shared.ids import (
    BranchId,
    BundleId,
    DocumentId,
    ProposalId,
    SessionId,
    UserId,
    WorkspaceId,
)
from sot.shared.unit_of_work import TransactionContext, UnitOfWorkFactory
from sot.workspace.contracts import WorkspaceMemberReader


def _view(proposal: Proposal) -> ProposalView:
    return ProposalView(
        proposal.id,
        proposal.workspace_id,
        proposal.document_id,
        proposal.source_session_id,
        proposal.created_by,
        proposal.created_at,
        proposal.current_version,
        proposal.status,
        proposal.approvals_for_current_version,
    )


@dataclass(frozen=True, slots=True)
class ProposalSources:
    """Collect authorized immutable inputs through owner-module capabilities."""

    sessions: SessionAuthorizer
    documents: DocumentReader
    bundles: BundleReader
    approvers: SessionApproverReader
    members: WorkspaceMemberReader

    async def prepare(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        session: SessionView,
        document_id: DocumentId,
        creator_id: UserId,
        bundle_ids: tuple[BundleId, ...],
        additional_approver_ids: frozenset[UserId],
    ) -> tuple[UUID, frozenset[UserId]]:
        """Use the caller's already-authorized immutable source within its tx."""
        if session.document_id is None:
            raise InvalidInput(
                "proposal_document_required", "Proposal requires a document"
            )
        if session.document_id != document_id:
            raise InvalidInput(
                "proposal_source_mismatch", "Source session belongs to another document"
            )
        document = await self.documents.require_document(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            document_id=document_id,
        )
        required = (
            additional_approver_ids
            | {creator_id}
            | await self.approvers.list_required_approvers(
                tx,
                workspace_id=workspace_id,
                session_id=session.id,
            )
        )
        for user_id in sorted(required, key=str):
            await self.members.require_member(tx, workspace_id, user_id)
        for bundle_id in bundle_ids:
            await self.bundles.require_snapshot(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                bundle_id=bundle_id,
            )
        return document.current_revision.id, frozenset(required)


class CreateProposal:
    def __init__(
        self,
        repository: ProposalRepository,
        sources: ProposalSources,
        branches: BranchContextReader,
        branch_versions: BranchVersionGuard,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._sources = sources
        self._branches = branches
        self._branch_versions = branch_versions
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        source_session_id: SessionId,
        *,
        document_id: DocumentId,
        content: str,
        bundle_ids: tuple[BundleId, ...] = (),
        additional_approver_ids: frozenset[UserId] = frozenset(),
    ) -> ProposalView:
        async with self._uow_factory().transaction() as tx:
            return _view(
                await self._create(
                    tx,
                    actor=actor,
                    workspace_id=workspace_id,
                    source_session_id=source_session_id,
                    document_id=document_id,
                    content=content,
                    bundle_ids=bundle_ids,
                    additional_approver_ids=additional_approver_ids,
                )
            )

    async def _create(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        source_session_id: SessionId,
        document_id: DocumentId,
        content: str,
        bundle_ids: tuple[BundleId, ...],
        additional_approver_ids: frozenset[UserId],
    ) -> Proposal:
        session = await self._sources.sessions.require(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            session_id=source_session_id,
            permission=SessionPermission.CREATE_PROPOSAL,
        )
        base_revision, required = await self._sources.prepare(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            session=session,
            document_id=document_id,
            creator_id=actor.user_id,
            bundle_ids=bundle_ids,
            additional_approver_ids=additional_approver_ids,
        )
        proposal = Proposal.create(
            workspace_id=workspace_id,
            document_id=document_id,
            source_session_id=source_session_id,
            created_by=actor.user_id,
            base_revision_id=base_revision,
            content=content,
            required_approver_ids=required,
            bundle_ids=bundle_ids,
            additional_approver_ids=additional_approver_ids,
            now=self._clock.now(),
        )
        await self._repository.add(tx, proposal)
        return proposal

    async def create_from_agent(
        self,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        expected_branch_version: int,
        content: str,
    ) -> BranchMutationResult:
        async with self._uow_factory().transaction() as tx:
            context = await self._branches.read(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                branch_id=branch_id,
                permission=SessionPermission.CREATE_PROPOSAL,
            )
            if context.document_id is None:
                raise InvalidInput(
                    "proposal_document_required", "Proposal requires a document"
                )
            branch_version = await self._branch_versions.advance(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                branch_id=branch_id,
                expected_version=expected_branch_version,
            )
            proposal = await self._create(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                source_session_id=context.session_id,
                document_id=context.document_id,
                content=content,
                bundle_ids=(),
                additional_approver_ids=frozenset(),
            )
            return BranchMutationResult(proposal.id, branch_version)


class ReviseProposal:
    def __init__(
        self,
        repository: ProposalRepository,
        sources: ProposalSources,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._sources = sources
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
        *,
        expected_version: int,
        content: str,
        bundle_ids: tuple[BundleId, ...],
        additional_approver_ids: frozenset[UserId] | None = None,
    ) -> ProposalView:
        async with self._uow_factory().transaction() as tx:
            proposal = await self._repository.get_for_update(
                tx, workspace_id, proposal_id
            )
            if proposal is None:
                raise ProposalNotFound()
            # Authorize before reporting version/status or creator-only restrictions.
            try:
                session = await self._sources.sessions.require(
                    tx,
                    actor=actor,
                    workspace_id=workspace_id,
                    session_id=proposal.source_session_id,
                    permission=SessionPermission.CREATE_PROPOSAL,
                )
            except NotFound:
                raise ProposalNotFound() from None
            proposal.require_version(expected_version)
            extras = proposal.current_version.additional_approver_ids
            if (
                additional_approver_ids is not None
                and additional_approver_ids != extras
            ):
                if actor.user_id != proposal.created_by:
                    raise Forbidden(
                        "proposal_creator_required",
                        "Only creator can change additional approvers",
                    )
                extras = additional_approver_ids
            base_revision, required = await self._sources.prepare(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                session=session,
                document_id=proposal.document_id,
                creator_id=proposal.created_by,
                bundle_ids=bundle_ids,
                additional_approver_ids=extras,
            )
            revised = proposal.revise(
                actor_id=actor.user_id,
                expected_version=expected_version,
                base_revision_id=base_revision,
                content=content,
                required_approver_ids=required,
                bundle_ids=bundle_ids,
                additional_approver_ids=extras,
                now=self._clock.now(),
            )
            await self._repository.save(tx, revised)
            return _view(revised)


class DecideProposal:
    def __init__(
        self,
        repository: ProposalRepository,
        members: WorkspaceMemberReader,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._members = members
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
        *,
        expected_version: int,
        decision: ApprovalDecision,
    ) -> ProposalView:
        async with self._uow_factory().transaction() as tx:
            await self._members.require_member(tx, workspace_id, actor.user_id)
            proposal = await self._repository.get_for_update(
                tx, workspace_id, proposal_id
            )
            if proposal is None or actor.user_id not in proposal.required_approvers:
                raise ProposalNotFound()
            decided = proposal.decide(
                actor_id=actor.user_id,
                expected_version=expected_version,
                decision=decision,
                now=self._clock.now(),
            )
            await self._repository.save(tx, decided)
            return _view(decided)


class ReadProposal:
    def __init__(
        self,
        repository: ProposalRepository,
        sessions: SessionAuthorizer,
        members: WorkspaceMemberReader,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._sessions = sessions
        self._members = members
        self._uow_factory = uow_factory

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
    ) -> ProposalView:
        async with self._uow_factory().transaction() as tx:
            return await self.require_proposal(
                tx, actor=actor, workspace_id=workspace_id, proposal_id=proposal_id
            )

    async def require_proposal(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        proposal_id: ProposalId,
    ) -> ProposalView:
        await self._members.require_member(tx, workspace_id, actor.user_id)
        proposal = await self._repository.find(tx, workspace_id, proposal_id)
        if proposal is None:
            raise ProposalNotFound()
        if actor.user_id not in proposal.required_approvers:
            try:
                await self._sessions.require(
                    tx,
                    actor=actor,
                    workspace_id=workspace_id,
                    session_id=proposal.source_session_id,
                    permission=SessionPermission.READ,
                )
            except NotFound:
                raise ProposalNotFound() from None
        return _view(proposal)
