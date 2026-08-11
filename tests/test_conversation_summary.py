"""슬라이딩 윈도와 대화 요약 통합 테스트.

작성자: 김진우
"""
from __future__ import annotations

import unittest

from app.core.config import CHAT_HISTORY_MAX_TURNS, CONVERSATION_SUMMARY_MAX_CHARS
from app.services.conversation_summary import (
    ConversationSummarizer,
    select_evicted_turns,
)
from app.services.intent_classifier import Intent
from app.services.query_rewriter import ConversationTurn
from tests.test_chat_orchestrator import _build_orchestrator, _document
from tests.test_query_rewriter import FakeChain


def _turns(count: int) -> list[ConversationTurn]:
    return [
        ConversationTurn("user" if index % 2 == 0 else "assistant", f"발화 {index}")
        for index in range(count)
    ]


class ConversationSummarizerTest(unittest.TestCase):
    def test_selects_only_evicted_turns(self) -> None:
        self.assertEqual(select_evicted_turns(_turns(CHAT_HISTORY_MAX_TURNS)), [])
        evicted = select_evicted_turns(_turns(CHAT_HISTORY_MAX_TURNS + 2))
        self.assertEqual([turn.content for turn in evicted], ["발화 0", "발화 1"])

    def test_no_eviction_keeps_previous_summary(self) -> None:
        chain = FakeChain("호출되면 안 됩니다.")
        result = ConversationSummarizer(chain).update("기존 요약", [])
        self.assertEqual(chain.calls, [])
        self.assertEqual(result.summary, "기존 요약")

    def test_failure_keeps_previous_summary(self) -> None:
        result = ConversationSummarizer(FakeChain(RuntimeError("LLM 오류"))).update(
            "기존 요약",
            _turns(2),
        )
        self.assertEqual(result.summary, "기존 요약")
        self.assertFalse(result.updated)

    def test_summary_is_truncated(self) -> None:
        result = ConversationSummarizer(
            FakeChain("가" * (CONVERSATION_SUMMARY_MAX_CHARS + 100))
        ).update("", _turns(2))
        self.assertEqual(len(result.summary), CONVERSATION_SUMMARY_MAX_CHARS)

    def test_orchestrator_updates_summary_after_answer(self) -> None:
        orchestrator, _, _, _ = _build_orchestrator(
            Intent.SIMPLE_LOOKUP,
            documents=[_document()],
        )
        summary_chain = FakeChain("사용자는 혈압 관리에 관심이 있습니다.")
        orchestrator._conversation_summarizer = ConversationSummarizer(summary_chain)
        history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"발화 {index}"}
            for index in range(CHAT_HISTORY_MAX_TURNS)
        ]

        result = orchestrator.answer("공복혈당이 뭐야?", history, "기존 요약")

        self.assertTrue(result.summary_updated)
        self.assertEqual(result.conversation_summary, "사용자는 혈압 관리에 관심이 있습니다.")
        self.assertEqual(len(summary_chain.calls), 1)


if __name__ == "__main__":
    unittest.main()
