"""저장된 대화 요약과 최근 대화로 현재 질문의 문맥을 구조화한다.

첫 질문은 원문을 유지하고, 두 번째 질문부터는 Supabase 세션에서 로드한 요약과 최근
대화를 LLM에 전달한다. LLM은 독립형 질문과 후속 여부, 현재 주제, 이어받은 대상,
개인 건강검진 조회 필요 여부를 함께 반환한다. 이후 파이프라인의 순서는 유지한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.core.config import CHAT_HISTORY_MAX_CHARS, CHAT_HISTORY_MAX_TURNS, MODEL


USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"


@dataclass(frozen=True)
class ConversationTurn:
    """클라이언트가 보낸 직전 대화 한 턴."""

    role: str
    content: str


class RewrittenQuery(BaseModel):
    """LLM이 구조화해 반환하는 대화 문맥 판단 결과."""

    standalone_question: str = Field(
        description="직전 대화 없이도 단독으로 이해되는 한국어 질문 한 문장"
    )
    rewritten: bool = Field(
        description="원래 질문을 실제로 바꿨는지. 이미 자족적이면 false"
    )
    is_follow_up: bool = Field(
        description="현재 질문이 이전 대화에서 이어지는 후속 질문인지"
    )
    current_topic: str = Field(
        description="현재 질문의 핵심 주제. 확인할 수 없으면 빈 문자열"
    )
    inherited_target: str = Field(
        description="이전 대화에서 이어받은 대상. 없으면 빈 문자열"
    )
    personal_context_required: bool = Field(
        description="로그인 사용자의 건강검진 결과 조회가 필요한 질문인지"
    )
    reason: str = Field(description="재작성 여부 판단 이유")


@dataclass(frozen=True)
class QueryRewriteResult:
    """파이프라인이 사용할 질문과 재작성 메타데이터."""

    question: str
    original_question: str
    rewritten: bool
    reason: str
    is_follow_up: bool = False
    current_topic: str = ""
    inherited_target: str = ""
    personal_context_required: bool = False
    context_analysis_performed: bool = False
    error: str | None = None


QUERY_REWRITE_PROMPT = """너는 건강정보 챗봇의 대화 문맥 해석기다.
이전 대화 요약, 최근 대화, 사용자의 현재 질문을 함께 보고 구조화된 문맥 판단 결과를 반환하라.

규칙:
1. 대명사("그거", "이건")와 생략된 주제를 직전 대화에서 찾아 명시적으로 복원한다.
   "낮추려면 어떻게 해야 돼?", "부작용은?"처럼 목적어만 빠진 후속 질문도
   직전 대화의 대상으로 복원한다.
2. 직전 대화에 없는 의료 사실, 질환명, 수치, 약 이름을 새로 지어내지 않는다.
3. 마지막 발화가 이미 단독으로 이해되면 그대로 두고 rewritten=false로 표시한다.
4. 사용자의 의도와 어조를 바꾸지 않는다. 특히 개인 진단·복약 결정·내원 판단을
   요구하는 표현은 **약화하거나 삭제하지 말고 그대로 보존**한다. 안전 검사가
   재작성된 질문을 보고 판단하기 때문이다.
5. 주제가 바뀐 새 질문이면 직전 대화를 끌어오지 않는다.
6. 질문 한 문장만 만든다. 답을 하지 않고, 설명이나 인사말을 붙이지 않는다.
7. [이전 대화 요약]은 창 밖으로 밀려난 오래된 맥락이다. 직전 대화만으로 해소되지
   않을 때만 참고하고, 요약에 있는 내용을 새 사실처럼 질문에 덧붙이지 않는다.
8. 사용자의 1인칭 관점을 보존한다. 이전 대화가 사용자의 본인 정보에 관한 내용이면
   "내", "나의", "제", "저의"를 유지하고 사용자 이름이나 제3자 표현으로 바꾸지 않는다.
9. is_follow_up은 현재 질문이 이전 질문이나 답변의 대상·결과·요청을 이어갈 때만 true다.
10. current_topic에는 현재 질문의 핵심 의료 주제나 일반 대화 주제를 짧게 적는다.
11. inherited_target에는 이전 대화에서 실제로 이어받은 검사, 질환, 약, 검진 결과 등의
    대상을 적고, 새 주제이거나 이어받은 대상이 없으면 빈 문자열로 둔다.
12. personal_context_required는 로그인 사용자의 실제 개인 기록이 필요할 때만 true다.
    대상은 두 가지다. (1) 건강검진 기록·수치·판정·추이 또는 그 결과를 바탕으로 한 설명.
    (2) 걸음수·활동량·운동·식단·영양·수분 섭취·수면·체중·BMI·혈압·혈당·심박수처럼
    기기 연동이나 직접 기록으로 쌓인 생활습관 데이터. 일반적인 검사·질환·의약품 정보
    질문에는 false다. 질병 자체를 묻는 질문("고혈압이 뭐야", "당뇨병 증상")은 개인
    기록이 아니므로 false다. 이전 턴에서 개인 검진 결과나 생활습관 기록을 다뤘고
    현재 질문이 그 결과를 이어받는다면 true를 유지한다.

[이전 대화 요약]
{summary}

[직전 대화]
{history}

[사용자의 마지막 발화]
{question}
"""


def normalize_history(turns) -> list[ConversationTurn]:
    """최근 대화만 남기고 길이를 제한한다.

    문맥 창을 제한해 프롬프트 비용과 잘못된 주제 끌어오기를 함께 줄인다.
    """
    normalized: list[ConversationTurn] = []
    for turn in turns or []:
        role = str(getattr(turn, "role", None) or turn["role"]).strip().lower()
        content = str(getattr(turn, "content", None) or turn["content"]).strip()
        if role not in (USER_ROLE, ASSISTANT_ROLE) or not content:
            continue
        normalized.append(
            ConversationTurn(role=role, content=content[:CHAT_HISTORY_MAX_CHARS])
        )
    return normalized[-CHAT_HISTORY_MAX_TURNS:]


def format_history(turns: list[ConversationTurn]) -> str:
    """프롬프트에 넣을 대화 문자열을 만든다."""
    labels = {USER_ROLE: "사용자", ASSISTANT_ROLE: "챗봇"}
    return "\n".join(f"{labels[turn.role]}: {turn.content}" for turn in turns)


def _coerce(value: Any) -> RewrittenQuery:
    if isinstance(value, RewrittenQuery):
        return value
    return RewrittenQuery.model_validate(value)


class QueryRewriter:
    """첫 질문을 제외한 모든 질문의 문맥을 LLM으로 구조화한다."""

    def __init__(self, chain) -> None:
        self._chain = chain

    def rewrite(self, question: str, history, summary: str = "") -> QueryRewriteResult:
        """후속 질문을 자족적인 질문으로 바꾼다.

        재작성에 실패하면 원문을 그대로 사용한다. 멀티턴 보조 기능 때문에
        답변 자체가 막히면 안 되기 때문이다.
        """
        turns = normalize_history(history)
        summary_text = (summary or "").strip()
        if not turns and not summary_text:
            # 첫 턴에는 LLM을 호출하지 않는다(지연시간 0).
            return QueryRewriteResult(
                question=question,
                original_question=question,
                rewritten=False,
                reason="직전 대화와 요약이 없어 재작성하지 않았습니다.",
            )
        try:
            result = _coerce(
                self._chain.invoke(
                    {
                        "question": question,
                        "history": format_history(turns) or "(없음)",
                        "summary": summary_text or "(없음)",
                    }
                )
            )
        except Exception as exc:
            return QueryRewriteResult(
                question=question,
                original_question=question,
                rewritten=False,
                reason="질문 재작성에 실패해 원래 질문을 사용했습니다.",
                context_analysis_performed=False,
                error=f"{type(exc).__name__}: {exc}",
            )

        standalone = (result.standalone_question or "").strip()
        if not standalone:
            return QueryRewriteResult(
                question=question,
                original_question=question,
                rewritten=False,
                reason="재작성 결과가 비어 있어 원래 질문을 사용했습니다.",
                context_analysis_performed=False,
                error="empty_standalone_question",
            )

        return QueryRewriteResult(
            question=standalone,
            original_question=question,
            rewritten=bool(result.rewritten) and standalone != question,
            reason=result.reason or "",
            is_follow_up=result.is_follow_up,
            current_topic=result.current_topic.strip(),
            inherited_target=result.inherited_target.strip(),
            personal_context_required=result.personal_context_required,
            context_analysis_performed=True,
        )


def build_query_rewriter() -> QueryRewriter:
    """FastAPI lifespan에서 공유할 질문 재작성 체인을 만든다."""
    prompt = ChatPromptTemplate.from_template(QUERY_REWRITE_PROMPT)
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    return QueryRewriter(prompt | llm.with_structured_output(RewrittenQuery))
