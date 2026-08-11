"""Supabase 대화 세션 API 계약 테스트.

작성자: 김진우
"""

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import conversations
from app.routers.auth import AuthenticatedSession, require_current_session


SESSION_ROW = {
    "session_id": "11111111-1111-1111-1111-111111111111",
    "title": "혈압 기준",
    "summary": "사용자가 혈압 기준을 질문했다.",
    "created_at": "2026-08-11T01:00:00+00:00",
    "updated_at": "2026-08-11T01:01:00+00:00",
}


class ConversationApiTest(unittest.TestCase):
    """로그인 사용자별 세션 목록과 메시지 조회 계약을 검증한다."""

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(conversations.router)
        app.dependency_overrides[require_current_session] = lambda: AuthenticatedSession(
            user={"id": "user-id"},
            access_token="access-token",
        )
        self.app = app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    @patch.object(conversations.conversation_service, "list_sessions")
    def test_list_conversations_uses_user_access_token(self, list_sessions) -> None:
        list_sessions.return_value = [SESSION_ROW]

        response = self.client.get("/conversations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["title"], "혈압 기준")
        list_sessions.assert_called_once_with("access-token")

    @patch.object(conversations.conversation_service, "get_messages")
    @patch.object(conversations.conversation_service, "get_session")
    def test_get_conversation_returns_stored_messages(
        self,
        get_session,
        get_messages,
    ) -> None:
        get_session.return_value = SESSION_ROW
        get_messages.return_value = [
            {
                "message_id": "22222222-2222-2222-2222-222222222222",
                "role": "user",
                "content": "정상 혈압 기준은?",
                "created_at": "2026-08-11T01:01:00+00:00",
                "message_order": 1,
            }
        ]

        response = self.client.get(f"/conversations/{SESSION_ROW['session_id']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["messages"][0]["role"], "user")
        get_session.assert_called_once_with("access-token", SESSION_ROW["session_id"])
        get_messages.assert_called_once_with("access-token", SESSION_ROW["session_id"])


if __name__ == "__main__":
    unittest.main()
