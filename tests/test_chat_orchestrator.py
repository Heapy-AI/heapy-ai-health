"""Intent 4분기 챗봇 오케스트레이션 단위 테스트.

작성자: 김진우
"""
from __future__ import annotations

import unittest

from langchain_core.documents import Document

from app.core.config import PINECONE_DIMENSION
from app.services.chat_orchestrator import (
    ChatOrchestrator,
    GENERAL_IGNORE_ANSWER,
)
from app.services.grounded_rag import (
    GroundedAnswerResult,
    GroundedRagProgress,
    RetrievalAssessment,
)
from app.services.intent_classifier import Intent, IntentPrediction
from app.services.query_resolver import (
    InMemoryMedicalTermRepository,
    MedicalQueryResolver,
)
from app.services.query_rewriter import QueryRewriter, RewrittenQuery
from app.services.vector_search import MultiCollectionSearchResult


class FakeVectorSearch:
    def __init__(self, documents: list[Document] | None = None) -> None:
        self.documents = documents or []
        self.embed_count = 0
        self.embedded_questions: list[str] = []
        self.search_count = 0

    def embed_query(self, question: str) -> list[float]:
        self.embed_count += 1
        self.embedded_questions.append(question)
        return [0.0] * PINECONE_DIMENSION

    def search_many_by_vector(
        self,
        collections,
        query_vector,
        top_k_per_collection,
    ) -> MultiCollectionSearchResult:
        self.search_count += 1
        return MultiCollectionSearchResult(
            documents=self.documents,
            searched_collections=list(collections),
            errors={},
        )


class FakeClassifier:
    model_version = "intent-v6-test"

    def __init__(self, intent: Intent, *, uncertain: bool = False) -> None:
        self.intent = intent
        self.uncertain = uncertain

    def predict(self, embedding: list[float]) -> IntentPrediction:
        return IntentPrediction(
            intent=self.intent,
            confidence=0.9,
            probabilities={
                label.value: 0.9 if label is self.intent else 0.1 / 3
                for label in Intent
            },
            uncertain=self.uncertain,
            model_version=self.model_version,
        )


class FakeGroundedRagService:
    def __init__(self) -> None:
        self.call_count = 0
        self.safety_policy = None
        self.audit = None
        self.personal_context = ""

    def answer(
        self,
        question,
        documents,
        *,
        safety_policy,
        audit=True,
        personal_context="",
    ):
        self.call_count += 1
        self.safety_policy = safety_policy
        self.audit = audit
        self.personal_context = personal_context
        return GroundedAnswerResult(
            answer="검색 근거 기반 답변",
            grounded=True,
            cited_chunk_ids=["C1"],
            verification_method="retrieval_check_post_audit",
            grounding_errors=[],
            unsupported_claims=[],
            evidence_status="sufficient",
            retrieval_assessment=RetrievalAssessment(
                status="evidence_available",
                eligible=True,
                reason="테스트 근거 있음",
                max_score=0.91,
                query_entities=[],
                matched_entities=[],
            ),
        )

    def stream_answer(
        self,
        question,
        documents,
        *,
        safety_policy,
        audit=True,
        personal_context="",
    ):
        self.call_count += 1
        self.safety_policy = safety_policy
        self.audit = audit
        self.personal_context = personal_context
        yield "검색 근거 "
        yield "기반 답변"
        yield GroundedRagProgress(stage="answer_stream_complete")
        yield GroundedAnswerResult(
            answer="검색 근거 기반 답변",
            grounded=True,
            cited_chunk_ids=["C1"],
            verification_method="retrieval_check_post_audit",
            grounding_errors=[],
            unsupported_claims=[],
            evidence_status="sufficient",
            retrieval_assessment=RetrievalAssessment(
                status="evidence_available",
                eligible=True,
                reason="테스트 근거 있음",
                max_score=0.91,
                query_entities=[],
                matched_entities=[],
            ),
        )


class FakeGeneralChatChain:
    def __init__(self) -> None:
        self.call_count = 0

    def invoke(self, values):
        self.call_count += 1
        return "오늘도 무리하지 말고 천천히 해봐요."

    def stream(self, values):
        self.call_count += 1
        yield "오늘도 무리하지 말고 "
        yield "천천히 해봐요."


class FakeQueryRewriteChain:
    """정해진 독립형 질문을 반환하는 테스트용 재작성 체인."""

    def __init__(self, response: RewrittenQuery) -> None:
        self.response = response

    def invoke(self, _values):
        return self.response


def _document() -> Document:
    return Document(
        page_content="공복혈당은 금식 후 혈액 속 포도당 농도를 측정합니다.",
        metadata={
            "collection": "health_checkup_info",
            "record_id": "FASTING_GLUCOSE",
            "score": 0.91,
        },
    )


def _build_orchestrator(
    intent: Intent,
    *,
    uncertain: bool = False,
    documents: list[Document] | None = None,
):
    vector_search = FakeVectorSearch(documents)
    grounded_rag = FakeGroundedRagService()
    general_chat = FakeGeneralChatChain()
    orchestrator = ChatOrchestrator(
        vector_search=vector_search,
        intent_classifier=FakeClassifier(intent, uncertain=uncertain),
        grounded_rag_service=grounded_rag,
        general_chat_chain=general_chat,
        search_collections=("disease_info", "health_checkup_info"),
        top_k_per_collection=3,
        final_top_k=6,
        max_per_collection=2,
        min_score=0.0,
    )
    return orchestrator, vector_search, grounded_rag, general_chat


class ChatOrchestratorTest(unittest.TestCase):
    def test_simple_lookup_streams_tokens_then_complete_result(self) -> None:
        orchestrator, vector_search, grounded_rag, _ = _build_orchestrator(
            Intent.SIMPLE_LOOKUP,
            documents=[_document()],
        )

        events = list(orchestrator.stream_answer("공복혈당이 뭐야?"))

        self.assertEqual(
            [event.stage for event in events if event.event == "progress"],
            [
                "prepare_query",
                "classify_intent",
                "search_evidence",
                "generate_answer",
                "answer_stream_complete",
                "summarize_conversation",
            ],
        )
        token_events = [event for event in events if event.event == "token"]
        self.assertEqual(
            "".join(event.text for event in token_events),
            events[-1].result.answer,
        )
        self.assertTrue(events[-1].result.grounded)
        self.assertEqual(vector_search.embed_count, 1)
        self.assertEqual(grounded_rag.safety_policy.risk_level.value, "normal")
        self.assertFalse(grounded_rag.audit)

    def test_general_chat_uses_chain_stream(self) -> None:
        orchestrator, vector_search, _, general_chat = _build_orchestrator(
            Intent.GENERAL_CHAT
        )

        events = list(orchestrator.stream_answer("오늘 너무 지쳐"))

        self.assertEqual("".join(event.text for event in events[:-1]), "오늘도 무리하지 말고 천천히 해봐요.")
        self.assertEqual(events[-1].event, "complete")
        self.assertEqual(general_chat.call_count, 1)
        self.assertEqual(vector_search.search_count, 0)

    def test_ignore_stream_does_not_call_llm(self) -> None:
        orchestrator, _, grounded_rag, general_chat = _build_orchestrator(
            Intent.IGNORE
        )

        events = list(orchestrator.stream_answer("오늘 환율 알려줘"))

        token_event = next(event for event in events if event.event == "token")
        self.assertEqual(token_event.text, GENERAL_IGNORE_ANSWER)
        self.assertEqual(events[-1].result.answer, GENERAL_IGNORE_ANSWER)
        self.assertEqual(grounded_rag.call_count, 0)
        self.assertEqual(general_chat.call_count, 0)

    def test_simple_lookup_reuses_one_embedding_and_searches(self) -> None:
        orchestrator, vector_search, grounded_rag, general_chat = (
            _build_orchestrator(Intent.SIMPLE_LOOKUP, documents=[_document()])
        )

        result = orchestrator.answer("공복혈당이 뭐야?")

        self.assertEqual(result.intent, Intent.SIMPLE_LOOKUP)
        self.assertEqual(vector_search.embed_count, 1)
        self.assertEqual(vector_search.search_count, 1)
        self.assertEqual(grounded_rag.safety_policy.risk_level.value, "normal")
        self.assertFalse(grounded_rag.audit)
        self.assertEqual(general_chat.call_count, 0)

    def test_comprehensive_uses_same_retrieval_flow(self) -> None:
        orchestrator, _, grounded_rag, _ = _build_orchestrator(
            Intent.COMPREHENSIVE,
            documents=[_document()],
        )

        result = orchestrator.answer("내 공복혈당 결과를 자세히 분석해줘")

        self.assertEqual(result.intent, Intent.COMPREHENSIVE)
        self.assertEqual(grounded_rag.call_count, 1)
        self.assertFalse(result.personal_context_used)

    def test_comprehensive_combines_personal_context_with_rag(self) -> None:
        orchestrator, _, grounded_rag, _ = _build_orchestrator(
            Intent.COMPREHENSIVE,
            documents=[_document()],
        )

        result = orchestrator.answer(
            "내 AST 수치를 설명해줘",
            personal_context_loader=lambda _question, _terms: (
                "2026-08-06 AST 54 U/L 이상"
            ),
        )

        self.assertTrue(result.personal_context_used)
        self.assertEqual(
            grounded_rag.personal_context,
            "2026-08-06 AST 54 U/L 이상",
        )

    def test_personal_result_promotes_simple_model_result_to_comprehensive(self) -> None:
        orchestrator, _, grounded_rag, _ = _build_orchestrator(
            Intent.SIMPLE_LOOKUP,
            documents=[_document()],
        )

        result = orchestrator.answer(
            "나의 HDL 수치가 어떤 편이야?",
            personal_context_loader=lambda _question, _terms: (
                "2026-08-06 HDL 45 mg/dL 정상"
            ),
        )

        self.assertEqual(result.intent, Intent.COMPREHENSIVE)
        self.assertEqual(result.intent_source, "personal_health_context_override")
        self.assertTrue(result.personal_context_used)
        self.assertEqual(
            grounded_rag.personal_context,
            "2026-08-06 HDL 45 mg/dL 정상",
        )

    def test_personal_checkup_follow_up_loads_context_after_named_rewrite(self) -> None:
        """재작성기가 이름을 사용해도 본인 검진 후속 질문은 RDB를 이어서 조회한다."""
        orchestrator, _, grounded_rag, _ = _build_orchestrator(
            Intent.SIMPLE_LOOKUP,
            documents=[_document()],
        )
        orchestrator._query_rewriter = QueryRewriter(
            FakeQueryRewriteChain(
                RewrittenQuery(
                    standalone_question=(
                        "김민철님의 건강검진 결과에서 주의해야 할 부분들 중에서 "
                        "제일 먼저 관리해야 할 것은 무엇인가요?"
                    ),
                    rewritten=True,
                    reason="직전 개인 검진 결과를 복원",
                )
            )
        )
        history = [
            {"role": "user", "content": "내 건강검진 결과를 전체적으로 설명해줘"},
            {
                "role": "assistant",
                "content": "김민철님의 건강검진 결과에서 주의할 항목을 설명했습니다.",
            },
        ]

        result = orchestrator.answer(
            "그 중에서 제일 먼저 관리해야 할 건 뭐야?",
            history,
            personal_context_loader=lambda _question, _terms: (
                "2026-08-06 감마지티피 83 U/L 이상"
            ),
        )

        self.assertEqual(result.intent, Intent.COMPREHENSIVE)
        self.assertTrue(result.personal_context_used)
        self.assertEqual(
            grounded_rag.personal_context,
            "2026-08-06 감마지티피 83 U/L 이상",
        )

    def test_other_person_checkup_without_personal_history_skips_context(self) -> None:
        """제3자 이름만 있는 첫 질문에는 로그인 사용자의 검진값을 결합하지 않는다."""
        orchestrator, _, _, _ = _build_orchestrator(
            Intent.SIMPLE_LOOKUP,
            documents=[_document()],
        )
        load_count = 0

        def load(_question: str, _terms: list[dict]) -> str:
            nonlocal load_count
            load_count += 1
            return "로그인 사용자의 검진 결과"

        result = orchestrator.answer(
            "홍길동님의 건강검진 결과를 설명해줘",
            personal_context_loader=load,
        )

        self.assertEqual(load_count, 0)
        self.assertFalse(result.personal_context_used)

    def test_personal_context_loader_receives_dictionary_canonical_keys(self) -> None:
        orchestrator, _, _, _ = _build_orchestrator(
            Intent.SIMPLE_LOOKUP,
            documents=[_document()],
        )
        orchestrator._query_resolver = MedicalQueryResolver(
            InMemoryMedicalTermRepository(
                [
                    {
                        "canonical_key": "HDL_CHOLESTEROL",
                        "canonical_name": "HDL 콜레스테롤",
                        "term_type": "SCREENING",
                        "aliases": ["HDL"],
                    }
                ]
            )
        )
        received_terms: list[dict] = []

        def load(_question: str, terms: list[dict]) -> str:
            received_terms.extend(terms)
            return "2026-08-06 HDL 45 mg/dL 정상"

        orchestrator.answer(
            "나의 HDL 수치가 어떤 편이야?",
            personal_context_loader=load,
        )

        self.assertEqual(
            received_terms[0]["canonical_keys"],
            ["HDL_CHOLESTEROL"],
        )

    def test_comprehensive_stream_reports_and_uses_personal_context(self) -> None:
        orchestrator, _, grounded_rag, _ = _build_orchestrator(
            Intent.COMPREHENSIVE,
            documents=[_document()],
        )

        events = list(
            orchestrator.stream_answer(
                "내 AST 수치를 설명해줘",
                personal_context_loader=lambda _question, _terms: (
                    "2026-08-06 AST 54 U/L 이상"
                ),
            )
        )

        progress_stages = [
            event.stage for event in events if event.event == "progress"
        ]
        self.assertIn("load_health_context", progress_stages)
        self.assertTrue(events[-1].result.personal_context_used)
        self.assertEqual(
            grounded_rag.personal_context,
            "2026-08-06 AST 54 U/L 이상",
        )

    def test_general_chat_skips_search(self) -> None:
        orchestrator, vector_search, grounded_rag, general_chat = (
            _build_orchestrator(Intent.GENERAL_CHAT)
        )

        result = orchestrator.answer("요즘 일이 많아서 지쳐")

        self.assertEqual(result.intent, Intent.GENERAL_CHAT)
        self.assertEqual(vector_search.embed_count, 1)
        self.assertEqual(vector_search.search_count, 0)
        self.assertEqual(grounded_rag.call_count, 0)
        self.assertEqual(general_chat.call_count, 1)
        self.assertIsNone(result.grounded)

    def test_ignore_skips_search_and_llm(self) -> None:
        orchestrator, vector_search, grounded_rag, general_chat = (
            _build_orchestrator(Intent.IGNORE)
        )

        result = orchestrator.answer("오늘 환율 알려줘")

        self.assertEqual(result.answer, GENERAL_IGNORE_ANSWER)
        self.assertEqual(vector_search.search_count, 0)
        self.assertEqual(grounded_rag.call_count, 0)
        self.assertEqual(general_chat.call_count, 0)

    def test_safety_guard_keeps_intent_and_rag_but_adds_restrictions(self) -> None:
        orchestrator, vector_search, grounded_rag, general_chat = (
            _build_orchestrator(Intent.SIMPLE_LOOKUP)
        )

        result = orchestrator.answer("이 약을 두 알 먹어도 돼?")

        self.assertTrue(result.guard_triggered)
        self.assertEqual(result.intent, Intent.SIMPLE_LOOKUP)
        self.assertEqual(result.answer, "검색 근거 기반 답변")
        self.assertEqual(vector_search.embed_count, 1)
        self.assertEqual(vector_search.search_count, 1)
        self.assertEqual(grounded_rag.call_count, 1)
        self.assertIn("personalized_prescription", result.restricted_actions)
        self.assertEqual(result.risk_level, "caution")
        self.assertEqual(general_chat.call_count, 0)


if __name__ == "__main__":
    unittest.main()
