from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID, uuid4

from sot.document.contracts import DocumentReader
from sot.identity.contracts import Actor
from sot.session.contracts import (
    BranchContext,
    BranchContextReader,
    BranchMutationResult,
    BundleSnapshot,
    CitedConversation,
    CitedConversationReader,
    CompletedTurnsAppender,
    CreatedSessionResult,
    FrozenEvidence,
    SessionAuthorizer,
    SessionView,
    ShareableBundleSnapshot,
    ToolRecordReader,
    TranscriptTurn,
)
from sot.session.domain import (
    Attachment,
    Branch,
    Bundle,
    BundleItem,
    CompletedTurnsResult,
    CurationOperation,
    CurationProjection,
    CurationRecord,
    JoinTurns,
    NewTurn,
    Session,
    SessionForbidden,
    SessionMember,
    SessionNotFound,
    SessionPermission,
    SessionRole,
    VersionConflict,
    is_allowed,
)
from sot.session.ports import (
    BundleRepository,
    CurationRepository,
    SessionListQuery,
    SessionRepository,
)
from sot.shared.clock import Clock
from sot.shared.errors import InvalidInput
from sot.shared.ids import (
    BranchId,
    BundleId,
    DocumentId,
    SessionId,
    UserId,
    WorkspaceId,
)
from sot.shared.unit_of_work import TransactionContext, UnitOfWorkFactory
from sot.workspace.contracts import (
    Permission,
    WorkspaceAuthorizer,
    WorkspaceMemberReader,
)


class SessionAccess:
    def __init__(
        self, repository: SessionRepository, members: WorkspaceMemberReader
    ) -> None:
        self._repository = repository
        self._members = members

    async def require(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        permission: SessionPermission,
    ) -> SessionView:
        workspace_member = await self._members.require_member(
            tx, workspace_id, actor.user_id
        )
        member = await self._repository.get_member(
            tx, workspace_id, session_id, actor.user_id
        )
        if member is None:
            raise SessionNotFound()
        if not is_allowed(workspace_member.role, member.role, permission):
            raise SessionForbidden()
        session = await self._repository.load_session(tx, workspace_id, session_id)
        if session is None:
            raise SessionNotFound()
        if permission not in {SessionPermission.READ, SessionPermission.REVOKE_TOSS}:
            session.require_open()
        return SessionView(
            session.id,
            session.workspace_id,
            session.document_id,
            session.created_by,
            session.created_at,
            session.status,
            session.origin.session_id if session.origin else None,
            session.origin.branch_id if session.origin else None,
        )


class BranchAccess:
    def __init__(
        self,
        repository: SessionRepository,
        authorizer: SessionAuthorizer,
        members: WorkspaceMemberReader,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._members = members

    async def read(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        permission: SessionPermission = SessionPermission.READ,
    ) -> BranchContext:
        await self._members.require_member(tx, workspace_id, actor.user_id)
        session_id = await self._repository.session_for_branch(
            tx, workspace_id, branch_id
        )
        if session_id is None:
            raise SessionNotFound()
        session = await self._authorizer.require(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            session_id=session_id,
            permission=permission,
        )
        branch = await self._repository.load_branch(tx, workspace_id, branch_id)
        if branch is None or branch.session_id != session_id:
            raise SessionNotFound()
        return BranchContext(
            workspace_id,
            session_id,
            session.document_id,
            branch_id,
            branch.version,
            branch.turns,
        )


class CreateSession:
    def __init__(
        self,
        repository: SessionRepository,
        authorizer: WorkspaceAuthorizer,
        documents: DocumentReader,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._documents = documents
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> CreatedSessionResult:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.SESSION_CREATE
            )
            await self._documents.require_document(
                tx, actor=actor, workspace_id=workspace_id, document_id=document_id
            )
            now = self._clock.now()
            session = Session.create(workspace_id, document_id, actor.user_id, now)
            branch = Branch.create(workspace_id, session.id, actor.user_id, now)
            await self._repository.create_session(tx, workspace_id, session)
            await self._repository.add_member(
                tx,
                workspace_id,
                SessionMember(
                    workspace_id, session.id, actor.user_id, SessionRole.OWNER
                ),
            )
            await self._repository.create_branch(tx, workspace_id, branch)
            return CreatedSessionResult(session.id, branch.id)


class ForkSession:
    """Continue a conversation you can read, in a session of your own.

    Being sent a session as a viewer leaves you following an argument with
    nowhere to take it: you cannot type in someone else's session, and asking
    them to promote you turns a thought into a negotiation. Forking copies
    the transcript as it stands into a session you own, which is what
    "talking in someone's session" always actually meant.
    """

    def __init__(
        self,
        repository: SessionRepository,
        authorizer: WorkspaceAuthorizer,
        branches: BranchContextReader,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._branches = branches
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        *,
        branch_id: BranchId,
    ) -> CreatedSessionResult:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.SESSION_CREATE
            )
            # Reading the branch is the whole permission check: it proves the
            # branch is in this session and that the actor may read it.
            context = await self._branches.read(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                branch_id=branch_id,
                permission=SessionPermission.READ,
            )
            if context.session_id != session_id:
                raise SessionNotFound()
            source_session = await self._repository.load_session(
                tx, workspace_id, session_id
            )
            source_branch = await self._repository.load_branch(
                tx, workspace_id, branch_id
            )
            if source_session is None or source_branch is None:
                raise SessionNotFound()
            now = self._clock.now()
            session = Session.fork(source_session, branch_id, actor.user_id, now)
            branch = Branch.copy_of(source_branch, session.id, actor.user_id, now)
            await self._repository.create_session(tx, workspace_id, session)
            await self._repository.add_member(
                tx,
                workspace_id,
                SessionMember(
                    workspace_id, session.id, actor.user_id, SessionRole.OWNER
                ),
            )
            await self._repository.create_branch(tx, workspace_id, branch)
            return CreatedSessionResult(session.id, branch.id)


class GetSession:
    def __init__(
        self, authorizer: SessionAuthorizer, uow_factory: UnitOfWorkFactory
    ) -> None:
        self._authorizer = authorizer
        self._uow_factory = uow_factory

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, session_id: SessionId
    ) -> SessionView:
        async with self._uow_factory().transaction() as tx:
            return await self._authorizer.require(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                session_id=session_id,
                permission=SessionPermission.READ,
            )


class ListDocumentSessions:
    def __init__(
        self,
        query: SessionListQuery,
        documents: DocumentReader,
        authorizer: SessionAuthorizer,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._query, self._documents = query, documents
        self._authorizer, self._uow_factory = authorizer, uow_factory

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, document_id: DocumentId
    ) -> tuple[SessionView, ...]:
        async with self._uow_factory().transaction() as tx:
            await self._documents.require_document(
                tx, actor=actor, workspace_id=workspace_id, document_id=document_id
            )
            visible = []
            for session_id in await self._query.list_session_ids(
                tx, workspace_id, document_id
            ):
                try:
                    visible.append(
                        await self._authorizer.require(
                            tx,
                            actor=actor,
                            workspace_id=workspace_id,
                            session_id=session_id,
                            permission=SessionPermission.READ,
                        )
                    )
                except SessionNotFound:
                    continue
            return tuple(visible)


class ListSessionBranches:
    def __init__(
        self,
        query: SessionListQuery,
        authorizer: SessionAuthorizer,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._query, self._authorizer = query, authorizer
        self._uow_factory = uow_factory

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, session_id: SessionId
    ) -> tuple[Branch, ...]:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                session_id=session_id,
                permission=SessionPermission.READ,
            )
            return await self._query.list_branches(tx, workspace_id, session_id)


class ListBranchTurns:
    def __init__(
        self,
        reader: BranchContextReader,
        uow_factory: UnitOfWorkFactory,
        records: ToolRecordReader,
    ) -> None:
        self._reader, self._uow_factory = reader, uow_factory
        self._records = records

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> tuple[TranscriptTurn, ...]:
        async with self._uow_factory().transaction() as tx:
            branch = await self._reader.read(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                branch_id=branch_id,
            )
            # The whole record, arguments and results included: an update
            # you cannot see the agent make is one you have to take on trust,
            # and a run already streams all of it to whoever watched. Holding
            # it back afterwards only made the same session read differently
            # on reload. Curation keeps every tool turn out of bundles, so
            # none of it reaches shared evidence.
            kept: list[TranscriptTurn] = []
            for turn in branch.turns:
                if turn.role != "tool":
                    kept.append(TranscriptTurn(turn))
                    continue
                record = self._records.record(turn.content)
                if record is not None:
                    kept.append(
                        TranscriptTurn(replace(turn, content=record.name), record)
                    )
            return tuple(kept)


class InviteSessionMember:
    def __init__(
        self,
        repository: SessionRepository,
        authorizer: SessionAuthorizer,
        members: WorkspaceMemberReader,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._members = members
        self._uow_factory = uow_factory

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        session_id: SessionId,
        *,
        user_id: UserId,
        role: SessionRole,
    ) -> SessionMember:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                session_id=session_id,
                permission=SessionPermission.MANAGE_MEMBERS,
            )
            # You already hold what you are sending, so this is a mistake
            # rather than an action, and it would only hit the member
            # uniqueness constraint anyway.
            if user_id == actor.user_id:
                raise InvalidInput(
                    "session_member_self", "You already hold this session"
                )
            await self._members.require_member(tx, workspace_id, user_id)
            member = SessionMember(workspace_id, session_id, user_id, role)
            await self._repository.add_member(tx, workspace_id, member)
            return member


class ListSessionMembers:
    """Who this session was sent to. Readable by anyone who can read it."""

    def __init__(
        self,
        repository: SessionRepository,
        authorizer: SessionAuthorizer,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._uow_factory = uow_factory

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, session_id: SessionId
    ) -> tuple[SessionMember, ...]:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                session_id=session_id,
                permission=SessionPermission.READ,
            )
            return await self._repository.list_members(tx, workspace_id, session_id)


class CreateBranch:
    def __init__(
        self,
        repository: SessionRepository,
        authorizer: SessionAuthorizer,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, session_id: SessionId
    ) -> Branch:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                session_id=session_id,
                permission=SessionPermission.EDIT,
            )
            branch = Branch.create(
                workspace_id, session_id, actor.user_id, self._clock.now()
            )
            await self._repository.create_branch(tx, workspace_id, branch)
            return branch


class CloseSession:
    def __init__(
        self,
        repository: SessionRepository,
        authorizer: SessionAuthorizer,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._uow_factory = uow_factory

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, session_id: SessionId
    ) -> None:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                session_id=session_id,
                permission=SessionPermission.MANAGE_MEMBERS,
            )
            session = await self._repository.load_session(tx, workspace_id, session_id)
            if session is None:
                raise SessionNotFound()
            session.close()
            await self._repository.save_session(tx, workspace_id, session)


class VersionGuard:
    def __init__(
        self, repository: SessionRepository, reader: BranchContextReader
    ) -> None:
        self._repository = repository
        self._reader = reader

    async def advance(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        expected_version: int,
    ) -> int:
        await self._reader.read(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            branch_id=branch_id,
            permission=SessionPermission.EDIT,
        )
        version = await self._repository.advance_version(
            tx, workspace_id, branch_id, expected_version=expected_version
        )
        if version is None:
            raise VersionConflict()
        return version


class AppendCompletedTurns:
    def __init__(
        self,
        repository: SessionRepository,
        reader: BranchContextReader,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._reader = reader
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        *,
        expected_version: int,
        messages: tuple[NewTurn, ...],
    ) -> CompletedTurnsResult:
        async with self._uow_factory().transaction() as tx:
            context = await self._reader.read(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                branch_id=branch_id,
                permission=SessionPermission.EDIT,
            )
            now = self._clock.now()
            branch = Branch(
                branch_id,
                workspace_id,
                context.session_id,
                actor.user_id,
                now,
                context.version,
                context.turns,
            )
            result = branch.append_completed(
                author=actor.user_id,
                expected_version=expected_version,
                messages=messages,
                now=now,
            )
            version = await self._repository.advance_version(
                tx, workspace_id, branch_id, expected_version=expected_version
            )
            if version is None:
                raise VersionConflict()
            await self._repository.append_turns(
                tx, workspace_id, branch_id, result.turns
            )
            return result


class AttachToBranch:
    """Bring a file into the conversation.

    It is appended as a turn, which is the only thing that is already all
    four of: visible in the transcript, part of the agent's history, part of
    the evidence a passage written from it cites, and owned by the person who
    brought it. Anything beside the conversation would have to earn each of
    those separately.
    """

    def __init__(self, appender: CompletedTurnsAppender) -> None:
        self._appender = appender

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        *,
        expected_version: int,
        attachments: Sequence[Attachment],
    ) -> CompletedTurnsResult:
        return await self._appender.execute(
            actor,
            workspace_id,
            branch_id,
            expected_version=expected_version,
            messages=tuple(one.as_turn() for one in attachments),
        )


class RequiredApprovers:
    """Called inside an already-authorized proposal command's transaction."""

    def __init__(self, repository: SessionRepository) -> None:
        self._repository = repository

    async def list_required_approvers(
        self,
        tx: TransactionContext,
        *,
        workspace_id: WorkspaceId,
        session_id: SessionId,
    ) -> frozenset[UserId]:
        members = await self._repository.list_members(tx, workspace_id, session_id)
        return frozenset(
            member.user_id
            for member in members
            if member.role in {SessionRole.OWNER, SessionRole.EDITOR}
        )


async def _projection(
    repository: CurationRepository,
    tx: TransactionContext,
    context: BranchContext,
) -> tuple[CurationProjection, int]:
    records = await repository.list_curation(
        tx, context.workspace_id, context.branch_id
    )
    projection = CurationProjection.from_turns(context.turns)
    for record in records:
        projection.apply(record.operation)
    return projection, len(records)


class ApplyCuration:
    def __init__(
        self,
        repository: CurationRepository,
        branches: SessionRepository,
        reader: BranchContextReader,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._branches = branches
        self._reader = reader
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        *,
        expected_version: int,
        operation: CurationOperation,
    ) -> BranchMutationResult:
        async with self._uow_factory().transaction() as tx:
            context = await self._reader.read(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                branch_id=branch_id,
                permission=SessionPermission.EDIT,
            )
            if context.version != expected_version:
                raise VersionConflict()
            projection, count = await _projection(self._repository, tx, context)
            projection.apply(operation)
            version = await self._branches.advance_version(
                tx,
                workspace_id,
                branch_id,
                expected_version=expected_version,
            )
            if version is None:
                raise VersionConflict()
            record = CurationRecord(
                uuid4(),
                branch_id,
                count + 1,
                operation,
                actor.user_id,
                self._clock.now(),
            )
            await self._repository.append_curation(tx, workspace_id, record)
            return BranchMutationResult(record.id, version)

    async def create_from_agent(
        self,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        expected_branch_version: int,
        turn_ids: tuple[UUID, ...],
        summary: str,
    ) -> BranchMutationResult:
        return await self.execute(
            actor,
            workspace_id,
            branch_id,
            expected_version=expected_branch_version,
            operation=JoinTurns(turn_ids, summary),
        )


class PreviewBundle:
    def __init__(
        self,
        repository: CurationRepository,
        reader: BranchContextReader,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._reader = reader
        self._uow_factory = uow_factory

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
    ) -> tuple[BundleItem, ...]:
        async with self._uow_factory().transaction() as tx:
            context = await self._reader.read(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                branch_id=branch_id,
            )
            projection, _ = await _projection(self._repository, tx, context)
            return projection.items


class FreezeEvidence:
    """Answers EvidenceFreezer: the curated conversation, frozen where it is.

    No version is advanced here. The command that proposes the update owns the
    branch version; this only records what that update was written from.
    """

    def __init__(
        self,
        repository: BundleRepository,
        curation: CurationRepository,
        reader: BranchContextReader,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._curation = curation
        self._reader = reader
        self._clock = clock

    async def freeze(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        branch_id: BranchId,
        title: str,
    ) -> FrozenEvidence:
        context = await self._reader.read(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            branch_id=branch_id,
            permission=SessionPermission.PUBLISH_BUNDLE,
        )
        projection, _ = await _projection(self._curation, tx, context)
        now = self._clock.now()
        branch = Branch(branch_id, workspace_id, context.session_id, actor.user_id, now)
        bundle = Bundle.publish(
            branch, projection.items, actor.user_id, now, title=title
        )
        await self._repository.create_bundle(tx, workspace_id, bundle)
        return FrozenEvidence(bundle.id, bundle.items)


class ReadCitedConversation:
    """Open the conversation a citation points at.

    Authorization is the owning session's: a citation is only readable by
    someone who may read the conversation it froze.
    """

    def __init__(
        self, bundles: CitedConversationReader, uow_factory: UnitOfWorkFactory
    ) -> None:
        self._bundles = bundles
        self._uow_factory = uow_factory

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, bundle_id: BundleId
    ) -> CitedConversation:
        async with self._uow_factory().transaction() as tx:
            snapshot = await self._bundles.require_snapshot(
                tx, actor=actor, workspace_id=workspace_id, bundle_id=bundle_id
            )
            session_id = await self._bundles.require_owning_session(
                tx, actor=actor, workspace_id=workspace_id, bundle_id=bundle_id
            )
            return CitedConversation(
                snapshot.bundle_id, snapshot.title, session_id, snapshot.items
            )


class BundleAccess:
    def __init__(
        self,
        repository: BundleRepository,
        authorizer: SessionAuthorizer,
        members: WorkspaceMemberReader,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._members = members

    async def require_revocation(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> None:
        await self._members.require_member(tx, workspace_id, actor.user_id)
        session_id = await self._repository.session_for_bundle(
            tx, workspace_id, bundle_id
        )
        if session_id is None:
            raise SessionNotFound()
        await self._authorizer.require(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            session_id=session_id,
            permission=SessionPermission.REVOKE_TOSS,
        )

    async def require_snapshot(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> BundleSnapshot:
        shareable = await self._require_snapshot(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            bundle_id=bundle_id,
            permission=SessionPermission.READ,
        )
        return shareable.snapshot

    async def require_shareable_snapshot(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> ShareableBundleSnapshot:
        return await self._require_snapshot(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            bundle_id=bundle_id,
            permission=SessionPermission.PUBLISH_BUNDLE,
        )

    async def require_owning_session(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
    ) -> SessionId:
        """Which session this bundle came from, for someone allowed to read it.

        A share link never leaves the workspace, so it resolves to the session
        it curated. Anyone who may not read that session gets not-found.
        """
        await self._members.require_member(tx, workspace_id, actor.user_id)
        session_id = await self._repository.session_for_bundle(
            tx, workspace_id, bundle_id
        )
        if session_id is None:
            raise SessionNotFound()
        await self._authorizer.require(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            session_id=session_id,
            permission=SessionPermission.READ,
        )
        return session_id

    async def _require_snapshot(
        self,
        tx: TransactionContext,
        *,
        actor: Actor,
        workspace_id: WorkspaceId,
        bundle_id: BundleId,
        permission: SessionPermission,
    ) -> ShareableBundleSnapshot:
        await self._members.require_member(tx, workspace_id, actor.user_id)
        session_id = await self._repository.session_for_bundle(
            tx, workspace_id, bundle_id
        )
        if session_id is None:
            raise SessionNotFound()
        await self._authorizer.require(
            tx,
            actor=actor,
            workspace_id=workspace_id,
            session_id=session_id,
            permission=permission,
        )
        bundle = await self._repository.load_bundle(tx, workspace_id, bundle_id)
        if bundle is None or bundle.session_id != session_id:
            raise SessionNotFound()
        return ShareableBundleSnapshot(
            BundleSnapshot(bundle.id, bundle.title, bundle.items, bundle.published_at),
            bundle.published_by,
        )
