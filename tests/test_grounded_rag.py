"""청크 인용 및 근거 검증 RAG 서비스 단위 테스트.

작성자: 김진우
"""
from __future__ import annotations

import unittest

from langchain_core.documents import Document

from app.services.grounded_rag import (
    GroundedAnswerDraft,
    GroundedRagService,
    GroundingReview,
    NOT_GROUNDED_ANSWER,
)


class FakeChain:
    def __init__(self, response) -> None:
        self.response = response
        self.call_count = 0
        self.values = None

    def invoke(self, values):
        self.call_count += 1
        self.values = values
        return self.response


def _documents() -> list[Document]:
    return [
        Document(
            page_content="AST는 간과 근육 등 여러 조직에 존재하는 효소입니다.",
            metadata={
                "collection": "health_checkup_info",
                "record_id": "AST",
                "score": 0.91,
                "source_label": "검진 기준",
                "source": "https://example.com/ast",
            },
        ),
        Document(
            page_content="AST 검사는 간 손상 평가에 사용됩니다.",
            metadata={
                "collection": "disease_info",
                "record_id": "D1",
                "score": 0.88,
                "source_label": "의학 지식",
                "source": "https://example.com/d1",
            },
        ),
    ]


class GroundedRagServiceTest(unittest.TestCase):
    def test_supported_answer_passes_with_valid_citations(self) -> None:
        generator = FakeChain(
            GroundedAnswerDraft(
                answer=(
                    "AST는 여러 조직에 존재하는 효소입니다. [C1] "
                    "간 손상 평가에 사용됩니다. [C2]"
                ),
                cited_chunk_ids=["C1", "C2"],
                has_sufficient_context=True,
            )
        )
        verifier = FakeChain(
            GroundingReview(supported=True, unsupported_claims=[])
        )
        service = GroundedRagService(generator, verifier)

        result = service.answer("AST가 무엇인가요?", _documents())

        self.assertTrue(result.grounded)
        self.assertEqual(result.cited_chunk_ids, ["C1", "C2"])
        self.assertIn("의료 진단이 아닌 정보 제공 목적", result.answer)
        self.assertIn("[C1]", result.answer)
        self.assertEqual(generator.call_count, 1)
        self.assertEqual(verifier.call_count, 1)
        self.assertIn("[C1]", verifier.values["context"])

    def test_unknown_citation_fails_before_verifier(self) -> None:
        generator = FakeChain(
            GroundedAnswerDraft(
                answer="AST는 특정 질환을 확정합니다. [C99]",
                cited_chunk_ids=["C99"],
                has_sufficient_context=True,
            )
        )
        verifier = FakeChain(
            GroundingReview(supported=True, unsupported_claims=[])
        )
        service = GroundedRagService(generator, verifier)

        result = service.answer("질문", _documents())

        self.assertFalse(result.grounded)
        self.assertEqual(result.answer, NOT_GROUNDED_ANSWER)
        self.assertEqual(verifier.call_count, 0)
        self.assertTrue(result.grounding_errors)

    def test_citation_only_mode_skips_semantic_verifier(self) -> None:
        generator = FakeChain(
            GroundedAnswerDraft(
                answer="AST는 여러 조직에 존재하는 효소입니다. [C1]",
                cited_chunk_ids=["C1"],
                has_sufficient_context=True,
            )
        )
        verifier = FakeChain(
            GroundingReview(supported=True, unsupported_claims=[])
        )
        service = GroundedRagService(generator, verifier)

        result = service.answer(
            "AST가 무엇인가요?",
            _documents(),
            verify_semantics=False,
        )

        self.assertTrue(result.grounded)
        self.assertEqual(result.verification_method, "citation_only")
        self.assertEqual(verifier.call_count, 0)

    def test_unsupported_claim_is_blocked(self) -> None:
        generator = FakeChain(
            GroundedAnswerDraft(
                answer="AST 상승은 암을 확정합니다. [C1]",
                cited_chunk_ids=["C1"],
                has_sufficient_context=True,
            )
        )
        verifier = FakeChain(
            GroundingReview(
                supported=False,
                unsupported_claims=["AST 상승은 암을 확정합니다."],
            )
        )
        service = GroundedRagService(generator, verifier)

        result = service.answer("질문", _documents())

        self.assertFalse(result.grounded)
        self.assertEqual(result.answer, NOT_GROUNDED_ANSWER)
        self.assertEqual(result.cited_chunk_ids, [])
        self.assertEqual(
            result.unsupported_claims,
            ["AST 상승은 암을 확정합니다."],
        )

    def test_insufficient_context_skips_verifier(self) -> None:
        generator = FakeChain(
            GroundedAnswerDraft(
                answer="",
                cited_chunk_ids=[],
                has_sufficient_context=False,
            )
        )
        verifier = FakeChain(
            GroundingReview(supported=True, unsupported_claims=[])
        )
        service = GroundedRagService(generator, verifier)

        result = service.answer("질문", _documents())

        self.assertFalse(result.grounded)
        self.assertEqual(verifier.call_count, 0)


if __name__ == "__main__":
    unittest.main()
