from dataclasses import dataclass

from sot.consensus.contracts import ProposalCreator
from sot.identity.contracts import Actor
from sot.session.contracts import CiteCreator
from sot.shared.ids import BranchId, WorkspaceId


@dataclass(slots=True)
class BranchLineage:
    expected_version: int

    def advance_to(self, version: int) -> None:
        if version <= self.expected_version:
            raise ValueError("branch version must increase")
        self.expected_version = version


@dataclass(frozen=True, slots=True)
class AgentDeps:
    actor: Actor
    workspace_id: WorkspaceId
    branch_id: BranchId
    lineage: BranchLineage
    cite_creator: CiteCreator
    proposal_creator: ProposalCreator
