"""청크 인용과 별도 검증을 사용하는 근거 기반 RAG 서비스.

작성자: 김진우
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.core.config import MODEL
from app.services.rag import cite


NOT_GROUNDED_ANSWER = "지식베이스에 근거 없음"
MEDICAL_DISCLAIMER = "이 답변은 의료 진단이 아닌 정보 제공 목적입니다"
_CITATION_PATTERN = re.compile(r"\[(C\d+)]")


class GroundedAnswerDraft(BaseModel):
    """Gemini가 생성한 인용 포함 답변 초안."""

    answer: str = Field(description="각 건강정보 주장 뒤에 [C1] 형식 인용을 붙인 답변")
    cited_chunk_ids: list[str] = Field(description="답변에서 인용한 청크 ID 목록")
    has_sufficient_context: bool = Field(description="청크만으로 답할 수 있는지 여부")


class GroundingReview(BaseModel):
    """답변 주장과 인용 청크의 근거 일치 검토 결과."""

    supported: bool = Field(description="모든 건강정보 주장이 인용 청크로 뒷받침되는지")
    unsupported_claims: list[str] = Field(
        description="청크로 뒷받침되지 않거나 인용이 맞지 않는 주장"
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


GENERATION_PROMPT = """너는 HEAPY의 건강정보 안내 봇이다.
아래 검색 청크에 명시된 내용만 사용해 한국어로 답하라.

규칙:
1. 건강·의료 사실, 수치, 원인, 관계를 설명하는 각 문장 끝에 근거 청크 ID를 [C1] 형식으로 붙인다.
2. 하나의 문장이 여러 청크에 근거하면 [C1][C2]처럼 붙인다.
3. 청크에 없는 지식을 사전학습 기억으로 보충하거나 추측하지 않는다.
4. 충분한 근거가 없으면 has_sufficient_context=false로 설정한다.
5. 존재하지 않는 청크 ID를 만들지 않는다.
6. 의료 진단 면책 문구는 서버가 붙이므로 answer에는 작성하지 않는다.

[검색 청크]
{context}

[질문]
{question}
"""


VERIFICATION_PROMPT = """너는 건강정보 답변의 엄격한 근거 검증기다.
답변의 건강·의료 관련 주장을 문장 단위로 확인하라.

검증 규칙:
1. 각 주장은 문장에 표시된 [C숫자] 청크가 직접 뒷받침해야 한다.
2. 인용 청크와 관련만 있는 정도로는 부족하며, 실제 주장 내용이 청크에 있어야 한다.
3. 청크에 없는 질환명, 원인, 수치, 권고를 추가했으면 unsupported다.
4. 일반적인 연결 표현과 의료 진단 면책 문구는 검증 대상에서 제외한다.
5. 모든 주장이 뒷받침될 때만 supported=true다.

[질문]
{question}

[답변]
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


class GroundedRagService:
    """답변 생성 후 인용 ID와 주장 근거를 검증한다."""

    def __init__(self, generator, verifier) -> None:
        self._generator = generator
        self._verifier = verifier

    def answer(
        self,
        question: str,
        documents: list[Document],
        *,
        verify_semantics: bool = True,
    ) -> GroundedAnswerResult:
        """최종 청크만으로 답하고 검증 실패 시 안전하게 회피한다."""
        if not documents:
            return GroundedAnswerResult(
                answer=NOT_GROUNDED_ANSWER,
                grounded=False,
                cited_chunk_ids=[],
                verification_method="citation_validation_failed",
                grounding_errors=["검색된 최종 청크가 없습니다."],
                unsupported_claims=[],
            )

        context = format_citation_context(documents)
        draft = _coerce_model(
            self._generator.invoke({"question": question, "context": context}),
            GroundedAnswerDraft,
        )
        if not draft.has_sufficient_context:
            return GroundedAnswerResult(
                answer=NOT_GROUNDED_ANSWER,
                grounded=False,
                cited_chunk_ids=[],
                verification_method="citation_validation_failed",
                grounding_errors=["생성 모델이 검색 근거 부족을 보고했습니다."],
                unsupported_claims=[],
            )

        inline_ids = list(dict.fromkeys(_CITATION_PATTERN.findall(draft.answer)))
        declared_ids = list(dict.fromkeys(draft.cited_chunk_ids))
        valid_ids = {f"C{index}" for index in range(1, len(documents) + 1)}
        invalid_ids = sorted((set(inline_ids) | set(declared_ids)) - valid_ids)
        grounding_errors: list[str] = []

        if not inline_ids:
            grounding_errors.append("답변에 청크 인용 ID가 없습니다.")
        if invalid_ids:
            grounding_errors.append(
                f"존재하지 않는 청크 인용 ID가 있습니다: {invalid_ids}"
            )
        if set(inline_ids) != set(declared_ids):
            grounding_errors.append(
                "답변 본문의 인용 ID와 cited_chunk_ids가 일치하지 않습니다."
            )
        if grounding_errors:
            return GroundedAnswerResult(
                answer=NOT_GROUNDED_ANSWER,
                grounded=False,
                cited_chunk_ids=[],
                verification_method="citation_validation_failed",
                grounding_errors=grounding_errors,
                unsupported_claims=[],
            )

        if not verify_semantics:
            answer = draft.answer.strip()
            if MEDICAL_DISCLAIMER not in answer:
                answer = f"{answer}\n\n{MEDICAL_DISCLAIMER}."
            return GroundedAnswerResult(
                answer=answer,
                grounded=True,
                cited_chunk_ids=inline_ids,
                verification_method="citation_only",
                grounding_errors=[],
                unsupported_claims=[],
            )

        review = _coerce_model(
            self._verifier.invoke(
                {
                    "question": question,
                    "answer": draft.answer,
                    "context": context,
                }
            ),
            GroundingReview,
        )
        if not review.supported or review.unsupported_claims:
            return GroundedAnswerResult(
                answer=NOT_GROUNDED_ANSWER,
                grounded=False,
                cited_chunk_ids=[],
                verification_method="llm_verification_failed",
                grounding_errors=["근거 검증을 통과하지 못했습니다."],
                unsupported_claims=review.unsupported_claims,
            )

        answer = draft.answer.strip()
        if MEDICAL_DISCLAIMER not in answer:
            answer = f"{answer}\n\n{MEDICAL_DISCLAIMER}."
        return GroundedAnswerResult(
            answer=answer,
            grounded=True,
            cited_chunk_ids=inline_ids,
            verification_method="llm_verified",
            grounding_errors=[],
            unsupported_claims=[],
        )


def build_grounded_rag_service() -> GroundedRagService:
    """FastAPI lifespan에서 공유할 생성·검증 체인을 만든다."""
    generator_prompt = ChatPromptTemplate.from_template(GENERATION_PROMPT)
    verifier_prompt = ChatPromptTemplate.from_template(VERIFICATION_PROMPT)
    generator_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    verifier_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    generator = generator_prompt | generator_llm.with_structured_output(
        GroundedAnswerDraft
    )
    verifier = verifier_prompt | verifier_llm.with_structured_output(GroundingReview)
    return GroundedRagService(generator, verifier)
