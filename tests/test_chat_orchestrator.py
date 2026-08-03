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
    SAFETY_IGNORE_ANSWER,
)
from app.services.grounded_rag import GroundedAnswerResult
from app.services.intent_classifier import Intent, IntentPrediction
from app.services.vector_search import MultiCollectionSearchResult


class FakeVectorSearch:
    def __init__(self, documents: list[Document] | None = None) -> None:
        self.documents = documents or []
        self.embed_count = 0
        self.search_count = 0

    def embed_query(self, question: str) -> list[float]:
        self.embed_count += 1
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
        self.verify_semantics = None

    def answer(self, question, documents, *, verify_semantics):
        self.call_count += 1
        self.verify_semantics = verify_semantics
        return GroundedAnswerResult(
            answer="검색 근거 기반 답변 [C1]",
            grounded=True,
            cited_chunk_ids=["C1"],
            verification_method=(
                "llm_verified" if verify_semantics else "citation_only"
            ),
            grounding_errors=[],
            unsupported_claims=[],
        )


class FakeGeneralChatChain:
    def __init__(self) -> None:
        self.call_count = 0

    def invoke(self, values):
        self.call_count += 1
        return "오늘도 무리하지 말고 천천히 해봐요."


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
    def test_simple_lookup_reuses_one_embedding_and_searches(self) -> None:
        orchestrator, vector_search, grounded_rag, general_chat = (
            _build_orchestrator(Intent.SIMPLE_LOOKUP, documents=[_document()])
        )

        result = orchestrator.answer("공복혈당이 뭐야?")

        self.assertEqual(result.intent, Intent.SIMPLE_LOOKUP)
        self.assertEqual(vector_search.embed_count, 1)
        self.assertEqual(vector_search.search_count, 1)
        self.assertFalse(grounded_rag.verify_semantics)
        self.assertEqual(general_chat.call_count, 0)

    def test_comprehensive_uses_semantic_verification(self) -> None:
        orchestrator, _, grounded_rag, _ = _build_orchestrator(
            Intent.COMPREHENSIVE,
            documents=[_document()],
        )

        result = orchestrator.answer("내 공복혈당 결과를 자세히 분석해줘")

        self.assertEqual(result.intent, Intent.COMPREHENSIVE)
        self.assertTrue(grounded_rag.verify_semantics)
        self.assertFalse(result.personal_context_used)

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

    def test_safety_guard_skips_embedding_classifier_and_llm(self) -> None:
        orchestrator, vector_search, grounded_rag, general_chat = (
            _build_orchestrator(Intent.SIMPLE_LOOKUP)
        )

        result = orchestrator.answer("이 약을 두 알 먹어도 돼?")

        self.assertTrue(result.guard_triggered)
        self.assertEqual(result.intent, Intent.IGNORE)
        self.assertEqual(result.answer, SAFETY_IGNORE_ANSWER)
        self.assertEqual(vector_search.embed_count, 0)
        self.assertEqual(vector_search.search_count, 0)
        self.assertEqual(grounded_rag.call_count, 0)
        self.assertEqual(general_chat.call_count, 0)


if __name__ == "__main__":
    unittest.main()
