"""검색 기본 검사·부분 답변·사후 감사 단위 테스트.

작성자: 김진우
"""
from __future__ import annotations

import unittest

from langchain_core.documents import Document

from app.services.grounded_rag import (
    FINAL_ANSWER_PROMPT,
    GroundedAnswerResult,
    GroundedRagProgress,
    GroundedRagService,
    GroundingAudit,
    NOT_GROUNDED_ANSWER,
    assess_retrieval,
    strip_citation_labels,
)
from app.services.safety_guard import check_safety_guard


class FakeChain:
    def __init__(self, response) -> None:
        self.response = response
        self.call_count = 0
        self.values = None

    def invoke(self, values):
        self.call_count += 1
        self.values = values
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeStreamChain:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.call_count = 0
        self.values = None

    def stream(self, values):
        self.call_count += 1
        self.values = values
        yield from self.tokens


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


def _passed_audit(coverage_status: str = "sufficient") -> GroundingAudit:
    return GroundingAudit(
        passed=True,
        summary="답변이 검색 근거와 안전 정책을 준수했습니다.",
        coverage_status=coverage_status,
        unanswered_items=[],
        unsupported_claims=[],
        safety_violations=[],
    )


class GroundedRagServiceTest(unittest.TestCase):
    def test_user_answer_removes_single_and_multiple_citation_labels(self) -> None:
        answer = "첫 문장[C1] 둘째 문장[c1, c2]"

        self.assertEqual(strip_citation_labels(answer), "첫 문장 둘째 문장")

    def test_final_prompt_requires_partial_answer_and_no_repeated_greeting(self) -> None:
        self.assertIn("근거가 있는 항목은 답하고", FINAL_ANSWER_PROMPT)
        self.assertIn("질문의 핵심부터 답한다", FINAL_ANSWER_PROMPT)
        self.assertIn("긴급 안내만 하고 답변을 끝내지 말고", FINAL_ANSWER_PROMPT)
        self.assertIn("내부 구현 용어를 노출하지 않는다", FINAL_ANSWER_PROMPT)
        self.assertIn("{personal_context}", FINAL_ANSWER_PROMPT)
        self.assertIn("개인 검진 측정값에는 청크 ID를 붙이지 않는다", FINAL_ANSWER_PROMPT)

    def test_emergency_information_request_still_uses_rag_generation(self) -> None:
        generator = FakeChain("즉시 119에 연락하세요. 호흡곤란은 숨쉬기 어려운 상태입니다.[C1]")
        auditor = FakeChain(_passed_audit())
        service = GroundedRagService(generator, auditor)
        question = "나 지금 숨이 안 쉬어지는데 호흡곤란 증상 좀 알려줘"

        result = service.answer(
            question,
            _documents(),
            safety_policy=check_safety_guard(question),
        )

        self.assertEqual(generator.call_count, 1)
        self.assertTrue(result.grounded)
        self.assertIn("호흡곤란", result.answer)

    def test_stream_generates_without_planner_then_audits(self) -> None:
        generator = FakeChain("사용하지 않는 동기 답변")
        auditor = FakeChain(_passed_audit())
        stream_generator = FakeStreamChain(
            ["AST는 여러 조직에 ", "존재하는 효소입니다.[C1]"]
        )
        service = GroundedRagService(generator, auditor, stream_generator)

        events = list(
            service.stream_answer(
                "AST가 무엇인가요?",
                _documents(),
                safety_policy=check_safety_guard("AST가 무엇인가요?"),
            )
        )

        self.assertEqual(events[:2], stream_generator.tokens)
        self.assertIsInstance(events[-2], GroundedRagProgress)
        self.assertEqual(events[-2].stage, "verify_answer")
        self.assertIsInstance(events[-1], GroundedAnswerResult)
        self.assertEqual(events[-1].answer, "AST는 여러 조직에 존재하는 효소입니다.")
        self.assertTrue(events[-1].grounded)
        self.assertEqual(events[-1].audit_status, "passed")
        self.assertEqual(events[-1].cited_chunk_ids, ["C1"])
        self.assertEqual(auditor.call_count, 1)

    def test_user_stream_skips_post_audit_without_changing_answer(self) -> None:
        """사용자 스트림은 답변 본문을 바꾸지 않는 사후 감사 호출을 생략한다.

        작성자: 김진우
        """
        auditor = FakeChain(_passed_audit())
        stream_generator = FakeStreamChain(["AST 설명입니다.[C1]"])
        service = GroundedRagService(FakeChain(""), auditor, stream_generator)

        events = list(
            service.stream_answer(
                "AST가 무엇인가요?",
                _documents(),
                safety_policy=check_safety_guard("AST가 무엇인가요?"),
                audit=False,
            )
        )

        progress_events = [
            event for event in events if isinstance(event, GroundedRagProgress)
        ]
        self.assertEqual(
            [event.stage for event in progress_events],
            ["answer_stream_complete"],
        )
        self.assertEqual(auditor.call_count, 0)
        self.assertEqual(events[-1].answer, "AST 설명입니다.")
        self.assertEqual(events[-1].audit_status, "not_run")

    def test_entity_mismatch_stops_generation_without_llm_call(self) -> None:
        generator = FakeChain("생성하면 안 되는 답변")
        auditor = FakeChain(_passed_audit())
        service = GroundedRagService(generator, auditor)

        result = service.answer(
            "판콜에스내복액이 무슨 약이야?",
            _documents(),
            safety_policy=check_safety_guard("판콜에스내복액이 무슨 약이야?"),
        )

        self.assertFalse(result.grounded)
        self.assertEqual(result.evidence_status, "entity_mismatch")
        self.assertEqual(generator.call_count, 0)
        self.assertEqual(auditor.call_count, 0)

    def test_partial_coverage_is_a_valid_grounded_answer(self) -> None:
        answer = "이 약의 효능은 확인됩니다.[C1] 부작용은 현재 자료에서 확인되지 않았습니다."
        auditor = FakeChain(
            GroundingAudit(
                passed=True,
                summary="효능은 답했고 부작용은 근거 부족으로 구분했습니다.",
                coverage_status="partial",
                unanswered_items=["부작용"],
                unsupported_claims=[],
                safety_violations=[],
            )
        )
        service = GroundedRagService(FakeChain(answer), auditor)

        result = service.answer(
            "AST의 의미와 위험요인을 알려줘",
            _documents(),
            safety_policy=check_safety_guard("AST의 의미와 위험요인을 알려줘"),
        )

        self.assertTrue(result.grounded)
        self.assertEqual(result.evidence_status, "partial")
        self.assertEqual(result.unanswered_items, ["부작용"])
        self.assertEqual(result.audit_status, "passed")

    def test_post_audit_failure_keeps_generated_answer(self) -> None:
        answer = "AST 상승은 암을 확정합니다.[C1]"
        auditor = FakeChain(
            GroundingAudit(
                passed=False,
                summary="근거 없는 진단성 주장이 추가됐습니다.",
                coverage_status="sufficient",
                unanswered_items=[],
                unsupported_claims=["AST 상승은 암을 확정합니다."],
                safety_violations=["definitive_diagnosis"],
            )
        )
        service = GroundedRagService(FakeChain(answer), auditor)

        result = service.answer(
            "AST로 암을 확정해줘",
            _documents(),
            safety_policy=check_safety_guard("AST로 암을 확정해줘"),
        )

        self.assertEqual(result.answer, "AST 상승은 암을 확정합니다.")
        self.assertEqual(result.audit_status, "failed")
        self.assertEqual(result.verification_method, "retrieval_check_audit_warning")

    def test_no_documents_returns_no_evidence_without_generation(self) -> None:
        generator = FakeChain("답변")
        service = GroundedRagService(generator, FakeChain(_passed_audit()))

        result = service.answer(
            "질문",
            [],
            safety_policy=check_safety_guard("질문"),
        )

        self.assertEqual(result.answer, NOT_GROUNDED_ANSWER)
        self.assertFalse(result.grounded)
        self.assertEqual(result.evidence_status, "no_evidence")
        self.assertEqual(generator.call_count, 0)

    def test_personal_context_allows_generation_without_vdb_documents(self) -> None:
        generator = FakeChain("최근 검진에서 AST는 54 U/L이고 DB 상태는 이상입니다.")
        service = GroundedRagService(generator, FakeChain(_passed_audit()))

        result = service.answer(
            "내 검진 결과를 설명해줘",
            [],
            safety_policy=check_safety_guard("내 검진 결과를 설명해줘"),
            audit=False,
            personal_context=(
                "측정일: 2026-08-06\n"
                "- AST: 54 U/L (DB 상태: 이상)"
            ),
        )

        self.assertTrue(result.grounded)
        self.assertEqual(result.evidence_status, "personal_evidence_available")
        self.assertEqual(generator.call_count, 1)
        self.assertEqual(generator.values["context"], "제공되지 않음")

    def test_personal_context_overrides_vdb_entity_mismatch(self) -> None:
        generator = FakeChain("개인 검진값을 기준으로 설명합니다.")
        service = GroundedRagService(generator, FakeChain(_passed_audit()))

        result = service.answer(
            "내 고혈압 관련 검진 결과를 설명해줘",
            _documents(),
            safety_policy=check_safety_guard("내 고혈압 관련 검진 결과를 설명해줘"),
            audit=False,
            personal_context="혈압: 130/85 mmHg (DB 상태: 경계)",
        )

        self.assertTrue(result.grounded)
        self.assertEqual(result.evidence_status, "personal_evidence_available")
        self.assertEqual(generator.call_count, 1)

    def test_assessment_accepts_matching_medication_entity(self) -> None:
        documents = [
            Document(
                page_content="의약품: 판콜에스내복액\n효능: 감기 증상 완화",
                metadata={"item_name": "판콜에스내복액", "score": 0.9},
            )
        ]

        result = assess_retrieval("판콜에스내복액은 무슨 약이야?", documents)

        self.assertTrue(result.eligible)
        self.assertEqual(result.matched_entities, ["판콜에스내복액"])


if __name__ == "__main__":
    unittest.main()
