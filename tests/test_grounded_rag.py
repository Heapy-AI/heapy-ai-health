"""근거 계획 선검증·최종 스트리밍·사후 감사 단위 테스트.

작성자: 김진우
"""
from __future__ import annotations

import unittest

from langchain_core.documents import Document

from app.services.grounded_rag import (
    FINAL_ANSWER_PROMPT,
    GroundedAnswerResult,
    GroundedRagService,
    GroundingAudit,
    GroundingPlan,
    GroundingPlanFact,
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


def _approved_plan(*citation_ids: str) -> GroundingPlan:
    return GroundingPlan(
        answerable=True,
        facts=[
            GroundingPlanFact(
                statement="AST는 여러 조직에 존재하는 효소입니다.",
                cited_chunk_ids=list(citation_ids or ("C1",)),
            )
        ],
        reason="검색 청크가 질문에 직접 답합니다.",
    )


def _passed_audit() -> GroundingAudit:
    return GroundingAudit(
        passed=True,
        summary="최종 답변이 승인된 근거 계획을 준수했습니다.",
        unsupported_claims=[],
    )


class GroundedRagServiceTest(unittest.TestCase):
    def test_final_prompt_skips_repeated_greeting_and_self_introduction(self) -> None:
        self.assertIn("질문의 핵심부터 바로 답한다", FINAL_ANSWER_PROMPT)
        self.assertIn('"HEAPY입니다"', FINAL_ANSWER_PROMPT)

    def test_stream_prevalidates_then_yields_final_tokens_and_audit(self) -> None:
        planner = FakeChain(_approved_plan("C1"))
        generator = FakeChain("사용하지 않는 동기 답변")
        auditor = FakeChain(_passed_audit())
        stream_generator = FakeStreamChain(
            ["AST는 여러 조직에 ", "존재하는 효소입니다."]
        )
        service = GroundedRagService(
            planner,
            generator,
            auditor,
            stream_generator,
        )

        events = list(service.stream_answer("AST가 무엇인가요?", _documents()))

        self.assertEqual(events[:2], stream_generator.tokens)
        self.assertIsInstance(events[-1], GroundedAnswerResult)
        self.assertEqual(events[-1].answer, "".join(stream_generator.tokens))
        self.assertTrue(events[-1].grounded)
        self.assertEqual(events[-1].audit_status, "passed")
        self.assertEqual(events[-1].cited_chunk_ids, ["C1"])
        self.assertNotIn("의료 진단이 아닌 정보 제공 목적", events[-1].answer)
        self.assertEqual(planner.call_count, 1)
        self.assertEqual(auditor.call_count, 1)

    def test_rejected_plan_does_not_start_generation_or_audit(self) -> None:
        planner = FakeChain(
            GroundingPlan(
                answerable=False,
                facts=[],
                reason="질문에 답할 근거가 부족합니다.",
            )
        )
        generator = FakeChain("생성하면 안 되는 답변")
        auditor = FakeChain(_passed_audit())
        stream_generator = FakeStreamChain(["생성하면 안 되는 토큰"])
        service = GroundedRagService(
            planner,
            generator,
            auditor,
            stream_generator,
        )

        events = list(service.stream_answer("질문", _documents()))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].answer, NOT_GROUNDED_ANSWER)
        self.assertFalse(events[0].grounded)
        self.assertEqual(events[0].verification_method, "plan_rejected")
        self.assertEqual(stream_generator.call_count, 0)
        self.assertEqual(auditor.call_count, 0)

    def test_unknown_plan_citation_is_rejected_before_generation(self) -> None:
        planner = FakeChain(_approved_plan("C99"))
        generator = FakeChain("생성하면 안 되는 답변")
        auditor = FakeChain(_passed_audit())
        service = GroundedRagService(planner, generator, auditor)

        result = service.answer("질문", _documents())

        self.assertFalse(result.grounded)
        self.assertEqual(result.answer, NOT_GROUNDED_ANSWER)
        self.assertTrue(result.grounding_errors)
        self.assertEqual(generator.call_count, 0)
        self.assertEqual(auditor.call_count, 0)

    def test_post_audit_failure_keeps_streamed_answer(self) -> None:
        answer = "AST 상승은 암을 확정합니다."
        planner = FakeChain(_approved_plan("C1"))
        generator = FakeChain(answer)
        auditor = FakeChain(
            GroundingAudit(
                passed=False,
                summary="승인되지 않은 진단성 주장이 추가됐습니다.",
                unsupported_claims=[answer],
            )
        )
        service = GroundedRagService(planner, generator, auditor)

        result = service.answer("질문", _documents())

        self.assertEqual(result.answer, answer)
        self.assertTrue(result.grounded)
        self.assertEqual(result.audit_status, "failed")
        self.assertEqual(result.unsupported_claims, [answer])
        self.assertEqual(result.verification_method, "prevalidated_audit_warning")

    def test_post_audit_error_keeps_answer_and_reports_monitoring_error(self) -> None:
        answer = "AST는 여러 조직에 존재하는 효소입니다."
        service = GroundedRagService(
            FakeChain(_approved_plan("C1")),
            FakeChain(answer),
            FakeChain(RuntimeError("감사 장애")),
        )

        result = service.answer("질문", _documents())

        self.assertEqual(result.answer, answer)
        self.assertTrue(result.grounded)
        self.assertEqual(result.audit_status, "error")
        self.assertTrue(result.grounding_errors)

    def test_enhanced_verification_level_is_sent_to_planner(self) -> None:
        planner = FakeChain(_approved_plan("C1"))
        service = GroundedRagService(
            planner,
            FakeChain("답변"),
            FakeChain(_passed_audit()),
        )

        service.answer("질문", _documents(), verify_semantics=True)

        self.assertIn("강화", planner.values["verification_level"])

    def test_no_documents_returns_rejected_plan_result(self) -> None:
        service = GroundedRagService(
            FakeChain(_approved_plan("C1")),
            FakeChain("답변"),
            FakeChain(_passed_audit()),
        )

        result = service.answer("질문", [])

        self.assertEqual(result.answer, NOT_GROUNDED_ANSWER)
        self.assertFalse(result.grounded)
        self.assertEqual(result.audit_status, "not_run")


if __name__ == "__main__":
    unittest.main()
