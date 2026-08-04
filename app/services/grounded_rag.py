"""청크 인용과 별도 검증을 사용하는 근거 기반 RAG 서비스.

작성자: 김진우
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from collections.abc import Iterator
from typing import Any

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.core.config import MODEL
from app.services.rag import cite


NOT_GROUNDED_ANSWER = "지식베이스에 근거 없음"
_CITATION_PATTERN = re.compile(r"\[(C\d+)]")


class GroundingPlanFact(BaseModel):
    """사용자 답변에 사용할 검증된 사실과 근거 청크."""

    statement: str = Field(description="검색 청크가 직접 뒷받침하는 단일 사실")
    cited_chunk_ids: list[str] = Field(description="사실을 뒷받침하는 C1 형식 청크 ID")


class GroundingPlan(BaseModel):
    """최종 답변 생성 전에 확정하는 근거 계획."""

    answerable: bool = Field(description="검색 청크만으로 질문에 답할 수 있는지")
    facts: list[GroundingPlanFact] = Field(description="최종 답변에 사용할 사실 목록")
    reason: str = Field(description="답변 가능 여부와 근거 계획 판단 이유")


class GroundingAudit(BaseModel):
    """스트리밍 완료 답변에 대한 사후 품질 감사 결과."""

    passed: bool = Field(description="최종 답변이 승인된 근거 계획을 벗어나지 않았는지")
    summary: str = Field(description="모니터링 패널에 표시할 감사 요약")
    unsupported_claims: list[str] = Field(
        description="승인된 근거 계획이나 검색 청크가 뒷받침하지 않는 주장"
    )


@dataclass(frozen=True)
class GroundedAnswerResult:
    """검증 완료 답변과 인용·오류 정보."""

    answer: str
    grounded: bool
    cited_chunk_ids: list[str]
    verification_method: str
    grounding_errors: list[str]
    unsupported_claims: list[str]
    grounding_plan: GroundingPlan | None = None
    audit_status: str = "not_applicable"
    audit_summary: str = ""


GROUNDING_PLAN_PROMPT = """너는 HEAPY 건강정보 답변의 근거 설계자다.
사용자에게 답변을 보여주기 전에 검색 청크만으로 답할 수 있는지 판단하고 근거 계획을 작성하라.

규칙:
1. 검색 청크가 직접 뒷받침하는 사실만 facts에 넣는다.
2. 각 사실에는 실제 근거 청크 ID를 하나 이상 연결한다.
3. 검색 청크에 없는 사실을 사전학습 기억으로 보충하거나 추측하지 않는다.
4. 질문의 핵심에 답할 근거가 부족하면 answerable=false로 설정하고 facts는 비운다.
5. 존재하지 않는 청크 ID를 만들지 않는다.
6. 사실은 최종 답변 작성기가 그대로 활용할 수 있도록 완결된 한국어 문장으로 작성한다.

[검증 수준]
{verification_level}

[검색 청크]
{context}

[질문]
{question}
"""


FINAL_ANSWER_PROMPT = """너는 HEAPY의 친절한 건강정보 안내 봇이다.
아래 승인된 근거 계획만 사용해 사용자에게 보여줄 최종 한국어 답변을 작성하라.

규칙:
1. 근거 계획의 facts에 없는 건강·의료 사실, 수치, 원인, 관계를 추가하지 않는다.
2. 청크 ID나 인용 라벨을 답변 본문에 표시하지 않는다.
3. 자연스럽고 읽기 쉬운 문장으로 작성하되 과장하거나 진단하지 않는다.
4. JSON, 코드 블록, 제목을 출력하지 않는다.
5. 사용자가 먼저 인사한 경우가 아니면 인사말, 자기소개, "HEAPY입니다" 같은 상투 문구 없이 질문의 핵심부터 바로 답한다.

[승인된 근거 계획]
{plan}

[질문]
{question}
"""


POST_AUDIT_PROMPT = """너는 HEAPY 건강정보 답변의 사후 품질 감사자다.
이미 사용자에게 스트리밍된 최종 답변을 승인된 근거 계획과 검색 청크에 대조하라.

감사 규칙:
1. 답변의 모든 건강·의료 사실은 승인된 facts와 검색 청크가 직접 뒷받침해야 한다.
2. 계획에 없는 질환명, 원인, 수치, 관계, 행동 권고가 추가되면 unsupported다.
3. 단순한 연결 표현이나 말투는 감사 대상에서 제외한다.
4. 승인된 계획을 벗어난 주장이 하나라도 있으면 passed=false다.
5. summary에는 통과 여부와 핵심 이유를 한두 문장으로 작성한다.

[질문]
{question}

[승인된 근거 계획]
{plan}

[최종 답변]
{answer}

[검색 청크]
{context}
"""


def _coerce_model(value: Any, model_type):
    """구조화 출력의 Pydantic·dict 표현을 동일하게 처리한다."""
    if isinstance(value, model_type):
        return value
    return model_type.model_validate(value)


def format_citation_context(documents: list[Document]) -> str:
    """최종 청크에 C1부터 순서대로 고정 인용 ID를 부여한다."""
    return "\n\n".join(
        (
            f"[C{index}]\n"
            f"컬렉션: {document.metadata.get('collection', 'unknown')}\n"
            f"레코드 ID: {document.metadata.get('record_id', '')}\n"
            f"출처: {cite(document)}\n"
            f"본문: {document.page_content}"
        )
        for index, document in enumerate(documents, start=1)
    )


def strip_citation_labels(answer: str) -> str:
    """검증용 인용 라벨을 사용자에게 표시할 답변에서 제거한다.

    작성자: 김진우
    """
    without_labels = _CITATION_PATTERN.sub("", answer)
    without_trailing_spaces = re.sub(r"[ \t]+\n", "\n", without_labels)
    return re.sub(r"[ \t]{2,}", " ", without_trailing_spaces).strip()


class GroundedRagService:
    """근거 계획을 선검증하고 최종 답변 스트리밍 후 감사를 수행한다."""

    def __init__(self, planner, generator, auditor, stream_generator=None) -> None:
        self._planner = planner
        self._generator = generator
        self._auditor = auditor
        self._stream_generator = stream_generator or generator

    def answer(
        self,
        question: str,
        documents: list[Document],
        *,
        verify_semantics: bool = True,
    ) -> GroundedAnswerResult:
        """선검증된 근거 계획만으로 최종 답변을 생성하고 사후 감사한다."""
        if not documents:
            return self._no_documents_result()

        context = format_citation_context(documents)
        plan, errors = self._create_grounding_plan(
            question,
            documents,
            context,
            verify_semantics=verify_semantics,
        )
        if errors:
            return self._rejected_plan_result(plan, errors)

        plan_text = self._format_plan(plan)
        answer = str(
            self._generator.invoke(
                {"question": question, "plan": plan_text}
            )
        ).strip()
        return self._build_audited_result(
            question=question,
            documents=documents,
            context=context,
            plan=plan,
            plan_text=plan_text,
            answer=answer,
        )

    def stream_answer(
        self,
        question: str,
        documents: list[Document],
        *,
        verify_semantics: bool = True,
    ) -> Iterator[str | GroundedAnswerResult]:
        """근거 계획 승인 후 최종 본문을 한 번 스트리밍하고 감사한다.

        작성자: 김진우
        """
        if not documents:
            yield self._no_documents_result()
            return

        context = format_citation_context(documents)
        plan, errors = self._create_grounding_plan(
            question,
            documents,
            context,
            verify_semantics=verify_semantics,
        )
        if errors:
            yield self._rejected_plan_result(plan, errors)
            return

        plan_text = self._format_plan(plan)
        answer_parts: list[str] = []
        for token in self._stream_generator.stream(
            {"question": question, "plan": plan_text}
        ):
            text = str(token)
            if not text:
                continue
            answer_parts.append(text)
            yield text

        answer = "".join(answer_parts)
        yield self._build_audited_result(
            question=question,
            documents=documents,
            context=context,
            plan=plan,
            plan_text=plan_text,
            answer=answer,
        )

    def _create_grounding_plan(
        self,
        question: str,
        documents: list[Document],
        context: str,
        *,
        verify_semantics: bool,
    ) -> tuple[GroundingPlan, list[str]]:
        """구조화된 근거 계획을 생성하고 청크 ID 계약을 검사한다.

        작성자: 김진우
        """
        verification_level = "강화: 사실과 청크의 의미 일치를 엄격하게 확인" if verify_semantics else "기본: 질문에 직접 답하는 근거 사실 확인"
        plan = _coerce_model(
            self._planner.invoke(
                {
                    "question": question,
                    "context": context,
                    "verification_level": verification_level,
                }
            ),
            GroundingPlan,
        )
        valid_ids = {f"C{index}" for index in range(1, len(documents) + 1)}
        errors: list[str] = []

        if not plan.answerable:
            errors.append(plan.reason or "검색 청크만으로 답변할 수 없습니다.")
            return plan, errors
        if not plan.facts:
            errors.append("답변 가능 계획에 승인된 사실이 없습니다.")

        for index, fact in enumerate(plan.facts, start=1):
            if not fact.statement.strip():
                errors.append(f"근거 계획 사실 {index}의 내용이 비어 있습니다.")
            if not fact.cited_chunk_ids:
                errors.append(f"근거 계획 사실 {index}에 청크 ID가 없습니다.")
                continue
            invalid_ids = sorted(set(fact.cited_chunk_ids) - valid_ids)
            if invalid_ids:
                errors.append(
                    f"근거 계획 사실 {index}에 존재하지 않는 청크 ID가 있습니다: {invalid_ids}"
                )
        return plan, errors

    def _build_audited_result(
        self,
        *,
        question: str,
        documents: list[Document],
        context: str,
        plan: GroundingPlan,
        plan_text: str,
        answer: str,
    ) -> GroundedAnswerResult:
        """표시 답변은 유지하면서 사후 감사 메타데이터를 구성한다."""
        cited_chunk_ids = self._plan_citation_ids(plan)
        try:
            audit = _coerce_model(
                self._auditor.invoke(
                    {
                        "question": question,
                        "plan": plan_text,
                        "answer": answer,
                        "context": context,
                    }
                ),
                GroundingAudit,
            )
            audit_status = "passed" if audit.passed and not audit.unsupported_claims else "failed"
            verification_method = (
                "prevalidated_post_audit"
                if audit_status == "passed"
                else "prevalidated_audit_warning"
            )
            audit_summary = audit.summary
            unsupported_claims = audit.unsupported_claims
            grounding_errors = []
        except Exception:
            audit_status = "error"
            verification_method = "prevalidated_audit_error"
            audit_summary = "사후 감사 호출에 실패했습니다. 표시된 답변은 선검증 근거 계획을 사용했습니다."
            unsupported_claims = []
            grounding_errors = ["사후 감사 호출에 실패했습니다."]

        return GroundedAnswerResult(
            answer=answer,
            grounded=True,
            cited_chunk_ids=cited_chunk_ids,
            verification_method=verification_method,
            grounding_errors=grounding_errors,
            unsupported_claims=unsupported_claims,
            grounding_plan=plan,
            audit_status=audit_status,
            audit_summary=audit_summary,
        )

    @staticmethod
    def _plan_citation_ids(plan: GroundingPlan) -> list[str]:
        return list(
            dict.fromkeys(
                citation_id
                for fact in plan.facts
                for citation_id in fact.cited_chunk_ids
            )
        )

    @staticmethod
    def _format_plan(plan: GroundingPlan) -> str:
        return json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2)

    @staticmethod
    def _no_documents_result() -> GroundedAnswerResult:
        return GroundedAnswerResult(
            answer=NOT_GROUNDED_ANSWER,
            grounded=False,
            cited_chunk_ids=[],
            verification_method="plan_rejected",
            grounding_errors=["검색된 최종 청크가 없습니다."],
            unsupported_claims=[],
            audit_status="not_run",
            audit_summary="근거 계획을 생성하지 않았습니다.",
        )

    @staticmethod
    def _rejected_plan_result(
        plan: GroundingPlan,
        errors: list[str],
    ) -> GroundedAnswerResult:
        return GroundedAnswerResult(
            answer=NOT_GROUNDED_ANSWER,
            grounded=False,
            cited_chunk_ids=[],
            verification_method="plan_rejected",
            grounding_errors=errors,
            unsupported_claims=[],
            grounding_plan=plan,
            audit_status="not_run",
            audit_summary="근거 계획이 선검증을 통과하지 못했습니다.",
        )


def build_grounded_rag_service() -> GroundedRagService:
    """FastAPI lifespan에서 공유할 계획·생성·감사 체인을 만든다."""
    planner_prompt = ChatPromptTemplate.from_template(GROUNDING_PLAN_PROMPT)
    generator_prompt = ChatPromptTemplate.from_template(FINAL_ANSWER_PROMPT)
    auditor_prompt = ChatPromptTemplate.from_template(POST_AUDIT_PROMPT)
    planner_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    generator_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    auditor_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    planner = planner_prompt | planner_llm.with_structured_output(GroundingPlan)
    generator = generator_prompt | generator_llm | StrOutputParser()
    auditor = auditor_prompt | auditor_llm.with_structured_output(GroundingAudit)
    return GroundedRagService(planner, generator, auditor, generator)
