"""슬라이딩 윈도 + 요약 메모리(Hybrid) 단위 테스트."""
from __future__ import annotations

import unittest

from app.core.config import CHAT_HISTORY_MAX_TURNS, CONVERSATION_SUMMARY_MAX_CHARS
from app.services.conversation_summary import (
    ConversationSummarizer,
    select_evicted_turns,
)
from app.services.query_rewriter import ConversationTurn, QueryRewriter, RewrittenQuery
from app.services.intent_classifier import Intent

from tests.test_query_rewriter import (
    FakeChain,
    HISTORY,
    _orchestrator,
)


def _turns(count: int) -> list[ConversationTurn]:
    return [
        ConversationTurn("user" if index % 2 == 0 else "assistant", f"발화 {index}")
        for index in range(count)
    ]


class EvictionTest(unittest.TestCase):
    def test_nothing_evicted_within_window(self) -> None:
        self.assertEqual(select_evicted_turns(_turns(CHAT_HISTORY_MAX_TURNS)), [])
        self.assertEqual(select_evicted_turns([]), [])

    def test_oldest_turns_are_evicted(self) -> None:
        turns = _turns(CHAT_HISTORY_MAX_TURNS + 2)
        evicted = select_evicted_turns(turns)
        self.assertEqual(len(evicted), 2)
        self.assertEqual(evicted[0].content, "발화 0")
        self.assertEqual(evicted[1].content, "발화 1")


class ConversationSummarizerTest(unittest.TestCase):
    def test_no_eviction_keeps_previous_summary(self) -> None:
        chain = FakeChain("호출되면 안 됨")
        result = ConversationSummarizer(chain).update("기존 요약", [])
        self.assertEqual(chain.calls, [])
        self.assertFalse(result.updated)
        self.assertEqual(result.summary, "기존 요약")

    def test_evicted_turns_are_merged_into_summary(self) -> None:
        chain = FakeChain("사용자는 고혈압이 있고 식단 관리에 관심이 있다.")
        result = ConversationSummarizer(chain).update("", _turns(2))
        self.assertTrue(result.updated)
        self.assertIn("고혈압", result.summary)
        self.assertIn("사용자: 발화 0", chain.calls[0]["evicted"])
        self.assertEqual(chain.calls[0]["previous_summary"], "(없음)")

    def test_previous_summary_is_passed_through(self) -> None:
        chain = FakeChain("갱신된 요약")
        ConversationSummarizer(chain).update("이전 요약", _turns(2))
        self.assertEqual(chain.calls[0]["previous_summary"], "이전 요약")

    def test_summary_is_truncated(self) -> None:
        chain = FakeChain("가" * (CONVERSATION_SUMMARY_MAX_CHARS + 100))
        result = ConversationSummarizer(chain).update("", _turns(2))
        self.assertEqual(len(result.summary), CONVERSATION_SUMMARY_MAX_CHARS)

    def test_failure_keeps_previous_summary(self) -> None:
        """요약은 보조 기능이므로 실패해도 대화를 막지 않는다."""
        chain = FakeChain(RuntimeError("LLM 오류"))
        result = ConversationSummarizer(chain).update("이전 요약", _turns(2))
        self.assertEqual(result.summary, "이전 요약")
        self.assertFalse(result.updated)
        self.assertIn("RuntimeError", result.error or "")

    def test_empty_output_keeps_previous_summary(self) -> None:
        chain = FakeChain("   ")
        result = ConversationSummarizer(chain).update("이전 요약", _turns(2))
        self.assertEqual(result.summary, "이전 요약")
        self.assertFalse(result.updated)


class OrchestratorSummaryTest(unittest.TestCase):
    def _rewriter(self) -> QueryRewriter:
        return QueryRewriter(
            FakeChain(
                RewrittenQuery(
                    standalone_question="고혈압 식단 관리 방법은?",
                    rewritten=True,
                    reason="주제 복원",
                )
            )
        )

    def test_summary_is_passed_to_rewriter(self) -> None:
        rewrite_chain = FakeChain(
            RewrittenQuery(
                standalone_question="고혈압 식단 관리 방법은?",
                rewritten=True,
                reason="요약 참고",
            )
        )
        orchestrator, _, _ = _orchestrator(QueryRewriter(rewrite_chain))
        orchestrator._conversation_summarizer = ConversationSummarizer(
            FakeChain("요약")
        )

        orchestrator.answer("그럼 식단은요?", HISTORY, "사용자는 고혈압이 있다.")

        self.assertEqual(
            rewrite_chain.calls[0]["summary"], "사용자는 고혈압이 있다."
        )

    def test_short_conversation_does_not_call_summarizer(self) -> None:
        """윈도가 넘치기 전에는 요약 LLM을 호출하지 않는다(비용 0)."""
        summary_chain = FakeChain("호출되면 안 됨")
        orchestrator, _, _ = _orchestrator(self._rewriter())
        orchestrator._conversation_summarizer = ConversationSummarizer(summary_chain)

        result = orchestrator.answer("그럼 식단은요?", HISTORY)

        self.assertEqual(summary_chain.calls, [])
        self.assertFalse(result.summary_updated)

    def test_overflowing_conversation_updates_summary(self) -> None:
        summary_chain = FakeChain("사용자는 고혈압 식단에 관심이 있다.")
        orchestrator, _, _ = _orchestrator(self._rewriter())
        orchestrator._conversation_summarizer = ConversationSummarizer(summary_chain)

        long_history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"발화 {index}"}
            for index in range(CHAT_HISTORY_MAX_TURNS)
        ]
        result = orchestrator.answer("그럼 식단은요?", long_history, "이전 요약")

        self.assertEqual(len(summary_chain.calls), 1)
        self.assertTrue(result.summary_updated)
        self.assertEqual(result.conversation_summary, "사용자는 고혈압 식단에 관심이 있다.")

    def test_summary_survives_when_summarizer_absent(self) -> None:
        orchestrator, _, _ = _orchestrator(self._rewriter())
        result = orchestrator.answer("그럼 식단은요?", HISTORY, "이전 요약")
        self.assertEqual(result.conversation_summary, "이전 요약")
        self.assertFalse(result.summary_updated)

    def test_stream_path_carries_summary(self) -> None:
        summary_chain = FakeChain("갱신된 요약")
        orchestrator, _, _ = _orchestrator(self._rewriter())
        orchestrator._conversation_summarizer = ConversationSummarizer(summary_chain)

        long_history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"발화 {index}"}
            for index in range(CHAT_HISTORY_MAX_TURNS)
        ]
        events = list(orchestrator.stream_answer("그럼 식단은요?", long_history, "이전"))

        complete = [event for event in events if event.event == "complete"]
        self.assertEqual(len(complete), 1)
        self.assertEqual(complete[0].result.conversation_summary, "갱신된 요약")
        self.assertTrue(complete[0].result.summary_updated)

    def test_summary_alone_still_triggers_rewrite(self) -> None:
        """이력이 비어도 요약이 있으면 문맥으로 사용한다."""
        rewrite_chain = FakeChain(
            RewrittenQuery(
                standalone_question="고혈압 식단은?", rewritten=True, reason="요약 참고"
            )
        )
        orchestrator, vector_search, _ = _orchestrator(QueryRewriter(rewrite_chain))

        orchestrator.answer("그럼 식단은요?", [], "사용자는 고혈압이 있다.")

        self.assertEqual(len(rewrite_chain.calls), 1)
        self.assertEqual(vector_search.embedded, ["고혈압 식단은?"])


if __name__ == "__main__":
    unittest.main()
