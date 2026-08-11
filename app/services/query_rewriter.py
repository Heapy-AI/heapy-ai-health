"""직전 대화를 참고해 후속 질문을 독립형 질문으로 재작성한다.

서버는 대화를 저장하지 않는다. 클라이언트가 매 요청에 최근 대화를 실어 보내고,
이 서비스가 그것을 근거로 대명사·생략을 해소한 자족적인 질문 한 문장을 만든다.
이후 파이프라인(Safety Guard·Intent 분류·검색·근거계획)은 재작성된 질문을 쓴다.
"""
from __future__ import annotations

import re
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
    """재작성 결과와 판단 근거."""

    standalone_question: str = Field(
        description="직전 대화 없이도 단독으로 이해되는 한국어 질문 한 문장"
    )
    rewritten: bool = Field(
        description="원래 질문을 실제로 바꿨는지. 이미 자족적이면 false"
    )
    reason: str = Field(description="재작성 여부 판단 이유")


@dataclass(frozen=True)
class QueryRewriteResult:
    """파이프라인이 사용할 질문과 재작성 메타데이터."""

    question: str
    original_question: str
    rewritten: bool
    reason: str
    error: str | None = None


QUERY_REWRITE_PROMPT = """너는 건강정보 챗봇의 질문 정규화기다.
직전 대화를 참고해, 사용자의 마지막 발화를 **단독으로 이해되는 질문 한 문장**으로 바꿔라.

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

[이전 대화 요약]
{summary}

[직전 대화]
{history}

[사용자의 마지막 발화]
{question}
"""


CONTEXT_REFERENCE_PATTERN = re.compile(
    r"(?:^|\s)(?:그거|그걸|그것|그건|그게|그 약|그 수치|그 검사|그 결과|"
    r"이거|이걸|이것|이건|이게|저거|저걸|저것|아까|앞에서|방금|"
    r"그러면|그럼|그렇게|그대로)(?:\s|은|는|이|가|을|를|도|의|로|\?|$)"
)


OMITTED_TARGET_FOLLOW_UP_PATTERN = re.compile(
    r"^(?:더\s*)?(?:"
    r"(?:낮추|높이|줄이|늘리|관리하|예방하|개선하|유지하|먹|복용하|끊|중단하)"
    r"(?:려면|려면은|면|어도|아도|는\s*방법|는\s*법)|"
    r"왜\s*(?:높|낮)(?:아|은|은\s*거|게|으면)|"
    r"(?:(?:정상|적정|권장|위험|높은|낮은)\s*)?"
    r"(?:수치|범위|기준|값|단위|부작용|효능|효과|원인|증상|예방법|주의사항)"
    r"(?:은|는|이|가|을|를)?(?:\s|[?？]|$)|"
    r"어떻게\s*(?:해야|관리|낮추|높이|줄이|늘리)"
    r")"
)


EXPLICIT_TOPIC_PATTERN = re.compile(
    r"(?:^|\s)[가-힣A-Za-z0-9][가-힣A-Za-z0-9·+\-/]{1,30}"
    r"(?:을|를|은|는|이|가|의)(?=\s|[?？]|$)"
)


def needs_context_rewrite(question: str, history=(), summary: str = "") -> bool:
    """이전 문맥이 필요할 가능성이 있는 질문을 재작성 대상으로 판정한다.

    명확히 자족적인 질문만 건너뛰고, 어느 쪽인지 애매하면 재작성 LLM이
    최종 판단하도록 전달한다. 의료용어 DB 연결 전에는 한국어 조사로 드러나는
    명시적 주제를 사용하며, DB 연결 후에는 용어 탐지 결과를 추가할 수 있다.

    작성자: 김진우
    """
    normalized = re.sub(r"\s+", " ", str(question or "").strip())
    has_context = bool(history) or bool(str(summary or "").strip())
    if not normalized or not has_context:
        return False
    if CONTEXT_REFERENCE_PATTERN.search(normalized):
        return True
    if OMITTED_TARGET_FOLLOW_UP_PATTERN.search(normalized):
        return True
    if EXPLICIT_TOPIC_PATTERN.search(normalized):
        return False
    return True


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
    """직전 대화가 있을 때만 LLM을 호출해 질문을 독립형으로 만든다."""

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
        if not needs_context_rewrite(question, turns, summary_text):
            return QueryRewriteResult(
                question=question,
                original_question=question,
                rewritten=False,
                reason="질문이 단독으로 이해되어 재작성하지 않았습니다.",
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
                error=f"{type(exc).__name__}: {exc}",
            )

        standalone = (result.standalone_question or "").strip()
        if not standalone:
            return QueryRewriteResult(
                question=question,
                original_question=question,
                rewritten=False,
                reason="재작성 결과가 비어 있어 원래 질문을 사용했습니다.",
                error="empty_standalone_question",
            )

        return QueryRewriteResult(
            question=standalone,
            original_question=question,
            rewritten=bool(result.rewritten) and standalone != question,
            reason=result.reason or "",
        )


def build_query_rewriter() -> QueryRewriter:
    """FastAPI lifespan에서 공유할 질문 재작성 체인을 만든다."""
    prompt = ChatPromptTemplate.from_template(QUERY_REWRITE_PROMPT)
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    return QueryRewriter(prompt | llm.with_structured_output(RewrittenQuery))
