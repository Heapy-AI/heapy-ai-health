"""통합 챗봇 SSE 스트리밍 API 계약 테스트.

작성자: 김진우
"""

import json
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.state import state
from app.routers import chat
from app.routers.auth import optional_current_session
from app.routers.chat import _CitationLabelStreamFilter
from app.services.chat_orchestrator import (
    ChatOrchestrationResult,
    ChatStreamEvent,
)
from app.services.intent_classifier import Intent


class FakeStreamingOrchestrator:
    """토큰 두 건과 완료 결과를 순서대로 생성한다."""

    def stream_answer(
        self,
        question: str,
        history=(),
        summary: str = "",
        *,
        confirmation_id: str = "",
        confirmation_answer: bool | None = None,
        personal_context_loader=None,
    ):
        yield ChatStreamEvent(event="progress", stage="generate_answer")
        yield ChatStreamEvent(event="token", text="안녕")
        yield ChatStreamEvent(event="token", text="하세요")
        yield ChatStreamEvent(event="progress", stage="answer_stream_complete")
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
                risk_level="normal",
                restricted_actions=[],
                response_policy="standard_grounded",
                emergency=False,
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
        state["chat_orchestrator"] = FakeStreamingOrchestrator()
        app = FastAPI()
        app.include_router(chat.router)
        app.dependency_overrides[optional_current_session] = lambda: None
        self.app = app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
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
        self.assertEqual(
            [event for event, _ in events],
            ["progress", "progress", "token", "token", "progress", "complete"],
        )
        self.assertEqual(events[0][1]["stage"], "load_conversation")
        self.assertEqual(
            events[0][1]["message"],
            "이전 대화 내용을 불러오는 중입니다",
        )
        self.assertEqual(events[1][1]["stage"], "generate_answer")
        self.assertEqual(events[1][1]["message"], "답변을 생성하는 중입니다")
        self.assertEqual(events[-2][1]["stage"], "answer_stream_complete")
        self.assertEqual(events[-2][1]["message"], "")
        self.assertEqual(
            "".join(data["text"] for event, data in events if event == "token"),
            events[-1][1]["answer"],
        )
        self.assertEqual(events[-1][1]["answer"], "안녕하세요")
        self.assertEqual(events[-1][1]["intent"], "general_chat")

    def test_filter_keeps_non_citation_brackets(self) -> None:
        label_filter = _CitationLabelStreamFilter()

        output = label_filter.feed("일반 [표시]와 [C2] 근거")
        output += label_filter.flush()

        self.assertEqual(output, "일반 [표시]와  근거")

    def test_filter_removes_lowercase_and_multiple_citation_labels(self) -> None:
        label_filter = _CitationLabelStreamFilter()

        output = label_filter.feed("효능 설명[c1, c2] 다음 문장")
        output += label_filter.flush()

        self.assertEqual(output, "효능 설명 다음 문장")


if __name__ == "__main__":
    unittest.main()
