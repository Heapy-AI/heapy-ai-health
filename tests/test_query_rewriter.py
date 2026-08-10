"""멀티턴 질문 재작성과 오케스트레이터 통합 단위 테스트."""
from __future__ import annotations

import unittest

from langchain_core.documents import Document

from app.core.config import CHAT_HISTORY_MAX_CHARS, CHAT_HISTORY_MAX_TURNS, PINECONE_DIMENSION
from app.services.chat_orchestrator import (
    ChatOrchestrator,
    SAFETY_IGNORE_ANSWER,
)
from app.services.grounded_rag import GroundedAnswerResult
from app.services.intent_classifier import Intent, IntentPrediction
from app.services.query_rewriter import (
    ConversationTurn,
    QueryRewriter,
    RewrittenQuery,
    format_history,
    normalize_history,
)
from app.services.vector_search import MultiCollectionSearchResult


class FakeChain:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[dict] = []

    def invoke(self, values):
        self.calls.append(values)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeVectorSearch:
    def __init__(self, documents: list[Document] | None = None) -> None:
        self.documents = documents or []
        self.embedded: list[str] = []

    def embed_query(self, question: str) -> list[float]:
        self.embedded.append(question)
        return [0.0] * PINECONE_DIMENSION

    def search_many_by_vector(self, collections, query_vector, top_k_per_collection):
        return MultiCollectionSearchResult(
            documents=list(self.documents),
            searched_collections=list(collections),
            errors={},
        )


class FakeClassifier:
    model_version = "intent-v6-test"

    def __init__(self, intent: Intent = Intent.SIMPLE_LOOKUP) -> None:
        self.intent = intent

    def predict(self, embedding) -> IntentPrediction:
        return IntentPrediction(
            intent=self.intent,
            confidence=0.95,
            probabilities={item.value: 0.25 for item in Intent},
            uncertain=False,
            model_version=self.model_version,
        )


class FakeGroundedRag:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def _result(self) -> GroundedAnswerResult:
        return GroundedAnswerResult(
            answer="답변",
            grounded=True,
            cited_chunk_ids=["C1"],
            verification_method="prevalidated_post_audit",
            grounding_errors=[],
            unsupported_claims=[],
            audit_status="passed",
            audit_summary="통과",
        )

    def answer(self, question, documents, *, verify_semantics=True):
        self.questions.append(question)
        return self._result()

    def stream_answer(self, question, documents, *, verify_semantics=True):
        self.questions.append(question)
        yield "답변"
        yield self._result()


def _document() -> Document:
    return Document(
        page_content="고혈압 식단은 나트륨을 줄이는 것이 핵심입니다.",
        metadata={
            "collection": "disease_info",
            "record_id": "kdca-1-1",
            "score": 0.8,
            "source_label": "질병관리청",
            "source": "https://example.com",
        },
    )


HISTORY = [
    ConversationTurn("user", "고혈압은 어떻게 관리하나요?"),
    ConversationTurn("assistant", "생활습관 관리가 중요합니다."),
]


class HistoryNormalizationTest(unittest.TestCase):
    def test_keeps_only_recent_turns(self) -> None:
        turns = [
            ConversationTurn("user", f"질문 {index}")
            for index in range(CHAT_HISTORY_MAX_TURNS + 4)
        ]
        normalized = normalize_history(turns)
        self.assertEqual(len(normalized), CHAT_HISTORY_MAX_TURNS)
        self.assertEqual(normalized[-1].content, turns[-1].content)

    def test_drops_empty_and_unknown_roles(self) -> None:
        turns = [
            ConversationTurn("user", "   "),
            ConversationTurn("system", "무시 대상"),
            ConversationTurn("assistant", "정상 발화"),
        ]
        normalized = normalize_history(turns)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].role, "assistant")

    def test_truncates_long_content(self) -> None:
        turns = [ConversationTurn("user", "가" * (CHAT_HISTORY_MAX_CHARS + 200))]
        self.assertEqual(
            len(normalize_history(turns)[0].content), CHAT_HISTORY_MAX_CHARS
        )

    def test_accepts_dict_and_object_turns(self) -> None:
        normalized = normalize_history([{"role": "user", "content": "안녕"}])
        self.assertEqual(normalized[0].content, "안녕")

    def test_format_history_labels_speakers(self) -> None:
        self.assertEqual(
            format_history(HISTORY),
            "사용자: 고혈압은 어떻게 관리하나요?\n챗봇: 생활습관 관리가 중요합니다.",
        )


class QueryRewriterTest(unittest.TestCase):
    def test_first_turn_skips_llm_call(self) -> None:
        chain = FakeChain(RewrittenQuery(standalone_question="x", rewritten=True, reason=""))
        result = QueryRewriter(chain).rewrite("고혈압이 뭔가요?", [])
        self.assertEqual(chain.calls, [])
        self.assertFalse(result.rewritten)
        self.assertEqual(result.question, "고혈압이 뭔가요?")

    def test_follow_up_is_expanded(self) -> None:
        chain = FakeChain(
            RewrittenQuery(
                standalone_question="고혈압 관리를 위한 식단은 어떻게 해야 하나요?",
                rewritten=True,
                reason="대명사 생략 복원",
            )
        )
        result = QueryRewriter(chain).rewrite("그럼 식단은요?", HISTORY)
        self.assertTrue(result.rewritten)
        self.assertEqual(result.original_question, "그럼 식단은요?")
        self.assertIn("고혈압", result.question)
        self.assertIn("사용자: 고혈압은", chain.calls[0]["history"])

    def test_self_contained_question_is_left_alone(self) -> None:
        chain = FakeChain(
            RewrittenQuery(
                standalone_question="당뇨병 증상은 무엇인가요?",
                rewritten=False,
                reason="이미 자족적",
            )
        )
        result = QueryRewriter(chain).rewrite("당뇨병 증상은 무엇인가요?", HISTORY)
        self.assertFalse(result.rewritten)

    def test_llm_failure_falls_back_to_original(self) -> None:
        """재작성은 보조 기능이므로 실패해도 답변을 막지 않는다."""
        chain = FakeChain(RuntimeError("LLM 오류"))
        result = QueryRewriter(chain).rewrite("그럼 식단은요?", HISTORY)
        self.assertEqual(result.question, "그럼 식단은요?")
        self.assertFalse(result.rewritten)
        self.assertIn("RuntimeError", result.error or "")

    def test_empty_rewrite_falls_back_to_original(self) -> None:
        chain = FakeChain(
            RewrittenQuery(standalone_question="   ", rewritten=True, reason="")
        )
        result = QueryRewriter(chain).rewrite("그럼 식단은요?", HISTORY)
        self.assertEqual(result.question, "그럼 식단은요?")
        self.assertFalse(result.rewritten)

    def test_dict_output_is_accepted(self) -> None:
        chain = FakeChain(
            {"standalone_question": "고혈압 식단", "rewritten": True, "reason": "복원"}
        )
        result = QueryRewriter(chain).rewrite("그럼 식단은요?", HISTORY)
        self.assertEqual(result.question, "고혈압 식단")


def _orchestrator(rewriter=None, intent=Intent.SIMPLE_LOOKUP):
    vector_search = FakeVectorSearch([_document()])
    grounded_rag = FakeGroundedRag()
    orchestrator = ChatOrchestrator(
        vector_search=vector_search,
        intent_classifier=FakeClassifier(intent),
        grounded_rag_service=grounded_rag,
        general_chat_chain=FakeChain("일반 대화 답변"),
        search_collections=("disease_info",),
        top_k_per_collection=3,
        final_top_k=6,
        max_per_collection=2,
        min_score=0.0,
        query_rewriter=rewriter,
    )
    return orchestrator, vector_search, grounded_rag


class OrchestratorMultiTurnTest(unittest.TestCase):
    def test_rewritten_question_is_used_for_search_and_answer(self) -> None:
        rewriter = QueryRewriter(
            FakeChain(
                RewrittenQuery(
                    standalone_question="고혈압 식단 관리 방법은 무엇인가요?",
                    rewritten=True,
                    reason="주제 복원",
                )
            )
        )
        orchestrator, vector_search, grounded_rag = _orchestrator(rewriter)

        result = orchestrator.answer("그럼 식단은요?", HISTORY)

        self.assertEqual(vector_search.embedded, ["고혈압 식단 관리 방법은 무엇인가요?"])
        self.assertEqual(grounded_rag.questions, ["고혈압 식단 관리 방법은 무엇인가요?"])
        self.assertEqual(result.original_question, "그럼 식단은요?")
        self.assertEqual(result.search_question, "고혈압 식단 관리 방법은 무엇인가요?")
        self.assertTrue(result.query_rewritten)

    def test_without_history_no_rewrite_happens(self) -> None:
        rewriter = QueryRewriter(FakeChain(RuntimeError("호출되면 안 됨")))
        orchestrator, vector_search, _ = _orchestrator(rewriter)

        result = orchestrator.answer("고혈압이 뭔가요?")

        self.assertEqual(vector_search.embedded, ["고혈압이 뭔가요?"])
        self.assertFalse(result.query_rewritten)

    def test_safety_guard_checks_rewritten_question(self) -> None:
        """재작성으로 비로소 드러나는 개인 진단 요청을 차단한다."""
        rewriter = QueryRewriter(
            FakeChain(
                RewrittenQuery(
                    standalone_question="제가 고혈압인지 진단해 주세요.",
                    rewritten=True,
                    reason="주제 복원",
                )
            )
        )
        orchestrator, vector_search, _ = _orchestrator(rewriter)

        result = orchestrator.answer("그럼 저는 해당되나요?", HISTORY)

        self.assertTrue(result.guard_triggered)
        self.assertEqual(result.answer, SAFETY_IGNORE_ANSWER)
        self.assertEqual(result.intent, Intent.IGNORE)
        self.assertEqual(vector_search.embedded, [])
        self.assertEqual(result.original_question, "그럼 저는 해당되나요?")
        self.assertEqual(result.search_question, "제가 고혈압인지 진단해 주세요.")

    def test_original_question_is_guarded_before_rewrite(self) -> None:
        """원문이 위험하면 재작성을 시도하지 않고 즉시 막는다."""
        rewriter = QueryRewriter(FakeChain(RuntimeError("호출되면 안 됨")))
        orchestrator, _, _ = _orchestrator(rewriter)

        result = orchestrator.answer("내 혈압 기록만 보고 고혈압이라고 진단해줘", HISTORY)

        self.assertTrue(result.guard_triggered)
        self.assertEqual(result.answer, SAFETY_IGNORE_ANSWER)

    def test_rewrite_failure_still_answers(self) -> None:
        rewriter = QueryRewriter(FakeChain(RuntimeError("LLM 오류")))
        orchestrator, vector_search, grounded_rag = _orchestrator(rewriter)

        result = orchestrator.answer("그럼 식단은요?", HISTORY)

        self.assertEqual(vector_search.embedded, ["그럼 식단은요?"])
        self.assertEqual(result.answer, "답변")
        self.assertFalse(result.query_rewritten)
        self.assertIn("RuntimeError", result.rewrite_error or "")

    def test_stream_path_uses_rewritten_question(self) -> None:
        rewriter = QueryRewriter(
            FakeChain(
                RewrittenQuery(
                    standalone_question="고혈압 식단 관리 방법은 무엇인가요?",
                    rewritten=True,
                    reason="주제 복원",
                )
            )
        )
        orchestrator, vector_search, grounded_rag = _orchestrator(rewriter)

        events = list(orchestrator.stream_answer("그럼 식단은요?", HISTORY))

        self.assertEqual(vector_search.embedded, ["고혈압 식단 관리 방법은 무엇인가요?"])
        self.assertEqual(grounded_rag.questions, ["고혈압 식단 관리 방법은 무엇인가요?"])
        complete = [event for event in events if event.event == "complete"]
        self.assertEqual(len(complete), 1)
        self.assertTrue(complete[0].result.query_rewritten)

    def test_general_chat_path_carries_rewrite_metadata(self) -> None:
        rewriter = QueryRewriter(
            FakeChain(
                RewrittenQuery(
                    standalone_question="오늘 기분이 어떤지 물어봤어요",
                    rewritten=True,
                    reason="복원",
                )
            )
        )
        orchestrator, _, _ = _orchestrator(rewriter, intent=Intent.GENERAL_CHAT)

        result = orchestrator.answer("그건 왜?", HISTORY)

        self.assertTrue(result.query_rewritten)
        self.assertEqual(result.original_question, "그건 왜?")


if __name__ == "__main__":
    unittest.main()
