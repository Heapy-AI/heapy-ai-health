"""예/아니요 표준용어 확인 상태 회귀 테스트."""
from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.state import state
from app.routers import chat
from app.services.chat_orchestrator import ChatOrchestrationResult
from app.services.query_confirmation import QueryConfirmationStore
from app.services.intent_classifier import Intent


class _FakeConfirmationOrchestrator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def answer(self, question: str, *, confirmed_term: dict | None = None):
        self.calls.append((question, confirmed_term))
        if confirmed_term is None:
            return ChatOrchestrationResult(
                intent=Intent.SIMPLE_LOOKUP,
                confidence=1.0,
                probabilities={"simple_lookup": 1.0},
                uncertain=False,
                model_version="test",
                intent_source="query_resolver",
                guard_triggered=False,
                guard_reason=None,
                matched_patterns=[],
                answer="혹시 '간수치'를 물어보신 걸까요?",
                grounded=None,
                query_confirmation=True,
                confirmation_question="혹시 '간수치'를 물어보신 걸까요?",
                resolved_terms=[
                    {
                        "input": "ㄱㅅㅊ",
                        "canonical_key": "AST",
                        "canonical_name": "간수치",
                        "term_type": "SCREENING",
                        "score": 0.97,
                        "match_kind": "initials",
                        "matched_alias": "간수치",
                    }
                ],
                resolution_status="CONFIRM",
            )
        return ChatOrchestrationResult(
            intent=Intent.SIMPLE_LOOKUP,
            confidence=1.0,
            probabilities={"simple_lookup": 1.0},
            uncertain=False,
            model_version="test",
            intent_source="query_resolver",
            guard_triggered=False,
            guard_reason=None,
            matched_patterns=[],
            answer=f"확정 검색: {confirmed_term['canonical_name']}",
            grounded=None,
            resolved_query=question.replace("ㄱㅅㅊ", "간수치"),
            resolved_terms=[confirmed_term],
            resolution_status="RESOLVED",
        )


class QueryConfirmationApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_orchestrator = state.get("chat_orchestrator")
        self.previous_store = state.get("query_confirmation_store")
        self.fake = _FakeConfirmationOrchestrator()
        state["chat_orchestrator"] = self.fake
        state["query_confirmation_store"] = QueryConfirmationStore()
        app = FastAPI()
        app.include_router(chat.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        if self.previous_orchestrator is None:
            state.pop("chat_orchestrator", None)
        else:
            state["chat_orchestrator"] = self.previous_orchestrator
        if self.previous_store is None:
            state.pop("query_confirmation_store", None)
        else:
            state["query_confirmation_store"] = self.previous_store

    def test_yes_uses_server_confirmation_state_without_re_resolving(self) -> None:
        question = "나 ㄱㅅㅊ가 너무 낮게 나왔어"
        first = self.client.post("/chat", json={"question": question})

        self.assertEqual(first.status_code, 200)
        payload = first.json()
        self.assertTrue(payload["query_confirmation"])
        self.assertTrue(payload["confirmation_id"])

        second = self.client.post(
            "/chat",
            json={
                "question": question,
                "confirmation_id": payload["confirmation_id"],
                "confirmation_answer": True,
            },
        )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(self.fake.calls), 2)
        self.assertEqual(self.fake.calls[1][0], question)
        self.assertEqual(self.fake.calls[1][1]["canonical_name"], "간수치")
        self.assertFalse(second.json()["query_confirmation"])


if __name__ == "__main__":
    unittest.main()
