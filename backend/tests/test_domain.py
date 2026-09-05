import pytest

from sot.domain.errors import DomainError
from sot.domain.models import NewTurn, ProposalStatus
from sot.domain.service import SOTService
from sot.store.memory import MemorySOTRepository


@pytest.mark.asyncio
async def test_draft_to_main_requires_two_distinct_approvals() -> None:
    service = SOTService(MemorySOTRepository())
    document = await service.create_document(
        actor_id="alice",
        title="요청 제한 토큰",
        content="초기 합의",
    )
    initial = await service.current_revision(document.id)
    session_view = await service.create_session(
        document_id=document.id,
        owner_id="alice",
        title="레이트리밋 검토",
    )
    alice_turns = await service.append_turns(
        branch_id=session_view.branch.id,
        actor_id="alice",
        turns=(
            NewTurn(role="assistant", content="격리 수준은 A와 B가 있습니다."),
            NewTurn(role="user", content="B"),
        ),
    )
    cite = await service.create_cite(
        branch_id=session_view.branch.id,
        actor_id="alice",
        turn_ids=tuple(turn.id for turn in alice_turns),
        summary="프로세스 격리를 선택함",
    )
    toss = await service.create_toss(cite_id=cite.id, actor_id="alice")
    bob_branch = await service.fork_toss(token=toss.token, actor_id="bob")
    proposal = await service.create_proposal(
        branch_id=bob_branch.id,
        actor_id="bob",
        content="각 사용자 작업은 별도 프로세스로 격리한다.",
    )

    first = await service.approve_proposal(proposal_id=proposal.id, actor_id="bob")

    assert first.proposal.status is ProposalStatus.OPEN
    assert first.revision is None
    assert (await service.current_revision(document.id)).id == initial.id

    second = await service.approve_proposal(
        proposal_id=proposal.id,
        actor_id="alice",
    )

    assert second.proposal.status is ProposalStatus.PUBLISHED
    assert second.revision is not None
    assert second.revision.number == 2
    assert second.revision.content == "각 사용자 작업은 별도 프로세스로 격리한다."
    assert (await service.current_revision(document.id)).id == second.revision.id


@pytest.mark.asyncio
async def test_branch_mutation_is_limited_to_its_owner() -> None:
    service = SOTService(MemorySOTRepository())
    document = await service.create_document(
        actor_id="alice", title="문서", content="초기"
    )
    session = await service.create_session(
        document_id=document.id,
        owner_id="alice",
        title="검토",
    )

    with pytest.raises(DomainError, match="branch_forbidden") as caught:
        await service.append_turns(
            branch_id=session.branch.id,
            actor_id="bob",
            turns=(NewTurn(role="user", content="침범"),),
        )

    assert caught.value.code == "branch_forbidden"


@pytest.mark.asyncio
async def test_cite_rejects_turn_from_another_branch() -> None:
    service = SOTService(MemorySOTRepository())
    document = await service.create_document(
        actor_id="alice", title="문서", content="초기"
    )
    left = await service.create_session(
        document_id=document.id, owner_id="alice", title="왼쪽"
    )
    right = await service.create_session(
        document_id=document.id, owner_id="alice", title="오른쪽"
    )
    foreign_turn = (
        await service.append_turns(
            branch_id=right.branch.id,
            actor_id="alice",
            turns=(NewTurn(role="user", content="다른 분기"),),
        )
    )[0]

    with pytest.raises(DomainError, match="cite_turn_mismatch") as caught:
        await service.create_cite(
            branch_id=left.branch.id,
            actor_id="alice",
            turn_ids=(foreign_turn.id,),
            summary="잘못된 인용",
        )

    assert caught.value.code == "cite_turn_mismatch"


@pytest.mark.asyncio
async def test_duplicate_approval_is_rejected() -> None:
    service = SOTService(MemorySOTRepository())
    document = await service.create_document(
        actor_id="alice", title="문서", content="초기"
    )
    session = await service.create_session(
        document_id=document.id, owner_id="alice", title="검토"
    )
    proposal = await service.create_proposal(
        branch_id=session.branch.id,
        actor_id="alice",
        content="새 합의",
    )
    await service.approve_proposal(proposal_id=proposal.id, actor_id="alice")

    with pytest.raises(DomainError, match="approval_duplicate") as caught:
        await service.approve_proposal(proposal_id=proposal.id, actor_id="alice")

    assert caught.value.code == "approval_duplicate"
