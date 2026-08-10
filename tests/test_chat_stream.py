"""통합 챗봇 SSE 스트리밍 API 계약 테스트.

작성자: 김진우
수정: 고수연 (멀티턴 추가)
"""

import json
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.state import state
from app.routers import chat
from app.routers.chat import _CitationLabelStreamFilter
from app.services.chat_orchestrator import (
    ChatOrchestrationResult,
    ChatStreamEvent,
)
from app.services.intent_classifier import Intent


class FakeStreamingOrchestrator:
    """토큰 두 건과 완료 결과를 순서대로 생성한다."""

    def __init__(self) -> None:
        self.received_history = None
        self.received_summary = None

    def stream_answer(self, question: str, history=(), summary: str = ""):
        self.received_history = list(history)
        self.received_summary = summary
        yield ChatStreamEvent(event="token", text="안녕")
        yield ChatStreamEvent(event="token", text="하세요")
        yield ChatStreamEvent(
            event="complete",
            result=ChatOrchestrationResult(
                intent=Intent.GENERAL_CHAT,
                confidence=0.9,
                probabilities={intent.value: 0.25 for intent in Intent},
                uncertain=False,
                model_version="intent-v6-test",
                intent_source="linear_classifier",
                guard_triggered=False,
                guard_reason=None,
                matched_patterns=[],
                answer="안녕하세요",
                grounded=None,
            ),
        )


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


class ChatStreamApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_orchestrator = state.get("chat_orchestrator")
        self.orchestrator = FakeStreamingOrchestrator()
        state["chat_orchestrator"] = self.orchestrator
        app = FastAPI()
        app.include_router(chat.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        if self.previous_orchestrator is None:
            state.pop("chat_orchestrator", None)
        else:
            state["chat_orchestrator"] = self.previous_orchestrator

    def test_stream_returns_tokens_before_complete_event(self) -> None:
        response = self.client.post(
            "/chat/stream",
            json={"question": "안녕하세요"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["content-type"].startswith("text/event-stream")
        )
        events = _parse_sse(response.text)
        self.assertEqual([event for event, _ in events], ["token", "token", "complete"])
        self.assertEqual(
            "".join(data["text"] for event, data in events if event == "token"),
            events[-1][1]["answer"],
        )
        self.assertEqual(events[-1][1]["answer"], "안녕하세요")
        self.assertEqual(events[-1][1]["intent"], "general_chat")
        self.assertEqual(self.orchestrator.received_history, [])
        self.assertEqual(self.orchestrator.received_summary, "")

    def test_stream_forwards_conversation_history(self) -> None:
        """멀티턴 문맥이 오케스트레이터까지 전달되는지 확인한다."""
        response = self.client.post(
            "/chat/stream",
            json={
                "question": "그럼 식단은요?",
                "history": [
                    {"role": "user", "content": "고혈압은 어떻게 관리하나요?"},
                    {"role": "assistant", "content": "생활습관 관리가 중요합니다."},
                ],
                "summary": "사용자는 고혈압에 관심이 있다.",
            },
        )

        self.assertEqual(response.status_code, 200)
        received = self.orchestrator.received_history
        self.assertEqual(len(received), 2)
        self.assertEqual(received[0].role, "user")
        self.assertEqual(received[0].content, "고혈압은 어떻게 관리하나요?")
        self.assertEqual(received[1].role, "assistant")
        self.assertEqual(
            self.orchestrator.received_summary, "사용자는 고혈압에 관심이 있다."
        )

    def test_filter_keeps_non_citation_brackets(self) -> None:
        label_filter = _CitationLabelStreamFilter()

        output = label_filter.feed("일반 [표시]와 [C2] 근거")
        output += label_filter.flush()

        self.assertEqual(output, "일반 [표시]와  근거")


if __name__ == "__main__":
    unittest.main()
