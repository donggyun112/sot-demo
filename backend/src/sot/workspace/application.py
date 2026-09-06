from uuid import uuid4

from sot.identity.contracts import Actor, IdentityReader
from sot.shared.ids import UserId, WorkspaceId
from sot.shared.unit_of_work import TransactionContext, UnitOfWorkFactory
from sot.workspace.contracts import WorkspaceAuthorizer
from sot.workspace.domain import (
    Permission,
    Workspace,
    WorkspaceForbidden,
    WorkspaceMembership,
    WorkspaceNotFound,
    WorkspaceRole,
    permissions_for,
)
from sot.workspace.ports import WorkspaceRepository


class WorkspaceAccess:
    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository

    async def require_member(
        self,
        tx: TransactionContext,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership:
        member = await self._repository.get_member(tx, workspace_id, user_id)
        if member is None:
            raise WorkspaceForbidden()
        return member

    async def require(
        self,
        tx: TransactionContext,
        actor: Actor,
        workspace_id: WorkspaceId,
        permission: Permission,
    ) -> WorkspaceMembership:
        member = await self.require_member(tx, workspace_id, actor.user_id)
        if permission not in permissions_for(member.role):
            raise WorkspaceForbidden()
        return member


class CreateWorkspace:
    def __init__(
        self, repository: WorkspaceRepository, uow_factory: UnitOfWorkFactory
    ) -> None:
        self._repository, self._uow_factory = repository, uow_factory

    async def execute(self, actor: Actor, *, name: str) -> Workspace:
        workspace = Workspace(WorkspaceId(uuid4()), name.strip())
        async with self._uow_factory().transaction() as tx:
            await self._repository.create(tx, workspace)
            await self._repository.add_member(
                tx,
                WorkspaceMembership(workspace.id, actor.user_id, WorkspaceRole.OWNER),
            )
        return workspace


class AddWorkspaceMember:
    def __init__(
        self,
        repository: WorkspaceRepository,
        authorizer: WorkspaceAuthorizer,
        identity: IdentityReader,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._repository, self._authorizer = repository, authorizer
        self._identity, self._uow_factory = identity, uow_factory

    async def execute(
        self,
        actor: Actor,
        workspace_id: WorkspaceId,
        *,
        user_id: UserId,
        role: WorkspaceRole,
    ) -> WorkspaceMembership:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.WORKSPACE_MANAGE
            )
            await self._identity.require_actor(tx, user_id)
            member = WorkspaceMembership(workspace_id, user_id, role)
            await self._repository.add_member(tx, member)
        return member


class ListActorWorkspaces:
    def __init__(
        self, repository: WorkspaceRepository, uow_factory: UnitOfWorkFactory
    ) -> None:
        self._repository, self._uow_factory = repository, uow_factory

    async def execute(self, actor: Actor) -> tuple[Workspace, ...]:
        async with self._uow_factory().transaction() as tx:
            return await self._repository.list_for_user(tx, actor.user_id)


class GetWorkspace:
    def __init__(
        self,
        repository: WorkspaceRepository,
        authorizer: WorkspaceAuthorizer,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._repository, self._authorizer = repository, authorizer
        self._uow_factory = uow_factory

    async def execute(self, actor: Actor, workspace_id: WorkspaceId) -> Workspace:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.DOCUMENT_READ
            )
            workspace = await self._repository.get(tx, workspace_id)
            if workspace is None:
                raise WorkspaceNotFound()
            return workspace
