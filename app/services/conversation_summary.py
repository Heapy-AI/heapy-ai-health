"""슬라이딩 윈도 밖으로 밀려나는 대화를 압축해 유지한다(Summary Memory).

최근 N턴은 원문 그대로 쓰고(Buffer Window), 창 밖으로 나가는 턴만 기존 요약과
합쳐 새 요약을 만든다. 로그인 환경에서는 서버가 Supabase 세션에 요약을 저장하고,
Supabase 미설정 로컬 환경에서는 클라이언트가 응답의 요약을 다음 요청에 전달한다.

요약은 질문 재작성기에만 전달한다. 답변 생성기는 승인된 근거 계획만 보아야
근거충실도 계약이 유지되기 때문이다.
"""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import (
    CHAT_HISTORY_MAX_TURNS,
    CONVERSATION_SUMMARY_MAX_CHARS,
    MODEL,
)
from app.services.query_rewriter import ConversationTurn, format_history


@dataclass(frozen=True)
class SummaryUpdateResult:
    """갱신된 요약과 처리 메타데이터."""

    summary: str
    updated: bool
    reason: str
    error: str | None = None


CONVERSATION_SUMMARY_PROMPT = """너는 건강정보 챗봇의 대화 기록 요약기다.
기존 요약과 새로 밀려난 대화를 합쳐, 이후 대화를 이해하는 데 필요한 사실만 남겨라.

규칙:
1. 사용자가 **직접 밝힌** 건강 상태, 복용 중인 약, 관심 주제만 적는다.
2. 챗봇이 이미 안내한 주제는 한 줄로 압축한다. 답변 본문을 옮기지 않는다.
3. 대화에 없는 사실을 추측하거나 보충하지 않는다.
4. 이름·연락처·주민등록번호·주소 같은 식별정보는 요약에 담지 않는다.
5. 진단이나 판단을 내리지 않는다. 사용자가 말한 것을 그대로 기술한다.
6. 한국어 사실 나열형으로 {max_chars}자 이내로 쓴다. 인사말이나 설명을 붙이지 않는다.
7. 남길 내용이 없으면 빈 문자열을 출력한다.

[기존 요약]
{previous_summary}

[새로 밀려난 대화]
{evicted}
"""


def select_evicted_turns(
    history: list[ConversationTurn],
    max_turns: int = CHAT_HISTORY_MAX_TURNS,
) -> list[ConversationTurn]:
    """이번 턴이 끝난 뒤 슬라이딩 윈도 밖으로 나갈 대화를 고른다.

    클라이언트도 같은 상한으로 자르므로 양쪽이 보는 '밀려난 턴'이 일치한다.
    """
    if len(history) <= max_turns:
        return []
    return history[: len(history) - max_turns]


class ConversationSummarizer:
    """창 밖으로 밀려난 대화만 기존 요약에 병합한다."""

    def __init__(self, chain, max_chars: int = CONVERSATION_SUMMARY_MAX_CHARS) -> None:
        self._chain = chain
        self._max_chars = max_chars

    def update(
        self,
        previous_summary: str,
        evicted_turns: list[ConversationTurn],
    ) -> SummaryUpdateResult:
        """밀려난 대화가 있을 때만 요약을 다시 만든다.

        실패하면 기존 요약을 그대로 유지한다. 요약은 보조 기능이므로
        갱신 실패가 대화를 막아서는 안 된다.
        """
        previous = (previous_summary or "").strip()
        if not evicted_turns:
            return SummaryUpdateResult(
                summary=previous,
                updated=False,
                reason="창 밖으로 밀려난 대화가 없습니다.",
            )

        try:
            raw = self._chain.invoke(
                {
                    "previous_summary": previous or "(없음)",
                    "evicted": format_history(evicted_turns),
                    "max_chars": self._max_chars,
                }
            )
        except Exception as exc:
            return SummaryUpdateResult(
                summary=previous,
                updated=False,
                reason="요약 갱신에 실패해 기존 요약을 유지했습니다.",
                error=f"{type(exc).__name__}: {exc}",
            )

        summary = str(raw).strip()[: self._max_chars]
        if not summary:
            return SummaryUpdateResult(
                summary=previous,
                updated=False,
                reason="요약할 내용이 없어 기존 요약을 유지했습니다.",
            )
        return SummaryUpdateResult(
            summary=summary,
            updated=summary != previous,
            reason=f"{len(evicted_turns)}턴을 요약에 반영했습니다.",
        )


def build_conversation_summarizer() -> ConversationSummarizer:
    """FastAPI lifespan에서 공유할 대화 요약 체인을 만든다."""
    prompt = ChatPromptTemplate.from_template(CONVERSATION_SUMMARY_PROMPT)
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    return ConversationSummarizer(prompt | llm | StrOutputParser())
