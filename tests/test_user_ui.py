"""사용자 웹 UI 정적 자산과 프록시 계약 테스트.

작성자: 김진우
"""

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from app.main import app


USER_FRONTEND_ROOT = (
    Path(__file__).resolve().parents[1] / "app" / "frontends" / "user"
)
SHARED_FRONTEND_ROOT = (
    Path(__file__).resolve().parents[1] / "app" / "frontends" / "shared"
)


class UserWebUiTest(unittest.TestCase):
    """메인 FastAPI가 사용자 UI를 기본 화면으로 제공하는지 확인한다."""

    def test_user_page_is_served(self) -> None:
        response = TestClient(app).get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("HEAPY 건강 AI", response.text)

    def test_required_assets_exist(self) -> None:
        self.assertTrue((USER_FRONTEND_ROOT / "index.html").is_file())
        self.assertTrue((USER_FRONTEND_ROOT / "assets" / "styles.css").is_file())
        self.assertTrue((USER_FRONTEND_ROOT / "assets" / "app.js").is_file())
        self.assertTrue((SHARED_FRONTEND_ROOT / "images" / "heapy-logo.png").is_file())
        self.assertTrue((SHARED_FRONTEND_ROOT / "images" / "heapy-doctor.png").is_file())

        markup = (USER_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
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
        markup = (USER_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (USER_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (USER_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("건강한 대화를 준비하고 있어요", markup)
        self.assertIn("hideInitialLoadingScreen()", script)
        self.assertIn("finally", script)
        self.assertIn(".initial-loading-screen", styles)
        self.assertIn("@keyframes initial-orbit-spin", styles)
        self.assertIn("@keyframes initial-screen-out", styles)

    def test_recommended_questions_use_admin_random_pool(self) -> None:
        """추천 질문은 관리자 UI와 동일한 16개 풀에서 네 개를 무작위 선택한다."""
        script = (USER_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn("const recommendationPool = [", script)
        self.assertIn("function selectRandomRecommendations", script)
        self.assertIn("function renderSuggestionCards", script)
        self.assertIn("Math.random()", script)
        self.assertGreaterEqual(script.count("question:"), 16)
        self.assertIn("renderSuggestionCards();", script)

    def test_sidebar_shows_conversations_without_service_tabs(self) -> None:
        markup = (USER_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        styles = (USER_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

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
        markup = (USER_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (USER_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn("insight-panel", markup)
        self.assertNotIn("ANSWER AUDIT", markup)
        self.assertNotIn("응답 결과 JSON", script)
        self.assertNotIn("audit_status", script)

    def test_streaming_chat_matches_developer_chat_without_sources(self) -> None:
        script = (USER_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

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

    def test_streaming_progress_is_shown_below_loading_bubble(self) -> None:
        """실제 SSE 처리 단계 문구를 작은 상태 텍스트로 표시한다.

        작성자: 김진우
        """
        script = (USER_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (USER_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('status.className = "loading-status"', script)
        self.assertIn("function updateLoadingProgress", script)
        self.assertIn("function hideLoadingProgress", script)
        self.assertIn('eventName === "progress"', script)
        self.assertIn('stage === "answer_stream_complete"', script)
        self.assertIn("tokenPacer.drain().then(hideLoadingProgress)", script)
        self.assertIn('status.setAttribute("aria-live", "polite")', script)
        self.assertIn(".loading-status", styles)
        self.assertIn("font-size: 10.5px", styles)
        self.assertIn("width: 74px", styles)
        self.assertIn("align-items: flex-start", styles)

    def test_session_loading_uses_centered_loader_instead_of_chat_bubble(self) -> None:
        """세션 조회 중에는 답변 생성용 말풍선 대신 중앙 로더를 표시한다."""
        script = (USER_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (USER_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
        load_conversation = script.split("async function loadConversation(sessionId)", 1)[1]
        load_conversation = load_conversation.split("function updateConversationSessionPreview", 1)[0]

        self.assertIn("elements.conversationLoading.hidden = false", load_conversation)
        self.assertIn("elements.conversationLoading.hidden = true", load_conversation)
        self.assertNotIn("appendLoadingMessage()", load_conversation)
        self.assertIn(".conversation-loading", styles)
        self.assertIn("@keyframes session-loading-spin", styles)

    def test_conversation_session_has_confirmed_delete_action(self) -> None:
        """대화 세션은 확인 후 본인 세션 삭제 API를 호출한다."""
        markup = (USER_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (USER_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (USER_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("conversation-delete-button", script)
        self.assertIn("confirmConversationDeletion", script)
        self.assertIn("deleteConversationDialog.showModal()", script)
        self.assertNotIn("window.confirm(", script)
        self.assertIn('method: "DELETE"', script)
        self.assertIn("deleteConversation(session.session_id", script)
        self.assertIn("삭제한 대화와 메시지는 복구할 수 없습니다.", markup)
        self.assertIn(".conversation-delete-button", styles)
        self.assertIn(".delete-dialog::backdrop", styles)

if __name__ == "__main__":
    unittest.main()
