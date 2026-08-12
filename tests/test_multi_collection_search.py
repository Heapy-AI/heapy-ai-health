"""다중 Pinecone namespace 검색과 결과 병합 단위 테스트.

작성자: 김진우
"""
from __future__ import annotations

import threading
import unittest

from fastapi import HTTPException
from langchain_core.documents import Document

from app.core.config import PINECONE_DIMENSION, SEARCH_COLLECTIONS
from app.core.state import state
from app.routers.ask import (
    ask_combined,
    search_combined,
)
from app.schemas.health_chatbot import CombinedAskRequest
from app.services.search_result_merger import merge_search_results
from app.services.grounded_rag import GroundedAnswerResult, RetrievalAssessment
from app.services.vector_search import (
    MultiCollectionSearchResult,
    PineconeSearchService,
)


def _document(
    text: str,
    collection: str,
    score: float,
    record_id: str,
    **metadata,
) -> Document:
    return Document(
        page_content=text,
        metadata={
            "collection": collection,
            "score": score,
            "record_id": record_id,
            **metadata,
        },
    )


class SearchResultMergerTest(unittest.TestCase):
    def test_merge_removes_duplicates_and_limits_collection_bias(self) -> None:
        candidates = [
            _document("공복혈당 검사 설명", "checkup", 0.95, "h1"),
            _document("고혈당 원인", "disease", 0.93, "d1"),
            _document("공복혈당   검사 설명", "disease", 0.92, "d2"),
            _document("당뇨 판정 기준", "checkup", 0.90, "h2"),
            _document("검진 정상B", "checkup", 0.89, "h3"),
            _document("혈당과 약물", "medication", 0.88, "m1"),
            _document("관련도 미달", "interaction", 0.30, "i1"),
        ]

        selected = merge_search_results(
            candidates,
            final_top_k=4,
            max_per_collection=2,
            min_score=0.50,
        )

        self.assertEqual(
            [document.page_content for document in selected],
            [
                "공복혈당 검사 설명",
                "고혈당 원인",
                "당뇨 판정 기준",
                "혈당과 약물",
            ],
        )

    def test_invalid_merge_settings_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            merge_search_results(
                [],
                final_top_k=0,
                max_per_collection=1,
                min_score=0.0,
            )


class PineconeMultiCollectionSearchTest(unittest.TestCase):
    class FakeEmbeddings:
        def __init__(self) -> None:
            self.call_count = 0

        def embed_query(self, question: str) -> list[float]:
            self.call_count += 1
            return [0.0] * PINECONE_DIMENSION

    class FakeIndex:
        def __init__(self, responses: dict[str, object]) -> None:
            self._responses = responses
            self._lock = threading.Lock()
            self.called_namespaces: list[str] = []

        def query(self, *, namespace: str, **kwargs):
            with self._lock:
                self.called_namespaces.append(namespace)
            response = self._responses[namespace]
            if isinstance(response, Exception):
                raise response
            return response

    def _build_service(
        self,
        responses: dict[str, object],
    ) -> tuple[PineconeSearchService, FakeEmbeddings, FakeIndex]:
        service = PineconeSearchService.__new__(PineconeSearchService)
        embeddings = self.FakeEmbeddings()
        index = self.FakeIndex(responses)
        service._embeddings = embeddings
        service._index = index
        return service, embeddings, index

    def test_search_many_embeds_once_and_collects_all_namespaces(self) -> None:
        service, embeddings, index = self._build_service(
            {
                "checkup": {
                    "matches": [
                        {
                            "id": "h1",
                            "score": 0.95,
                            "metadata": {"chunk_text": "공복혈당 검사 설명"},
                        }
                    ]
                },
                "disease": {"matches": []},
                "medication": {
                    "matches": [
                        {
                            "id": "m1",
                            "score": 0.88,
                            "metadata": {"chunk_text": "혈당과 약물"},
                        }
                    ]
                },
            }
        )

        result = service.search_many(
            ["checkup", "disease", "medication"],
            "혈당과 약의 관계",
            3,
        )

        self.assertEqual(embeddings.call_count, 1)
        self.assertCountEqual(
            index.called_namespaces,
            ["checkup", "disease", "medication"],
        )
        self.assertEqual(len(result.documents), 2)
        self.assertEqual(result.errors, {})
        self.assertEqual(
            {document.metadata["collection"] for document in result.documents},
            {"checkup", "medication"},
        )

    def test_search_many_preserves_partial_failure(self) -> None:
        service, _, _ = self._build_service(
            {
                "checkup": {"matches": []},
                "disease": RuntimeError("일시적 장애"),
            }
        )

        result = service.search_many(
            ["checkup", "disease"],
            "질문",
            3,
        )

        self.assertEqual(result.documents, [])
        self.assertEqual(list(result.errors), ["disease"])
        self.assertIn("RuntimeError", result.errors["disease"])


class CombinedSearchEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_state = dict(state)

    def tearDown(self) -> None:
        state.clear()
        state.update(self._original_state)

    def test_combined_endpoint_returns_collection_and_score(self) -> None:
        class FakeVectorSearch:
            def embed_query(self, question):
                return [0.0] * PINECONE_DIMENSION

            def search_many_by_vector(
                self, collections, query_vector, top_k_per_collection
            ):
                return MultiCollectionSearchResult(
                    documents=[
                        _document(
                            "공복혈당 검사 설명",
                            collections[0],
                            0.95,
                            "h1",
                            source_label="검진 기준",
                            source="https://example.com/checkup",
                        )
                    ],
                    searched_collections=list(collections),
                    errors={},
                )

        state["vector_search"] = FakeVectorSearch()

        response = search_combined(CombinedAskRequest(question="공복혈당이 뭐야?"))

        self.assertEqual(response.hits[0].collection, SEARCH_COLLECTIONS[0])
        self.assertEqual(response.hits[0].score, 0.95)
        self.assertEqual(response.failed_collections, [])

    def test_combined_endpoint_rejects_total_search_failure(self) -> None:
        class FailVectorSearch:
            def embed_query(self, question):
                return [0.0] * PINECONE_DIMENSION

            def search_many_by_vector(
                self, collections, query_vector, top_k_per_collection
            ):
                return MultiCollectionSearchResult(
                    documents=[],
                    searched_collections=list(collections),
                    errors={collection: "RuntimeError" for collection in collections},
                )

        state["vector_search"] = FailVectorSearch()

        with self.assertRaises(HTTPException) as context:
            search_combined(CombinedAskRequest(question="질문"))

        self.assertEqual(context.exception.status_code, 503)

    def test_combined_ask_returns_full_final_chunks(self) -> None:
        full_text = "공복혈당 검사 설명 " + ("상세 본문 " * 30)

        class FakeVectorSearch:
            def embed_query(self, question):
                return [0.0] * PINECONE_DIMENSION

            def search_many_by_vector(
                self, collections, query_vector, top_k_per_collection
            ):
                return MultiCollectionSearchResult(
                    documents=[
                        _document(
                            full_text,
                            collections[0],
                            0.95,
                            "h1",
                            source_label="검진 기준",
                            source="https://example.com/checkup",
                        )
                    ],
                    searched_collections=list(collections),
                    errors={},
                )

        class FakeGroundedRagService:
            def answer(
                self,
                question,
                documents,
                *,
                safety_policy,
                audit=True,
                personal_context="",
            ):
                self.question = question
                self.documents = documents
                self.safety_policy = safety_policy
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
                        max_score=0.95,
                        query_entities=[],
                        matched_entities=[],
                    ),
                )

        grounded_rag_service = FakeGroundedRagService()
        state["vector_search"] = FakeVectorSearch()
        state["grounded_rag_service"] = grounded_rag_service

        response = ask_combined(CombinedAskRequest(question="공복혈당이 뭐야?"))

        self.assertTrue(response.grounded)
        self.assertEqual(len(response.chunks), 1)
        self.assertEqual(response.chunks[0].text, full_text)
        self.assertEqual(response.chunks[0].record_id, "h1")
        self.assertEqual(response.citations[0].citation_id, "C1")
        self.assertEqual(response.citations[0].text, full_text)
        self.assertEqual(grounded_rag_service.documents[0].page_content, full_text)
        self.assertEqual(grounded_rag_service.safety_policy.risk_level.value, "normal")
        self.assertEqual(
            response.verification_method,
            "retrieval_check_post_audit",
        )
        self.assertEqual(response.verification_reason, "risk:normal")


if __name__ == "__main__":
    unittest.main()
