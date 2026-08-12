"""멀티턴 질문 재작성과 현재 오케스트레이터 통합 테스트.

작성자: 김진우
"""
from __future__ import annotations

import unittest

from app.services.intent_classifier import Intent
from app.services.query_rewriter import (
    ConversationTurn,
    QueryRewriter,
    RewrittenQuery,
    format_history,
    needs_context_rewrite,
    normalize_history,
)
from tests.test_chat_orchestrator import _build_orchestrator, _document


HISTORY = [
    ConversationTurn("user", "고혈압은 어떻게 관리하나요?"),
    ConversationTurn("assistant", "생활습관 관리가 중요합니다."),
]


class FakeChain:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[dict] = []

    def invoke(self, values):
        self.calls.append(values)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class QueryRewriterTest(unittest.TestCase):
    def test_first_turn_skips_llm(self) -> None:
        chain = FakeChain(RuntimeError("호출되면 안 됩니다."))
        result = QueryRewriter(chain).rewrite("고혈압이 뭔가요?", [])
        self.assertFalse(result.rewritten)
        self.assertEqual(chain.calls, [])

    def test_self_contained_follow_up_skips_llm(self) -> None:
        chain = FakeChain(RuntimeError("호출되면 안 됩니다."))
        result = QueryRewriter(chain).rewrite("당뇨병 증상은 무엇인가요?", HISTORY)
        self.assertFalse(result.rewritten)
        self.assertEqual(chain.calls, [])

    def test_context_dependent_question_is_expanded(self) -> None:
        chain = FakeChain(
            RewrittenQuery(
                standalone_question="고혈압 식단 관리 방법은 무엇인가요?",
                rewritten=True,
                reason="직전 주제 복원",
            )
        )
        result = QueryRewriter(chain).rewrite("그럼 식단은요?", HISTORY)
        self.assertTrue(result.rewritten)
        self.assertIn("고혈압", result.question)
        self.assertIn("사용자: 고혈압은", chain.calls[0]["history"])

    def test_failure_falls_back_to_original(self) -> None:
        result = QueryRewriter(FakeChain(RuntimeError("LLM 오류"))).rewrite(
            "그럼 식단은요?",
            HISTORY,
        )
        self.assertEqual(result.question, "그럼 식단은요?")
        self.assertFalse(result.rewritten)
        self.assertIn("RuntimeError", result.error or "")

    def test_history_normalization_and_format(self) -> None:
        turns = normalize_history(
            [{"role": "user", "content": " 안녕 "}, {"role": "system", "content": "제외"}]
        )
        self.assertEqual(format_history(turns), "사용자: 안녕")
        self.assertTrue(needs_context_rewrite("그 약은요?", HISTORY))

    def test_first_turn_never_requests_context_rewrite(self) -> None:
        self.assertFalse(needs_context_rewrite("그거 낮추려면?", []))

    def test_omitted_target_follow_up_requests_rewrite(self) -> None:
        self.assertTrue(needs_context_rewrite("낮추려면 어떻게 해야돼?", HISTORY))
        self.assertTrue(needs_context_rewrite("부작용은?", HISTORY))
        self.assertTrue(needs_context_rewrite("정상범위는?", HISTORY))
        self.assertTrue(needs_context_rewrite("정상 수치는?", HISTORY))
        self.assertTrue(needs_context_rewrite("기준은?", HISTORY))
        self.assertTrue(needs_context_rewrite("단위는?", HISTORY))

    def test_explicit_topic_skips_rewrite(self) -> None:
        self.assertFalse(
            needs_context_rewrite("공복혈당을 낮추려면 어떻게 해야돼?", HISTORY)
        )
        self.assertFalse(
            needs_context_rewrite("당뇨병 증상은 무엇인가요?", HISTORY)
        )

    def test_explicit_screening_acronym_skips_history_rewrite(self) -> None:
        self.assertFalse(
            needs_context_rewrite("나의 HDL 수치가 어떤 편이야?", HISTORY)
        )
        self.assertFalse(
            needs_context_rewrite("나의 LDL 수치가 어떤 편이야?", HISTORY)
        )

    def test_ambiguous_follow_up_is_delegated_to_rewriter(self) -> None:
        self.assertTrue(needs_context_rewrite("어떻게 생각해?", HISTORY))
        self.assertTrue(needs_context_rewrite("낮추려면?", [], "공복혈당을 설명함"))

    def test_omitted_target_is_expanded_from_history(self) -> None:
        chain = FakeChain(
            RewrittenQuery(
                standalone_question="공복혈당을 낮추려면 어떻게 해야 하나요?",
                rewritten=True,
                reason="직전 질문의 공복혈당을 목적어로 복원",
            )
        )
        history = [
            ConversationTurn("user", "공복혈당 정상 범위는 무엇인가요?"),
            ConversationTurn("assistant", "검사 기준에 따라 확인해야 합니다."),
        ]

        result = QueryRewriter(chain).rewrite("낮추려면 어떻게 해야돼?", history)

        self.assertTrue(result.rewritten)
        self.assertEqual(result.question, "공복혈당을 낮추려면 어떻게 해야 하나요?")
        self.assertEqual(len(chain.calls), 1)

    def test_bare_normal_value_is_expanded_from_history(self) -> None:
        chain = FakeChain(
            RewrittenQuery(
                standalone_question="중성지방의 정상 수치는 얼마인가요?",
                rewritten=True,
                reason="직전 질문의 중성지방을 측정 대상으로 복원",
            )
        )
        history = [
            ConversationTurn("user", "중성지방이 뭐야?"),
            ConversationTurn("assistant", "중성지방의 의미를 설명했습니다."),
        ]

        result = QueryRewriter(chain).rewrite("정상 수치는?", history)

        self.assertTrue(result.rewritten)
        self.assertEqual(result.question, "중성지방의 정상 수치는 얼마인가요?")
        self.assertEqual(len(chain.calls), 1)

    def test_new_self_contained_topic_is_not_rewritten_by_llm(self) -> None:
        chain = FakeChain(
            RewrittenQuery(
                standalone_question="오늘 기분은 어때요?",
                rewritten=False,
                reason="새로운 독립 주제",
            )
        )

        result = QueryRewriter(chain).rewrite("오늘 기분 어때?", HISTORY)

        self.assertFalse(result.rewritten)
        self.assertEqual(result.question, "오늘 기분은 어때요?")
        self.assertEqual(len(chain.calls), 1)


class OrchestratorMultiTurnTest(unittest.TestCase):
    def test_rewritten_question_is_used_for_embedding_and_answer(self) -> None:
        orchestrator, vector_search, _, _ = _build_orchestrator(
            Intent.SIMPLE_LOOKUP,
            documents=[_document()],
        )
        orchestrator._query_rewriter = QueryRewriter(
            FakeChain(
                RewrittenQuery(
                    standalone_question="고혈압 식단 관리 방법은 무엇인가요?",
                    rewritten=True,
                    reason="직전 주제 복원",
                )
            )
        )

        result = orchestrator.answer("그럼 식단은요?", HISTORY)

        self.assertEqual(
            vector_search.embedded_questions,
            ["고혈압 식단 관리 방법은 무엇인가요?"],
        )
        self.assertEqual(result.original_question, "그럼 식단은요?")
        self.assertEqual(result.standalone_question, "고혈압 식단 관리 방법은 무엇인가요?")
        self.assertTrue(result.query_rewritten)

    def test_safety_policy_is_merged_without_stopping_rag(self) -> None:
        orchestrator, vector_search, grounded_rag, _ = _build_orchestrator(
            Intent.SIMPLE_LOOKUP,
            documents=[_document()],
        )
        orchestrator._query_rewriter = QueryRewriter(
            FakeChain(
                RewrittenQuery(
                    standalone_question="제가 고혈압인지 진단해 주세요.",
                    rewritten=True,
                    reason="생략된 요청 복원",
                )
            )
        )

        result = orchestrator.answer("그럼 저는 해당되나요?", HISTORY)

        self.assertTrue(result.guard_triggered)
        self.assertEqual(result.intent, Intent.SIMPLE_LOOKUP)
        self.assertEqual(vector_search.search_count, 1)
        self.assertIn("definitive_diagnosis", grounded_rag.safety_policy.restricted_actions)


if __name__ == "__main__":
    unittest.main()
