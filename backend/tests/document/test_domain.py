from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sot.document.domain import (
    Document,
    RevisionCitationInput,
    VersionConflict,
)
from sot.shared.ids import BundleId, ProposalId, UserId, WorkspaceId

NOW = datetime(2026, 9, 6, tzinfo=UTC)


def test_document_publication_rejects_a_stale_expected_version() -> None:
    actor_id = UserId(uuid4())
    document = Document.create(WorkspaceId(uuid4()), actor_id, "Policy")
    document.initialize("revision one", actor_id, NOW)

    with pytest.raises(VersionConflict):
        document.publish(
            content="revision two",
            proposal_id=ProposalId(uuid4()),
            citations=(RevisionCitationInput("claim-1", BundleId(uuid4()), 0),),
            actor_id=actor_id,
            expected_version=0,
            now=NOW,
        )

    assert document.version == 1


def test_revisions_are_immutable_numbered_from_one_and_advance_main() -> None:
    actor_id = UserId(uuid4())
    document = Document.create(WorkspaceId(uuid4()), actor_id, "Policy")
    first = document.initialize("one", actor_id, NOW)
    second = document.publish(
        content="two",
        proposal_id=ProposalId(uuid4()),
        citations=(),
        actor_id=actor_id,
        expected_version=document.version,
        now=NOW,
    )

    assert (first.number, second.number) == (1, 2)
    assert document.current_revision_id == second.id
    assert document.version == 2
    with pytest.raises(FrozenInstanceError):
        second.content = "changed"  # type: ignore[misc]


def test_published_revision_materializes_immutable_citations() -> None:
    actor_id = UserId(uuid4())
    document = Document.create(WorkspaceId(uuid4()), actor_id, "Policy")
    document.initialize("one", actor_id, NOW)
    source = RevisionCitationInput("claim-1", BundleId(uuid4()), 3)

    revision = document.publish(
        content="two",
        proposal_id=ProposalId(uuid4()),
        citations=(source,),
        actor_id=actor_id,
        expected_version=1,
        now=NOW,
    )

    assert revision.citations[0].revision_id == revision.id
    assert revision.citations[0].claim_anchor == "claim-1"
    assert revision.citations[0].bundle_id == source.bundle_id
    assert revision.citations[0].bundle_item_position == 3
