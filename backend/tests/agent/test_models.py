import pytest
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.test import TestModel

from sot.agent.models import build_model


def test_build_model_uses_one_reference_directly() -> None:
    assert build_model(("openai:gpt-5.2",)) == "openai:gpt-5.2"


def test_build_model_preserves_fallback_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unit-test")
    model = build_model(("openai:gpt-5.2", "anthropic:claude-sonnet-4-5"))
    assert isinstance(model, FallbackModel)
    assert [f"{item.system}:{item.model_name}" for item in model.models] == [
        "openai:gpt-5.2",
        "anthropic:claude-sonnet-4-5",
    ]


def test_build_model_rejects_empty_chain() -> None:
    with pytest.raises(ValueError, match="at least one model"):
        build_model(())


def test_build_model_keeps_local_test_runs_text_only() -> None:
    model = build_model(("test",))
    assert isinstance(model, TestModel)
    assert model.call_tools == []
