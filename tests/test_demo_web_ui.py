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

    def test_sidebar_is_kept_without_project_environment(self) -> None:
        markup = (DEMO_ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn('class="sidebar"', markup)
        self.assertIn("건강정보 상담", markup)
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

    def test_streaming_chat_and_user_sources_are_wired(self) -> None:
        script = (DEMO_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn('fetch("/chat/stream"', script)
        self.assertIn('eventName === "token"', script)
        self.assertIn('eventName === "complete"', script)
        self.assertIn("답변 출처", script)
        self.assertIn("sanitizeAnswerText", script)

    @patch("app.demo.requests.post")
    def test_chat_stream_is_proxied_without_buffering(self, post: Mock) -> None:
        """백엔드 SSE 이벤트가 사용자 UI 응답으로 그대로 전달되는지 확인한다."""
        backend_response = Mock()
        backend_response.ok = True
        backend_response.iter_content.return_value = iter(
            [b'event: token\ndata: {"text":"hello"}\n\n']
        )
        post.return_value = backend_response

        response = TestClient(app).post(
            "/chat/stream",
            json={"question": "공복혈당이 무엇인가요?"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertIn("event: token", response.text)
        post.assert_called_once()
        backend_response.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
