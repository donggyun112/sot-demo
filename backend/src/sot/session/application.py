from __future__ import annotations

from sot.document.contracts import DocumentReader
from sot.identity.contracts import Actor
from sot.session.contracts import (
    BranchContext,
    BranchContextReader,
    CreatedSessionResult,
    SessionAuthorizer,
)
from sot.session.domain import (
    Branch,
    CompletedTurnsResult,
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
from sot.session.ports import SessionRepository
from sot.shared.clock import Clock
from sot.shared.ids import BranchId, DocumentId, SessionId, UserId, WorkspaceId
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
    ) -> Session:
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
        if permission is not SessionPermission.READ:
            session.require_open()
        return session


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


class GetSession:
    def __init__(
        self, authorizer: SessionAuthorizer, uow_factory: UnitOfWorkFactory
    ) -> None:
        self._authorizer = authorizer
        self._uow_factory = uow_factory

    async def execute(
        self, actor: Actor, workspace_id: WorkspaceId, session_id: SessionId
    ) -> Session:
        async with self._uow_factory().transaction() as tx:
            return await self._authorizer.require(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                session_id=session_id,
                permission=SessionPermission.READ,
            )


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
            await self._members.require_member(tx, workspace_id, user_id)
            member = SessionMember(workspace_id, session_id, user_id, role)
            await self._repository.add_member(tx, workspace_id, member)
            return member


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
            session = await self._authorizer.require(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                session_id=session_id,
                permission=SessionPermission.MANAGE_MEMBERS,
            )
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
                expected_version=expected_version, messages=messages, now=now
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
