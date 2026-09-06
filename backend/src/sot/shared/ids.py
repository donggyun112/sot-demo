from __future__ import annotations

from typing import NewType
from uuid import UUID

UserId = NewType("UserId", UUID)
WorkspaceId = NewType("WorkspaceId", UUID)
DocumentId = NewType("DocumentId", UUID)
SessionId = NewType("SessionId", UUID)
BranchId = NewType("BranchId", UUID)
BundleId = NewType("BundleId", UUID)
ProposalId = NewType("ProposalId", UUID)

__all__ = [
    "BranchId",
    "BundleId",
    "DocumentId",
    "ProposalId",
    "SessionId",
    "UserId",
    "WorkspaceId",
]
