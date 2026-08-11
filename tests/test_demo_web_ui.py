"""사용자 시연용 웹 UI 정적 자산과 프록시 계약 테스트.

작성자: 김진우
"""

from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.demo import app


DEMO_ROOT = Path(__file__).resolve().parents[1] / "app" / "demo_web"


class DemoWebUiTest(unittest.TestCase):
    """사용자 UI가 검증 정보 없이 별도 화면으로 제공되는지 확인한다."""

    def test_demo_page_is_served(self) -> None:
        response = TestClient(app).get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("HEAPY 건강 AI", response.text)

    def test_required_assets_exist(self) -> None:
        self.assertTrue((DEMO_ROOT / "index.html").is_file())
        self.assertTrue((DEMO_ROOT / "assets" / "styles.css").is_file())
        self.assertTrue((DEMO_ROOT / "assets" / "app.js").is_file())

        markup = (DEMO_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('/assets/styles.css?v=', markup)
        self.assertIn('/assets/app.js?v=', markup)
        self.assertIn('id="loginForm"', markup)
        self.assertIn('id="logoutButton"', markup)
        self.assertIn('id="conversationLoading"', markup)
        self.assertIn('class="session-loading-spinner"', markup)
        self.assertIn('id="deleteConversationDialog"', markup)
        self.assertIn('id="deleteConversationTitle"', markup)
        self.assertIn('id="initialLoadingScreen"', markup)
        self.assertIn('id="authScreen" class="auth-screen" aria-labelledby="loginTitle" hidden', markup)

    def test_initial_loading_screen_hides_auth_flash_during_session_restore(self) -> None:
        """세션 복원 전에는 전용 시작 화면만 표시한다."""
        markup = (DEMO_ROOT / "index.html").read_text(encoding="utf-8")
        script = (DEMO_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (DEMO_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("건강한 대화를 준비하고 있어요", markup)
        self.assertIn("hideInitialLoadingScreen()", script)
        self.assertIn("finally", script)
        self.assertIn(".initial-loading-screen", styles)
        self.assertIn("@keyframes initial-orbit-spin", styles)
        self.assertIn("@keyframes initial-screen-out", styles)

    def test_sidebar_shows_conversations_without_service_tabs(self) -> None:
        markup = (DEMO_ROOT / "index.html").read_text(encoding="utf-8")
        styles = (DEMO_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('class="sidebar"', markup)
        self.assertIn('id="conversationList"', markup)
        self.assertIn('id="newConversationButton"', markup)
        self.assertNotIn('class="service-menu"', markup)
        self.assertNotIn("건강정보 상담", markup)
        self.assertNotIn("서비스 안내", markup)
        self.assertIn("white-space: nowrap", styles)
        self.assertIn("min-width: max-content", styles)
        self.assertNotIn("PROJECT ENVIRONMENT", markup)
        self.assertNotIn("Pinecone collections", markup)
        self.assertNotIn("environment-card", markup)

    def test_right_audit_dashboard_is_removed(self) -> None:
        markup = (DEMO_ROOT / "index.html").read_text(encoding="utf-8")
        script = (DEMO_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn("insight-panel", markup)
        self.assertNotIn("ANSWER AUDIT", markup)
        self.assertNotIn("응답 결과 JSON", script)
        self.assertNotIn("audit_status", script)

    def test_streaming_chat_matches_developer_chat_without_sources(self) -> None:
        script = (DEMO_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn('fetch("/chat/stream"', script)
        self.assertIn('eventName === "token"', script)
        self.assertIn('eventName === "complete"', script)
        self.assertIn("createTokenPacer", script)
        self.assertIn("renderMarkdown", script)
        self.assertIn("sanitizeAnswerText", script)
        self.assertIn("history: conversationHistory", script)
        self.assertIn("summary: conversationSummary", script)
        self.assertIn("session_id: currentSessionId", script)
        self.assertIn('fetch("/auth/me"', script)
        self.assertIn('fetchWithSession("/conversations"', script)
        self.assertIn("loadConversation(session.session_id)", script)
        self.assertIn("currentSessionId = sessionId", script)
        self.assertIn("updateConversationSessionPreview(data)", script)
        self.assertNotIn("답변 출처", script)
        self.assertNotIn("source-details", script)

    def test_session_loading_uses_centered_loader_instead_of_chat_bubble(self) -> None:
        """세션 조회 중에는 답변 생성용 말풍선 대신 중앙 로더를 표시한다."""
        script = (DEMO_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (DEMO_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
        load_conversation = script.split("async function loadConversation(sessionId)", 1)[1]
        load_conversation = load_conversation.split("function updateConversationSessionPreview", 1)[0]

        self.assertIn("elements.conversationLoading.hidden = false", load_conversation)
        self.assertIn("elements.conversationLoading.hidden = true", load_conversation)
        self.assertNotIn("appendLoadingMessage()", load_conversation)
        self.assertIn(".conversation-loading", styles)
        self.assertIn("@keyframes session-loading-spin", styles)

    def test_conversation_session_has_confirmed_delete_action(self) -> None:
        """대화 세션은 확인 후 본인 세션 삭제 API를 호출한다."""
        markup = (DEMO_ROOT / "index.html").read_text(encoding="utf-8")
        script = (DEMO_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (DEMO_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("conversation-delete-button", script)
        self.assertIn("confirmConversationDeletion", script)
        self.assertIn("deleteConversationDialog.showModal()", script)
        self.assertNotIn("window.confirm(", script)
        self.assertIn('method: "DELETE"', script)
        self.assertIn("deleteConversation(session.session_id", script)
        self.assertIn("삭제한 대화와 메시지는 복구할 수 없습니다.", markup)
        self.assertIn(".conversation-delete-button", styles)
        self.assertIn(".delete-dialog::backdrop", styles)

    @patch("app.demo.requests.post")
    def test_chat_stream_is_proxied_without_buffering(self, post: Mock) -> None:
        """백엔드 SSE 이벤트가 사용자 UI 응답으로 그대로 전달되는지 확인한다."""
        backend_response = Mock()
        backend_response.ok = True
        backend_response.iter_content.return_value = iter(
            [b'event: token\ndata: {"text":"hello"}\n\n']
        )
        post.return_value = backend_response

        client = TestClient(app)
        client.cookies.set("heapy_access_token", "access-token")
        response = client.post(
            "/chat/stream",
            json={"question": "공복혈당이 무엇인가요?"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertIn("event: token", response.text)
        post.assert_called_once()
        self.assertIn("heapy_access_token=access-token", post.call_args.kwargs["headers"]["Cookie"])
        backend_response.close.assert_called_once()

    @patch("app.demo.requests.request")
    def test_login_proxy_forwards_backend_session_cookie(self, request: Mock) -> None:
        """백엔드 로그인 쿠키가 시연 UI 브라우저에 전달되는지 확인한다."""
        raw_headers = Mock()
        raw_headers.getlist.return_value = [
            "heapy_access_token=access-token; HttpOnly; Path=/; SameSite=lax"
        ]
        backend_response = Mock(
            status_code=200,
            content=b'{"id":"user-id","email":"user@example.com"}',
            headers={"content-type": "application/json"},
            raw=Mock(headers=raw_headers),
        )
        request.return_value = backend_response

        response = TestClient(app).post(
            "/auth/login",
            json={"email": "user@example.com", "password": "password123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        backend_response.close.assert_called_once()

    @patch("app.demo.requests.request")
    def test_conversation_list_proxy_forwards_auth_cookie(self, request: Mock) -> None:
        """대화 세션 목록 조회가 인증 쿠키와 함께 메인 API로 전달되는지 확인한다."""
        backend_response = Mock(
            status_code=200,
            content=b"[]",
            headers={"content-type": "application/json"},
            raw=Mock(headers=Mock(getlist=Mock(return_value=[]))),
        )
        request.return_value = backend_response
        client = TestClient(app)
        client.cookies.set("heapy_access_token", "access-token")

        response = client.get("/conversations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        self.assertEqual(request.call_args.args[:2], ("GET", "http://localhost:8000/conversations"))
        self.assertIn("heapy_access_token=access-token", request.call_args.kwargs["headers"]["Cookie"])


if __name__ == "__main__":
    unittest.main()
