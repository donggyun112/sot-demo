from __future__ import annotations

import pytest

from sot.session.domain import read_transcript

CHATGPT = """AI 로그 분석 검토 노트

You said:
정확 매칭만 vs 정확 매칭 + 임베딩 fallback.

ChatGPT said:
fallback이 정답을 몇 개 더 건지는지 숫자로 나옵니다.
안 건지면 빼면 되고요.

You said:
숫자 먼저.
"""


def test_a_chatgpt_export_becomes_the_exchange_it_was() -> None:
    """The title above the first speaker belongs to whoever spoke first: an
    export that opens with its own heading must not lose it."""
    turns = read_transcript(CHATGPT)

    assert [(turn.role, turn.content) for turn in turns] == [
        (
            "user",
            "AI 로그 분석 검토 노트\n\n정확 매칭만 vs 정확 매칭 + 임베딩 fallback.",
        ),
        (
            "assistant",
            "fallback이 정답을 몇 개 더 건지는지 숫자로 나옵니다.\n안 건지면 빼면 되고요.",
        ),
        ("user", "숫자 먼저."),
    ]


@pytest.mark.parametrize(
    "marker",
    ["## User", "**User:**", "Human:", "### 사용자", "나:", "__you said__"],
    ids=["heading", "bold", "bare", "korean-heading", "korean-bare", "underscored"],
)
def test_the_ways_a_tool_marks_a_speaker(marker: str) -> None:
    turns = read_transcript(f"{marker}\n물어봄\n\n## Assistant\n답함")

    assert [(turn.role, turn.content) for turn in turns] == [
        ("user", "물어봄"),
        ("assistant", "답함"),
    ]


def test_a_file_with_no_speaker_is_one_thing_the_importer_said() -> None:
    """Better a conversation with one long turn than one invented out of
    paragraph breaks: nothing here knows where a turn ended."""
    turns = read_transcript("## 개요\n\n본문 한 줄.\n\n본문 두 줄.")

    assert len(turns) == 1
    assert turns[0].role == "user"
    assert turns[0].content == "## 개요\n\n본문 한 줄.\n\n본문 두 줄."


def test_a_heading_that_is_not_a_speaker_stays_in_the_conversation() -> None:
    # "Overview" is not a speaker, and a transcript full of section headings
    # must not be shredded at every one of them.
    turns = read_transcript("## Assistant\n## Overview\n결론.\n## Colors\n파랑.")

    assert len(turns) == 1
    assert turns[0].role == "assistant"
    assert turns[0].content == "## Overview\n결론.\n## Colors\n파랑."


def test_a_speaker_who_said_nothing_takes_no_turn() -> None:
    # Two markers in a row, and trailing markers, are what a copied export
    # looks like when a message was empty.
    turns = read_transcript("You said:\n\nChatGPT said:\n답함\n\nYou said:\n")

    assert [(turn.role, turn.content) for turn in turns] == [("assistant", "답함")]


def test_an_empty_file_holds_no_conversation() -> None:
    assert read_transcript("   \n\n  ") == ()
