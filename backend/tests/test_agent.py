from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import AgentInfo, FunctionModel

from sot.agent import build_model


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
