"""사용자 Access Token과 RLS를 사용하는 Supabase 대화 저장소.

작성자: 김진우
"""

from typing import Any
from urllib.parse import quote

import requests


class SupabaseConversationError(RuntimeError):
    """Supabase Data API 대화 저장소 오류."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class SupabaseConversationService:
    """RLS를 통과한 사용자 자신의 대화만 읽고 저장한다."""

    def __init__(self, url: str, publishable_key: str) -> None:
        self.url = url.rstrip("/")
        self.publishable_key = publishable_key

    @property
    def configured(self) -> bool:
        """Data API 호출에 필요한 설정 존재 여부를 반환한다."""
        return bool(self.url and self.publishable_key)

    def list_sessions(self, access_token: str) -> list[dict[str, Any]]:
        """현재 사용자의 대화 세션을 최근 순으로 반환한다."""
        return self._request(
            "GET",
            "/rest/v1/chat_sessions"
            "?select=session_id,title,summary,created_at,updated_at"
            "&order=updated_at.desc",
            access_token,
        )

    def create_session(self, access_token: str, user_id: str) -> dict[str, Any]:
        """현재 사용자 소유의 빈 대화 세션을 만든다."""
        rows = self._request(
            "POST",
            "/rest/v1/chat_sessions",
            access_token,
            json={"user_id": user_id, "summary": ""},
            prefer="return=representation",
        )
        if not rows:
            raise SupabaseConversationError("대화 세션을 생성하지 못했습니다.", 502)
        return rows[0]

    def get_session(self, access_token: str, session_id: str) -> dict[str, Any]:
        """소유권이 확인된 대화 세션 한 건을 반환한다."""
        encoded = quote(session_id, safe="")
        rows = self._request(
            "GET",
            "/rest/v1/chat_sessions"
            f"?session_id=eq.{encoded}"
            "&select=session_id,title,summary,created_at,updated_at"
            "&limit=1",
            access_token,
        )
        if not rows:
            raise SupabaseConversationError("대화 세션을 찾을 수 없습니다.", 404)
        return rows[0]

    def get_messages(
        self,
        access_token: str,
        session_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """대화 메시지를 저장 순서대로 반환한다."""
        encoded = quote(session_id, safe="")
        path = (
            "/rest/v1/chat_messages"
            f"?session_id=eq.{encoded}"
            "&select=message_id,role,content,created_at,message_order"
        )
        if limit is None:
            path += "&order=message_order.asc"
            return self._request("GET", path, access_token)
        path += f"&order=message_order.desc&limit={max(1, limit)}"
        rows = self._request("GET", path, access_token)
        return list(reversed(rows))

    def append_turn(
        self,
        access_token: str,
        session_id: str,
        user_content: str,
        assistant_content: str,
        summary: str,
    ) -> None:
        """사용자·어시스턴트 메시지와 최신 요약을 원자적으로 저장한다."""
        self._request(
            "POST",
            "/rest/v1/rpc/append_chat_turn",
            access_token,
            json={
                "p_session_id": session_id,
                "p_user_content": user_content,
                "p_assistant_content": assistant_content,
                "p_summary": summary,
            },
        )

    def delete_session(self, access_token: str, session_id: str) -> None:
        """현재 사용자가 소유한 대화 세션을 삭제한다."""
        encoded = quote(session_id, safe="")
        self._request(
            "DELETE",
            f"/rest/v1/chat_sessions?session_id=eq.{encoded}",
            access_token,
        )

    def get_profile(self, access_token: str, user_id: str) -> dict[str, Any] | None:
        """현재 사용자의 공개 프로필을 반환한다."""
        encoded = quote(user_id, safe="")
        rows = self._request(
            "GET",
            f"/rest/v1/users?user_id=eq.{encoded}&select=user_id,name,birth_date,sex&limit=1",
            access_token,
        )
        return rows[0] if rows else None

    def _request(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        json: dict[str, Any] | None = None,
        prefer: str = "",
    ) -> list[dict[str, Any]]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "apikey": self.publishable_key,
        }
        if prefer:
            headers["Prefer"] = prefer
        try:
            response = requests.request(
                method,
                f"{self.url}{path}",
                headers=headers,
                json=json,
                timeout=(5, 15),
            )
        except requests.RequestException as exc:
            raise SupabaseConversationError(
                "대화 저장소에 연결할 수 없습니다.", 503
            ) from exc
        if not response.ok:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            message = str(
                payload.get("message")
                or payload.get("details")
                or "대화 저장소 요청에 실패했습니다."
            )
            status_code = 404 if response.status_code == 404 else response.status_code
            raise SupabaseConversationError(message, status_code)
        if response.status_code == 204 or not response.content:
            return []
        payload = response.json()
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return [payload]
        return []
