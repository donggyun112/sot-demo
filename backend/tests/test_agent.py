from uuid import UUID

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from sot.domain.models import NewTurn, ProposalStatus
from sot.domain.service import SOTService
from sot.legacy_agent import AgentDeps, build_agent, build_model
from sot.store.memory import MemorySOTRepository


def _response(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("ok")], model_name="test")


def test_build_model_uses_one_reference_directly() -> None:
    assert build_model(("openai:gpt-5",)) == "openai:gpt-5"


def test_build_model_preserves_fallback_order() -> None:
    primary = FunctionModel(_response, model_name="primary")
    secondary = FunctionModel(_response, model_name="secondary")

    model = build_model((primary, secondary))

    assert isinstance(model, FallbackModel)
    assert model.models == [primary, secondary]


def test_build_model_rejects_empty_chain() -> None:
    try:
        build_model(())
    except ValueError as error:
        assert str(error) == "at least one model is required"
    else:
        raise AssertionError("empty model chain was accepted")


def test_build_model_keeps_local_test_runs_text_only() -> None:
    model = build_model(("test",))

    assert isinstance(model, TestModel)
    assert model.call_tools == []


def _tool_model(tool_name: str, args: dict[str, object]) -> FunctionModel:
    calls = 0

    def response(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        assert {tool.name for tool in info.function_tools} == {
            "session_cite",
            "sot_update",
        }
        calls += 1
        if calls == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name, args, "server-tool-call")],
                model_name="test",
            )
        return ModelResponse(parts=[TextPart("done")], model_name="test")

    return FunctionModel(response, model_name="test")


async def _branch(
    *, owner_id: str = "alice"
) -> tuple[SOTService, UUID, UUID, tuple[UUID, ...]]:
    service = SOTService(MemorySOTRepository())
    document = await service.create_document(
        actor_id="alice", title="문서", content="초기"
    )
    session = await service.create_session(
        document_id=document.id, owner_id=owner_id, title="검토"
    )
    turns = await service.append_turns(
        branch_id=session.branch.id,
        actor_id=owner_id,
        turns=(NewTurn(role="user", content="이 결정을 기록해줘"),),
    )
    return (
        service,
        session.session.id,
        session.branch.id,
        tuple(turn.id for turn in turns),
    )


@pytest.mark.asyncio
async def test_session_cite_uses_authenticated_actor_and_routed_branch() -> None:
    service, session_id, branch_id, turn_ids = await _branch()
    agent = build_agent(
        _tool_model(
            "session_cite",
            {"turn_ids": [str(turn_id) for turn_id in turn_ids], "summary": "결정"},
        )
    )

    await agent.run(
        "선택한 대화를 인용해",
        deps=AgentDeps(user_id="alice", branch_id=branch_id, service=service),
    )

    detail = await service.session_detail(session_id=session_id, actor_id="alice")
    assert len(detail.cites) == 1
    assert detail.cites[0].branch_id == branch_id
    assert detail.cites[0].created_by == "alice"
    assert detail.cites[0].turn_ids == turn_ids


@pytest.mark.asyncio
async def test_sot_update_creates_open_proposal_for_routed_branch() -> None:
    service, session_id, branch_id, _turn_ids = await _branch(owner_id="bob")
    agent = build_agent(_tool_model("sot_update", {"content": "새 합의 내용"}))

    await agent.run(
        "SOT를 갱신해",
        deps=AgentDeps(user_id="bob", branch_id=branch_id, service=service),
    )

    detail = await service.session_detail(session_id=session_id, actor_id="bob")
    assert len(detail.proposals) == 1
    assert detail.proposals[0].branch_id == branch_id
    assert detail.proposals[0].created_by == "bob"
    assert detail.proposals[0].status is ProposalStatus.OPEN
