"""시연용 웹 앱 정적 자산 테스트.

작성자: 김진우
"""

from pathlib import Path
import unittest


WEB_ROOT = Path(__file__).resolve().parents[1] / "app" / "web"


class WebUiTest(unittest.TestCase):
    """웹 앱의 필수 화면과 API 연결 계약을 확인한다."""

    def test_required_assets_exist(self) -> None:
        self.assertTrue((WEB_ROOT / "index.html").is_file())
        self.assertTrue((WEB_ROOT / "assets" / "styles.css").is_file())
        self.assertTrue((WEB_ROOT / "assets" / "app.js").is_file())
        self.assertTrue((WEB_ROOT / "assets" / "images" / "heapy-logo.png").is_file())
        self.assertTrue((WEB_ROOT / "assets" / "images" / "heapy-doctor.png").is_file())

    def test_chat_contract_is_wired(self) -> None:
        script = (WEB_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn('fetch("/chat/stream"', script)
        self.assertIn('eventName === "token"', script)
        self.assertIn('eventName === "complete"', script)
        self.assertIn("sanitizeAnswerText(data.answer)", script)
        self.assertIn("sanitizeAnswerText", script)
        self.assertIn("STREAM_CHARACTER_DELAY_MS", script)
        self.assertIn("createTokenPacer", script)
        self.assertIn("await tokenPacer.drain()", script)
        self.assertIn("data.citations", script)
        self.assertIn("data.chunks", script)
        self.assertIn("question: normalized", script)
        self.assertIn("data.answer", script)
        self.assertIn("data.intent", script)

    def test_korean_mvp_status_is_visible(self) -> None:
        markup = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        script = (WEB_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("PROJECT ENVIRONMENT", markup)
        self.assertIn("의료진의 진단을 대신하지 않습니다", markup)
        self.assertIn("근거 청크", script)
        self.assertIn("응답 결과 JSON", script)
        self.assertIn('lang="ko"', markup)

    def test_figma_theme_tokens_are_applied(self) -> None:
        """Figma 와이어프레임에서 가져온 핵심 색상 토큰을 확인한다."""
        styles = (WEB_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
        markup = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn("--purple: #7b68e8", styles)
        self.assertIn("--ink: #173a31", styles)
        self.assertIn('name="theme-color" content="#7b68e8"', markup)

    def test_brand_and_doctor_images_are_wired(self) -> None:
        """브랜드 로고와 AI 의사 아바타가 화면 슬롯에 연결되는지 확인한다."""
        markup = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        script = (WEB_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertGreaterEqual(markup.count("/assets/images/heapy-logo.png"), 2)
        self.assertGreaterEqual(markup.count("/assets/images/heapy-doctor.png"), 2)
        self.assertIn("/assets/images/heapy-doctor.png", script)

    def test_sidebar_shows_live_project_environment(self) -> None:
        """좌측 패널이 메뉴 대신 실제 프로젝트 환경을 표시하는지 확인한다."""
        markup = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        script = (WEB_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (WEB_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn("건강 리포트", markup)
        self.assertNotIn("건강 기록", markup)
        self.assertNotIn("MVP 환경 현황", markup)
        self.assertIn("Pinecone collections", markup)
        self.assertIn('fetch("/health"', script)
        self.assertIn("data.indexed_chunks", script)
        self.assertIn("data.embed_model", script)
        self.assertIn("data.vector_backend", script)
        self.assertIn("overflow-wrap: anywhere", styles)

    def test_question_audit_cards_are_wired(self) -> None:
        """질문별 접이식 감사 카드와 선검증 메타데이터 연결을 확인한다."""
        markup = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        script = (WEB_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (WEB_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("질문별 감사 기록", markup)
        self.assertIn('id="auditCardList"', markup)
        self.assertIn('document.createElement("details")', script)
        self.assertIn("data.grounding_plan", script)
        self.assertIn("data.audit_status", script)
        self.assertIn("data.audit_summary", script)
        self.assertIn('message.dataset.started !== "true"', script)
        self.assertIn("[hidden] { display: none !important; }", styles)

    def test_recommended_questions_use_a_curated_random_pool(self) -> None:
        """추천 질문이 외부 API 없이 검증된 풀에서 무작위 선택되는지 확인한다."""
        script = (WEB_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn("const recommendationPool = [", script)
        self.assertIn("function selectRandomRecommendations", script)
        self.assertIn("function renderSuggestionCards", script)
        self.assertIn("Math.random()", script)
        self.assertGreaterEqual(script.count("question:"), 16)
        self.assertNotIn('fetch("/recommendations"', script)


if __name__ == "__main__":
    unittest.main()
