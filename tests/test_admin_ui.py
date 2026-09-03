"""개발자 모니터링 웹 UI 정적 자산 테스트.

작성자: 김진우
수정: 고수연
"""

from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.admin_frontend import app


ADMIN_FRONTEND_ROOT = (
    Path(__file__).resolve().parents[1] / "app" / "frontends" / "admin"
)
SHARED_FRONTEND_ROOT = (
    Path(__file__).resolve().parents[1] / "app" / "frontends" / "shared"
)


class AdminWebUiTest(unittest.TestCase):
    """개발자 UI의 필수 화면과 API 연결 계약을 확인한다."""

    def test_required_assets_exist(self) -> None:
        self.assertTrue((ADMIN_FRONTEND_ROOT / "index.html").is_file())
        self.assertTrue((ADMIN_FRONTEND_ROOT / "assets" / "styles.css").is_file())
        self.assertTrue((ADMIN_FRONTEND_ROOT / "assets" / "app.js").is_file())
        self.assertTrue((SHARED_FRONTEND_ROOT / "images" / "heapy-logo.png").is_file())
        self.assertTrue((SHARED_FRONTEND_ROOT / "images" / "heapy-doctor.png").is_file())

    def test_admin_page_is_served(self) -> None:
        response = TestClient(app).get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("PROJECT ENVIRONMENT", response.text)

    def test_chat_contract_is_wired(self) -> None:
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn('fetch("/chat/stream"', script)
        self.assertIn('eventName === "token"', script)
        self.assertIn('eventName === "complete"', script)
        self.assertIn("sanitizeAnswerText(data.answer)", script)
        self.assertIn("sanitizeAnswerText", script)
        self.assertIn("function renderMarkdown", script)
        self.assertIn("function escapeHtml", script)
        self.assertIn("bubble.innerHTML = renderMarkdown", script)
        self.assertIn("<strong>$1</strong>", script)
        self.assertIn("STREAM_CHARACTER_DELAY_MS", script)
        self.assertIn("createTokenPacer", script)
        self.assertIn("await tokenPacer.drain()", script)
        self.assertIn("data.citations", script)
        self.assertIn("data.chunks", script)
        self.assertIn("question: normalized", script)
        self.assertIn("data.answer", script)
        self.assertIn("data.intent", script)

    def test_supabase_login_and_logout_are_wired(self) -> None:
        """로그인 게이트와 세션 복원·로그아웃 연결을 확인한다."""
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="loginForm"', markup)
        self.assertIn('id="logoutButton"', markup)
        self.assertIn('fetch("/auth/login"', script)
        self.assertIn('fetch("/auth/signup"', script)
        self.assertIn('fetchWithSession("/conversations"', script)
        self.assertIn('fetch("/auth/me"', script)
        self.assertIn('fetch("/auth/refresh"', script)
        self.assertIn('fetch("/auth/logout"', script)
        self.assertIn("fetchChatStream", script)

    def test_korean_mvp_status_is_visible(self) -> None:
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("PROJECT ENVIRONMENT", markup)
        self.assertIn("의료진의 진단을 대신하지 않습니다", markup)
        self.assertIn("근거 청크", script)
        self.assertIn("응답 결과 JSON", script)
        self.assertIn('lang="ko"', markup)

    def test_figma_theme_tokens_are_applied(self) -> None:
        """Figma 와이어프레임에서 가져온 핵심 색상 토큰을 확인한다."""
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("--purple: #7b68e8", styles)
        self.assertIn("--ink: #173a31", styles)
        self.assertIn('name="theme-color" content="#7b68e8"', markup)

    def test_brand_and_doctor_images_are_wired(self) -> None:
        """브랜드 로고와 AI 의사 아바타가 화면 슬롯에 연결되는지 확인한다."""
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertGreaterEqual(markup.count("/images/heapy-logo.png"), 2)
        self.assertGreaterEqual(markup.count("/images/heapy-doctor.png"), 2)
        self.assertIn("/images/heapy-doctor.png", script)

    def test_sidebar_shows_live_project_environment(self) -> None:
        """좌측 패널이 메뉴 대신 실제 프로젝트 환경을 표시하는지 확인한다."""
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn("건강 리포트", markup)
        self.assertNotIn("건강 기록", markup)
        self.assertNotIn("MVP 환경 현황", markup)
        self.assertIn("Pinecone collections", markup)
        self.assertIn('fetch("/health"', script)
        self.assertIn("data.indexed_chunks", script)
        self.assertIn("data.embed_model", script)
        self.assertIn("data.vector_backend", script)
        self.assertIn("overflow-wrap: anywhere", styles)

    def test_checkup_record_dropdown_is_wired(self) -> None:
        """건강검진 회차 드롭다운이 기본 최신 회차 선택으로 연결됐는지 확인한다."""
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="checkupRecordSelect"', markup)
        self.assertIn('fetchWithSession("/me/checkup/records"', script)
        self.assertIn("가장 최신 검진", script)
        self.assertIn("checkupRecords[0]?.record_id", script)
        self.assertIn("record_id=${encodeURIComponent(selectedCheckupRecordId)}", script)
        self.assertIn('elements.checkupRecordSelect.addEventListener("change"', script)
        self.assertIn(".checkup-record-select", styles)

    def test_bio_line_chart_shares_one_time_axis(self) -> None:
        """생체 꺾은선이 시리즈를 나열하지 않고 공통 시간축에 겹쳐 그리는지 확인한다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("const axis = [...new Set(plots.flat().map((point) => point.x))].sort()", script)
        self.assertIn("position.get(key)", script)
        self.assertNotIn("points.indexOf(itemPoints[0])", script)
        # 단위가 다른 체중·BMI는 좌우 축을 나눠 각 선의 변화를 살린다.
        self.assertIn('axis: "right"', script)
        self.assertIn("const dualAxis = Boolean(leftScale && rightScale)", script)
        self.assertIn('"우축"', script)
        self.assertIn("stroke-width: 1.6", styles)
        # 전역 svg 규칙이 글자에 외곽선을 덧그리고 계열 색을 덮어쓰지 않도록 막는다.
        self.assertIn("svg text { stroke: none; }", styles)
        self.assertIn("stroke: none; font-size: 9.5px; font-weight: 400", styles)
        self.assertIn("style: `stroke: ${color}`", script)
        self.assertIn("style: `fill: ${color}`", script)

    def test_question_audit_cards_are_wired(self) -> None:
        """질문별 접이식 감사 카드와 검색·안전 메타데이터 연결을 확인한다."""
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("질문별 감사 기록", markup)
        self.assertIn('id="auditCardList"', markup)
        self.assertIn('document.createElement("details")', script)
        self.assertIn("data.retrieval_assessment", script)
        self.assertIn("data.risk_level", script)
        self.assertIn("data.audit_status", script)
        self.assertIn("data.audit_summary", script)
        self.assertIn('message.dataset.started !== "true"', script)
        self.assertIn('"chunk-scroll-content"', script)
        self.assertNotIn('detail.className = "chunk-detail"', script)
        self.assertNotIn('"전체 청크 보기"', script)
        self.assertIn("chunks.forEach", script)
        self.assertNotIn("chunks.slice(0, 6)", script)
        self.assertIn("max-height: calc(9.5px * 1.55 * 5)", styles)
        self.assertIn("overflow-y: auto", styles)
        self.assertIn("overscroll-behavior: contain", styles)
        self.assertNotIn("background: #faf9fe", styles)
        self.assertNotIn(".chunk-expand-button", styles)
        self.assertIn("[hidden] { display: none !important; }", styles)

    def test_recommended_questions_use_a_curated_random_pool(self) -> None:
        """추천 질문이 외부 API 없이 검증된 풀에서 무작위 선택되는지 확인한다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn("const recommendationPool = [", script)
        self.assertIn("function selectRandomRecommendations", script)
        self.assertIn("function renderSuggestionCards", script)
        self.assertIn("Math.random()", script)
        self.assertGreaterEqual(script.count("question:"), 16)
        self.assertNotIn('fetch("/recommendations"', script)

    @patch("app.admin_frontend.requests.post")
    def test_chat_stream_is_proxied_without_buffering(self, post: Mock) -> None:
        """개발자 UI가 백엔드 SSE 이벤트를 버퍼링 없이 전달한다."""
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
        self.assertEqual(
            response.headers["content-type"],
            "text/event-stream; charset=utf-8",
        )
        self.assertIn("event: token", response.text)
        self.assertIn(
            "heapy_access_token=access-token",
            post.call_args.kwargs["headers"]["Cookie"],
        )
        backend_response.close.assert_called_once()

    @patch("app.admin_frontend.requests.request")
    def test_login_proxy_forwards_backend_session_cookie(self, request: Mock) -> None:
        """개발자 UI가 백엔드 로그인 쿠키를 브라우저에 전달한다."""
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

    @patch("app.admin_frontend.requests.request")
    def test_health_proxy_uses_main_api(self, request: Mock) -> None:
        """개발자 환경 패널의 상태 조회를 메인 API로 중계한다."""
        backend_response = Mock(
            status_code=200,
            content=b'{"status":"ok"}',
            headers={"content-type": "application/json"},
            raw=Mock(headers=Mock(getlist=Mock(return_value=[]))),
        )
        request.return_value = backend_response

        response = TestClient(app).get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(
            request.call_args.args[:2],
            ("GET", "http://localhost:8000/health"),
        )

    @patch("app.admin_frontend.requests.request")
    def test_checkup_records_proxy_uses_main_api(self, request: Mock) -> None:
        """건강검진 회차 드롭다운 조회를 메인 API로 중계한다."""
        backend_response = Mock(
            status_code=200,
            content=b'[{"record_id":"record-1","measured_at":"2026-03-14"}]',
            headers={"content-type": "application/json"},
            raw=Mock(headers=Mock(getlist=Mock(return_value=[]))),
        )
        request.return_value = backend_response

        response = TestClient(app).get("/me/checkup/records")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["record_id"], "record-1")
        self.assertEqual(
            request.call_args.args[:2],
            ("GET", "http://localhost:8000/me/checkup/records"),
        )

    @patch("app.admin_frontend.requests.request")
    def test_checkup_proxy_forwards_selected_record_query(self, request: Mock) -> None:
        """드롭다운이 붙인 record_id 조회 조건을 메인 API까지 전달한다."""
        backend_response = Mock(
            status_code=200,
            content=b'{"measured_at":"2024-02-02","items":[]}',
            headers={"content-type": "application/json"},
            raw=Mock(headers=Mock(getlist=Mock(return_value=[]))),
        )
        request.return_value = backend_response

        response = TestClient(app).get("/me/checkup", params={"record_id": "record-9"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            request.call_args.args[:2],
            ("GET", "http://localhost:8000/me/checkup?record_id=record-9"),
        )


if __name__ == "__main__":
    unittest.main()
