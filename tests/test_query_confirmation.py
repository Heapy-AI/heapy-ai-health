"""의료용어 확인 상태와 오케스트레이터 통합 테스트.

작성자: 김진우
"""
from __future__ import annotations

import unittest

from app.services.intent_classifier import Intent
from app.services.query_confirmation import QueryConfirmationStore
from app.services.query_rewriter import QueryRewriter, RewrittenQuery
from tests.test_chat_orchestrator import _build_orchestrator, _document
from tests.test_query_resolver import _resolver
from tests.test_query_rewriter import FakeChain, HISTORY


class QueryConfirmationTest(unittest.TestCase):
    def _orchestrator(self):
        orchestrator, vector_search, _, _ = _build_orchestrator(
            Intent.SIMPLE_LOOKUP,
            documents=[_document()],
        )
        orchestrator._query_resolver = _resolver()
        orchestrator._confirmation_store = QueryConfirmationStore()
        return orchestrator, vector_search

    def test_confirmation_suspends_embedding_and_search(self) -> None:
        orchestrator, vector_search = self._orchestrator()

        result = orchestrator.answer("당뇨뼝 증상")

        self.assertTrue(result.query_confirmation)
        self.assertTrue(result.confirmation_id)
        self.assertEqual(result.resolution_status, "CONFIRM")
        self.assertEqual(vector_search.embed_count, 0)
        self.assertEqual(vector_search.search_count, 0)

    def test_yes_consumes_candidate_without_fuzzy_search_again(self) -> None:
        orchestrator, vector_search = self._orchestrator()
        first = orchestrator.answer("당뇨뼝 증상")

        second = orchestrator.answer(
            "당뇨뼝 증상",
            confirmation_id=first.confirmation_id,
            confirmation_answer=True,
        )

        self.assertFalse(second.query_confirmation)
        self.assertEqual(second.resolved_query, "당뇨병 증상")
        self.assertEqual(vector_search.embedded_questions, ["당뇨병 증상"])
        self.assertEqual(second.resolved_terms[0]["match_kind"], "confirmed")

    def test_confirmation_id_is_single_use(self) -> None:
        orchestrator, _ = self._orchestrator()
        first = orchestrator.answer("당뇨뼝 증상")
        orchestrator.answer(
            "당뇨뼝 증상",
            confirmation_id=first.confirmation_id,
            confirmation_answer=True,
        )

        reused = orchestrator.answer(
            "당뇨뼝 증상",
            confirmation_id=first.confirmation_id,
            confirmation_answer=True,
        )

        self.assertEqual(reused.resolution_status, "CONFIRMATION_EXPIRED")
        self.assertEqual(reused.verification_method, "query_confirmation_expired")

    def test_resolver_failure_falls_back_to_original_question(self) -> None:
        class FailingResolver:
            def resolve(self, question: str):
                raise RuntimeError("RDB 연결 실패")

        orchestrator, vector_search = self._orchestrator()
        orchestrator._query_resolver = FailingResolver()

        result = orchestrator.answer("당뇨병 증상")

        self.assertEqual(vector_search.embedded_questions, ["당뇨병 증상"])
        self.assertIn("RuntimeError", result.resolution_error or "")

    def test_rewrite_runs_before_medical_term_normalization(self) -> None:
        orchestrator, vector_search = self._orchestrator()
        orchestrator._query_rewriter = QueryRewriter(
            FakeChain(
                RewrittenQuery(
                    standalone_question="부루펜 부작용은?",
                    rewritten=True,
                    is_follow_up=True,
                    current_topic="부루펜 부작용",
                    inherited_target="부루펜",
                    personal_context_required=False,
                    reason="그 약의 대상을 복원",
                )
            )
        )

        result = orchestrator.answer("그 약 부작용은?", HISTORY)

        self.assertEqual(result.standalone_question, "부루펜 부작용은?")
        self.assertEqual(result.resolved_query, "이부프로펜 부작용은?")
        self.assertEqual(vector_search.embedded_questions, ["이부프로펜 부작용은?"])


if __name__ == "__main__":
    unittest.main()
