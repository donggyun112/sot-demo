import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import AgentInfo, FunctionModel


@pytest.mark.asyncio
async def test_native_fallback_uses_next_model_after_model_api_error() -> None:
    calls: list[str] = []

    def primary(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        calls.append("primary")
        raise ModelAPIError("primary", "unavailable")

    def fallback(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        calls.append("fallback")
        return ModelResponse(parts=[TextPart("ok")], model_name="fallback")

    model = FallbackModel(
        FunctionModel(primary, model_name="primary"),
        FunctionModel(fallback, model_name="fallback"),
    )
    result = await Agent(model).run("hello")

    assert result.output == "ok"
    assert calls == ["primary", "fallback"]


@pytest.mark.asyncio
async def test_native_fallback_does_not_catch_arbitrary_errors() -> None:
    fallback_calls = 0

    def primary(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise RuntimeError("tool-side failure")

    def fallback(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        nonlocal fallback_calls
        fallback_calls += 1
        return ModelResponse(parts=[TextPart("unexpected")], model_name="fallback")

    model = FallbackModel(
        FunctionModel(primary, model_name="primary"),
        FunctionModel(fallback, model_name="fallback"),
    )

    with pytest.raises(RuntimeError, match="tool-side failure"):
        await Agent(model).run("hello")
    assert fallback_calls == 0
