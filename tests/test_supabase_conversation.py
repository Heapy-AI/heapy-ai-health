"""Supabase Data API 대화 저장소 테스트.

작성자: 김진우
"""

import unittest
from unittest.mock import Mock, patch

from app.services.supabase_conversation import SupabaseConversationService


class SupabaseConversationServiceTest(unittest.TestCase):
    """사용자 JWT 전달과 원자적 대화 저장 RPC 계약을 검증한다."""

    @patch("app.services.supabase_conversation.requests.request")
    def test_append_turn_uses_user_jwt_and_rpc(self, request: Mock) -> None:
        response = Mock(ok=True, status_code=204, content=b"")
        request.return_value = response
        service = SupabaseConversationService(
            "https://example.supabase.co",
            "publishable-key",
        )

        service.append_turn(
            "user-access-token",
            "11111111-1111-1111-1111-111111111111",
            "질문",
            "답변",
            "대화 요약",
        )

        _, url = request.call_args.args
        kwargs = request.call_args.kwargs
        self.assertEqual(url, "https://example.supabase.co/rest/v1/rpc/append_chat_turn")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer user-access-token")
        self.assertEqual(kwargs["headers"]["apikey"], "publishable-key")
        self.assertEqual(kwargs["json"]["p_summary"], "대화 요약")


if __name__ == "__main__":
    unittest.main()
