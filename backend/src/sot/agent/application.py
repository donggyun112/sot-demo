from dataclasses import dataclass

from sot.agent.deps import (
    AgentDeps,
    BranchLineage,
    DocumentFetcher,
    DocumentSnapshot,
)
from sot.consensus.contracts import ProposalCreator
from sot.document.contracts import DocumentReader
from sot.identity.contracts import Actor
from sot.session.contracts import (
    BranchContextReader,
    CiteCreator,
    CompletedTurnsAppender,
    CompletedTurnsResult,
    NewTurn,
    SessionPermission,
    Turn,
)
from sot.shared.ids import BranchId, WorkspaceId
from sot.shared.unit_of_work import UnitOfWorkFactory
from sot.workspace.contracts import Permission, WorkspaceAuthorizer


@dataclass(frozen=True, slots=True)
class PreparedAgentRun:
    canonical_turns: tuple[Turn, ...]
    deps: AgentDeps

    @property
    def lineage(self) -> BranchLineage:
        return self.deps.lineage


class AgentRunPreparer:
    def __init__(
        self,
        authorizer: WorkspaceAuthorizer,
        reader: BranchContextReader,
        uow_factory: UnitOfWorkFactory,
        cite_creator: CiteCreator,
        proposal_creator: ProposalCreator,
        documents: DocumentReader,
        document_reader: DocumentFetcher,
    ) -> None:
        self._authorizer = authorizer
        self._reader = reader
        self._uow_factory = uow_factory
        self._cite_creator = cite_creator
        self._proposal_creator = proposal_creator
        self._documents = documents
        self._document_reader = document_reader

    async def prepare(
        self, *, actor: Actor, workspace_id: WorkspaceId, branch_id: BranchId
    ) -> PreparedAgentRun:
        async with self._uow_factory().transaction() as tx:
            await self._authorizer.require(
                tx, actor, workspace_id, Permission.SESSION_PARTICIPATE
            )
            context = await self._reader.read(
                tx,
                actor=actor,
                workspace_id=workspace_id,
                branch_id=branch_id,
                permission=SessionPermission.EDIT,
            )
            # Read here: the same transaction already proved this actor may
            # see the session, and the snapshot has to match the revision the
            # run's edits will be anchored against.
            document = None
            if context.document_id is not None:
                view = await self._documents.require_document(
                    tx,
                    actor=actor,
                    workspace_id=workspace_id,
                    document_id=context.document_id,
                )
                document = DocumentSnapshot.of(
                    view.document.id,
                    view.document.title,
                    view.current_revision.number,
                    view.current_revision.content,
                )
        # Mapping and all model work happen after this read transaction closes.
        #
        # An imported conversation's tool records stay in the transcript and
        # out of the history: they are another agent's calls to tools this one
        # does not have, and half of them were interrupted before they
        # returned. The conversation is what this model reads.
        turns = (
            tuple(turn for turn in context.turns if turn.role != "tool")
            if context.imported
            else context.turns
        )
        return PreparedAgentRun(
            turns,
            AgentDeps(
                actor,
                workspace_id,
                branch_id,
                BranchLineage(context.version),
                self._cite_creator,
                self._proposal_creator,
                document=document,
                document_reader=self._document_reader,
            ),
        )


class CompletedRunWriter:
    def __init__(self, appender: CompletedTurnsAppender) -> None:
        self._appender = appender

    async def write(
        self, deps: AgentDeps, *, messages: tuple[NewTurn, ...]
    ) -> CompletedTurnsResult:
        result = await self._appender.execute(
            deps.actor,
            deps.workspace_id,
            deps.branch_id,
            expected_version=deps.lineage.expected_version,
            messages=messages,
        )
        deps.lineage.advance_to(result.branch_version)
        return result

    async def execute(
        self, deps: AgentDeps, *, messages: tuple[NewTurn, ...]
    ) -> CompletedTurnsResult:
        """Compatibility alias for Task 1 callers; new lifecycle code uses write()."""
        return await self.write(deps, messages=messages)
