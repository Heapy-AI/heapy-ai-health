"""기본 검색 검사와 사후 감사를 사용하는 근거 기반 RAG 서비스.

작성자: 김진우
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.core.config import MODEL
from app.services.rag import cite
from app.services.safety_guard import GuardResult


NOT_GROUNDED_ANSWER = (
    "질문과 정확히 일치하는 정보를 찾지 못했습니다. 이름이나 수치를 다시 확인해 "
    "알려주시면 확인 가능한 정보부터 이어서 설명드릴게요."
)
EMERGENCY_NO_EVIDENCE_ANSWER = (
    "지금 실제로 숨쉬기 어렵거나 심한 흉통, 의식 저하 같은 증상이 있다면 "
    "답변을 기다리지 말고 주변에 도움을 요청한 뒤 119에 연락하거나 가까운 "
    "응급실로 이동하세요. 증상이 언제 시작됐는지와 현재 복용 중인 약을 정리해 "
    "의료진에게 전달하면 빠른 판단에 도움이 됩니다."
)
_CITATION_LABEL_PATTERN = re.compile(
    r"\[(?:C\d+\s*(?:,\s*C?\d+\s*)*)]",
    re.IGNORECASE,
)
_CITATION_ID_PATTERN = re.compile(r"C\d+", re.IGNORECASE)
_ENTITY_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9·+\-]{2,40}")
_MEDICATION_SUFFIXES = (
    "내복액",
    "캡슐",
    "시럽",
    "주사",
    "연고",
    "크림",
    "과립",
    "정",
    "액",
    "산",
)
_DISEASE_SUFFIXES = ("당뇨병", "고혈압", "감기", "암", "병", "염", "증")
_ENTITY_STOP_WORDS = {
    "질병",
    "합병증",
    "부작용",
    "증상",
    "염증",
    "검진",
    "건강",
    "약",
}
_ENTITY_METADATA_KEYS = (
    "item_name",
    "display_item_name",
    "search_item_name",
    "original_item_name",
    "disease",
    "heading",
    "canonical_key",
    "record_id",
)


class GroundingAudit(BaseModel):
    """스트리밍 완료 답변에 대한 사후 품질 감사 결과."""

    passed: bool = Field(description="답변의 의료 사실이 검색 청크와 안전 정책을 준수하는지")
    summary: str = Field(description="모니터링 패널에 표시할 감사 요약")
    coverage_status: str = Field(
        description="질문 항목별 근거 충족 상태: sufficient, partial, insufficient"
    )
    unanswered_items: list[str] = Field(
        default_factory=list,
        description="검색 근거가 없어 답하지 못한 질문 항목",
    )
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="검색 청크가 뒷받침하지 않는 주장",
    )
    safety_violations: list[str] = Field(
        default_factory=list,
        description="안전 정책의 금지 행동을 위반한 표현",
    )


@dataclass(frozen=True)
class RetrievalAssessment:
    """LLM 호출 전에 수행하는 결정론적 검색 결과 검사."""

    status: str
    eligible: bool
    reason: str
    max_score: float | None
    query_entities: list[str]
    matched_entities: list[str]


@dataclass(frozen=True)
class GroundedAnswerResult:
    """생성 답변과 검색 검사·사후 감사 정보."""

    answer: str
    grounded: bool
    cited_chunk_ids: list[str]
    verification_method: str
    grounding_errors: list[str]
    unsupported_claims: list[str]
    evidence_status: str
    retrieval_assessment: RetrievalAssessment
    audit_status: str = "not_applicable"
    audit_summary: str = ""
    unanswered_items: list[str] | None = None
    safety_violations: list[str] | None = None


FINAL_ANSWER_PROMPT = """너는 HEAPY의 건강정보 안내 봇이다.
사용자 질문에 대해 아래 검색 청크와 안전 정책만 사용해 한국어 답변을 작성하라.

[근거 사용 규칙]
1. 검색 청크가 직접 뒷받침하는 의료 사실만 말한다. 사전학습 기억으로 보충하거나 추측하지 않는다.
2. 질문에 여러 항목이 있으면 항목별로 판단한다. 근거가 있는 항목은 답하고, 없는 항목은 "현재 확인 가능한 정보에서는 구체적인 내용을 찾지 못했다"고 자연스럽게 구분한다.
3. 일부 항목의 근거가 없다는 이유로 근거가 있는 다른 항목까지 거절하지 않는다.
4. 의료 사실을 사용한 문단 끝에는 내부 검증용 청크 ID를 [C1] 형식으로 붙인다. 존재하지 않는 ID는 만들지 않는다.
5. 청크의 대상 의약품·질병·검사항목을 다른 대상으로 바꾸어 설명하지 않는다.

[안전 규칙]
1. safety_policy의 restricted_actions에 포함된 의료적 결정을 대신 수행하지 않는다.
2. definitive_diagnosis가 제한되면 질병을 확정하지 않고 관련 일반 정보와 위험 신호를 설명한다.
3. personalized_prescription, medication_dose_change, medication_stop이 제한되면 특정 약의 선택·증량·감량·중단을 결정하지 않는다.
4. emergency=true이면 첫 문장에서 119 연락 또는 즉시 응급실 방문을 우선 안내한다. 단, 긴급 안내만 하고 답변을 끝내지 말고 검색 청크에서 확인되는 사용자의 요청 정보도 최대한 제공한다.
5. personalized_prognosis가 제한되면 개인의 완치 날짜나 회복 시점을 단정하지 않고 일반적인 경과와 영향을 주는 요인을 설명한다.
6. 개인 증상, 복약 결정, 부분 근거 부족, 지속·악화 위험이 있는 경우에만 의료진 상담이나 진료 안내를 덧붙인다. 모든 답변에 같은 면책 문구를 반복하지 않는다.

[표현 규칙]
1. 자연스럽고 읽기 쉽게 쓰되 JSON이나 코드 블록은 출력하지 않는다.
2. 사용자가 먼저 인사하지 않았다면 인사말이나 자기소개 없이 질문의 핵심부터 답한다.
3. 사용자에게는 청크 ID가 제거되어 표시되므로, 문장이 자연스럽게 이어지도록 작성한다.
4. 사용자에게 데이터베이스, 청크, 근거 계획 같은 내부 구현 용어를 노출하지 않는다.

[안전 정책]
{safety_policy}

[검색 청크]
{context}

[질문]
{question}
"""


POST_AUDIT_PROMPT = """너는 HEAPY 건강정보 답변의 사후 품질 감사자다.
이미 사용자에게 스트리밍된 답변을 검색 청크와 안전 정책에 대조하라. 답변 본문은 수정하지 않고 모니터링 결과만 기록한다.

감사 규칙:
1. 답변의 모든 의료 사실이 검색 청크에 직접 근거하는지 확인한다.
2. 질문의 여러 요청 중 답한 항목과 근거 부족으로 답하지 않은 항목을 구분한다.
3. 일부만 답했으며 부족한 항목을 명확히 밝혔으면 coverage_status=partial로 기록하되 그 이유만으로 실패 처리하지 않는다.
4. 근거 없는 사실을 추가했거나 안전 정책의 금지 행동을 수행했으면 passed=false다.
5. 충분히 답했으면 sufficient, 전혀 답할 근거가 없었으면 insufficient로 기록한다.
6. summary는 통과 여부, 근거 충족도, 안전 정책 준수 여부를 한두 문장으로 작성한다.

[질문]
{question}

[안전 정책]
{safety_policy}

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


def _normalize_entity(value: str) -> str:
    """대상 일치 비교를 위해 조사·공백·기호를 제거한다."""
    normalized = re.sub(r"[^가-힣a-z0-9]", "", value.lower())
    return re.sub(r"(?:으로|에서|에게|에는|으로는|이랑|와|과|은|는|이|가|을|를|의)$", "", normalized)


def extract_query_entities(question: str) -> list[str]:
    """명시적인 의약품·질병명 후보만 보수적으로 추출한다."""
    entities: list[str] = []
    for raw_token in _ENTITY_TOKEN_PATTERN.findall(question):
        token = _normalize_entity(raw_token)
        if token in _ENTITY_STOP_WORDS or len(token) < 2:
            continue
        if token.endswith(_MEDICATION_SUFFIXES) or token.endswith(_DISEASE_SUFFIXES):
            entities.append(token)
    return list(dict.fromkeys(entities))


def _document_search_text(document: Document) -> str:
    metadata_values = [
        str(document.metadata.get(key, ""))
        for key in _ENTITY_METADATA_KEYS
    ]
    return _normalize_entity(" ".join([document.page_content, *metadata_values]))


def assess_retrieval(
    question: str,
    documents: list[Document],
) -> RetrievalAssessment:
    """결과 존재 여부와 명시 대상 일치를 LLM 없이 검사한다."""
    if not documents:
        return RetrievalAssessment(
            status="no_evidence",
            eligible=False,
            reason="검색된 최종 청크가 없습니다.",
            max_score=None,
            query_entities=[],
            matched_entities=[],
        )

    scores = [
        float(document.metadata.get("score", 0.0) or 0.0)
        for document in documents
    ]
    query_entities = extract_query_entities(question)
    searchable_text = " ".join(_document_search_text(document) for document in documents)
    matched_entities = [entity for entity in query_entities if entity in searchable_text]
    if query_entities and not matched_entities:
        return RetrievalAssessment(
            status="entity_mismatch",
            eligible=False,
            reason=(
                "질문에 명시된 대상과 검색 청크의 대상이 일치하지 않습니다: "
                + ", ".join(query_entities)
            ),
            max_score=max(scores),
            query_entities=query_entities,
            matched_entities=[],
        )

    return RetrievalAssessment(
        status="evidence_available",
        eligible=True,
        reason="최소 검색 기준을 통과한 청크가 있으며 명시 대상 불일치가 없습니다.",
        max_score=max(scores),
        query_entities=query_entities,
        matched_entities=matched_entities,
    )


def format_citation_context(documents: list[Document]) -> str:
    """최종 청크에 C1부터 순서대로 내부 검증 ID를 부여한다."""
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
    """검증용 인용 라벨을 사용자 표시 답변에서 제거한다."""
    without_labels = _CITATION_LABEL_PATTERN.sub("", answer)
    without_trailing_spaces = re.sub(r"[ \t]+\n", "\n", without_labels)
    return re.sub(r"[ \t]{2,}", " ", without_trailing_spaces).strip()


def _safety_policy_json(safety_policy: GuardResult) -> str:
    return json.dumps(
        {
            "risk_level": safety_policy.risk_level.value,
            "restricted_actions": safety_policy.restricted_actions,
            "response_policy": safety_policy.response_policy,
            "emergency": safety_policy.emergency,
            "reason": safety_policy.reason,
        },
        ensure_ascii=False,
        indent=2,
    )


class GroundedRagService:
    """기본 검색 검사를 통과한 문맥으로 생성하고 결과를 사후 감사한다."""

    def __init__(self, generator, auditor, stream_generator=None) -> None:
        self._generator = generator
        self._auditor = auditor
        self._stream_generator = stream_generator or generator

    def answer(
        self,
        question: str,
        documents: list[Document],
        *,
        safety_policy: GuardResult,
    ) -> GroundedAnswerResult:
        assessment = assess_retrieval(question, documents)
        if not assessment.eligible:
            return self._rejected_retrieval_result(assessment, safety_policy)

        context = format_citation_context(documents)
        safety_policy_text = _safety_policy_json(safety_policy)
        raw_answer = str(
            self._generator.invoke(
                {
                    "question": question,
                    "context": context,
                    "safety_policy": safety_policy_text,
                }
            )
        ).strip()
        return self._build_audited_result(
            question=question,
            context=context,
            safety_policy_text=safety_policy_text,
            raw_answer=raw_answer,
            assessment=assessment,
        )

    def stream_answer(
        self,
        question: str,
        documents: list[Document],
        *,
        safety_policy: GuardResult,
    ) -> Iterator[str | GroundedAnswerResult]:
        assessment = assess_retrieval(question, documents)
        if not assessment.eligible:
            yield self._rejected_retrieval_result(assessment, safety_policy)
            return

        context = format_citation_context(documents)
        safety_policy_text = _safety_policy_json(safety_policy)
        answer_parts: list[str] = []
        for token in self._stream_generator.stream(
            {
                "question": question,
                "context": context,
                "safety_policy": safety_policy_text,
            }
        ):
            text = str(token)
            if not text:
                continue
            answer_parts.append(text)
            yield text

        yield self._build_audited_result(
            question=question,
            context=context,
            safety_policy_text=safety_policy_text,
            raw_answer="".join(answer_parts),
            assessment=assessment,
        )

    def _build_audited_result(
        self,
        *,
        question: str,
        context: str,
        safety_policy_text: str,
        raw_answer: str,
        assessment: RetrievalAssessment,
    ) -> GroundedAnswerResult:
        cited_chunk_ids = list(
            dict.fromkeys(
                citation_id.upper()
                for label in _CITATION_LABEL_PATTERN.findall(raw_answer)
                for citation_id in _CITATION_ID_PATTERN.findall(label)
            )
        )
        answer = strip_citation_labels(raw_answer)
        try:
            audit = _coerce_model(
                self._auditor.invoke(
                    {
                        "question": question,
                        "safety_policy": safety_policy_text,
                        "answer": raw_answer,
                        "context": context,
                    }
                ),
                GroundingAudit,
            )
            audit_passed = (
                audit.passed
                and not audit.unsupported_claims
                and not audit.safety_violations
            )
            audit_status = "passed" if audit_passed else "failed"
            verification_method = (
                "retrieval_check_post_audit"
                if audit_passed
                else "retrieval_check_audit_warning"
            )
            grounding_errors: list[str] = []
            evidence_status = audit.coverage_status
            audit_summary = audit.summary
            unsupported_claims = audit.unsupported_claims
            unanswered_items = audit.unanswered_items
            safety_violations = audit.safety_violations
        except Exception:
            audit_status = "error"
            verification_method = "retrieval_check_audit_error"
            grounding_errors = ["사후 감사 호출에 실패했습니다."]
            evidence_status = "unknown"
            audit_summary = "검색 검사는 통과했지만 사후 감사 호출에 실패했습니다."
            unsupported_claims = []
            unanswered_items = []
            safety_violations = []

        return GroundedAnswerResult(
            answer=answer,
            grounded=True,
            cited_chunk_ids=cited_chunk_ids,
            verification_method=verification_method,
            grounding_errors=grounding_errors,
            unsupported_claims=unsupported_claims,
            evidence_status=evidence_status,
            retrieval_assessment=assessment,
            audit_status=audit_status,
            audit_summary=audit_summary,
            unanswered_items=unanswered_items,
            safety_violations=safety_violations,
        )

    @staticmethod
    def _rejected_retrieval_result(
        assessment: RetrievalAssessment,
        safety_policy: GuardResult,
    ) -> GroundedAnswerResult:
        answer = (
            EMERGENCY_NO_EVIDENCE_ANSWER
            if safety_policy.emergency
            else NOT_GROUNDED_ANSWER
        )
        return GroundedAnswerResult(
            answer=answer,
            grounded=False,
            cited_chunk_ids=[],
            verification_method="retrieval_rejected",
            grounding_errors=[assessment.reason],
            unsupported_claims=[],
            evidence_status=assessment.status,
            retrieval_assessment=assessment,
            audit_status="not_run",
            audit_summary="검색 결과 기본 검사에서 답변 생성을 중단했습니다.",
            unanswered_items=[],
            safety_violations=[],
        )


def build_grounded_rag_service() -> GroundedRagService:
    """FastAPI lifespan에서 공유할 생성·사후 감사 체인을 만든다."""
    generator_prompt = ChatPromptTemplate.from_template(FINAL_ANSWER_PROMPT)
    auditor_prompt = ChatPromptTemplate.from_template(POST_AUDIT_PROMPT)
    generator_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    auditor_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    generator = generator_prompt | generator_llm | StrOutputParser()
    auditor = auditor_prompt | auditor_llm.with_structured_output(GroundingAudit)
    return GroundedRagService(generator, auditor, generator)
