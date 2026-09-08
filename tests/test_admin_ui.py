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

    def test_lifestyle_tab_layout_is_today_then_ai_then_period_trends(self) -> None:
        """생활건강 탭이 당일 수치 → AI 분석 → 기간 버튼 → 세부 항목 그래프 순서인지 확인한다."""
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        for block_id in ('id="lifestyleToday"', 'id="lifestyleReport"', 'id="lifestyleTrends"'):
            self.assertIn(block_id, markup)
        # 기간 버튼은 AI 분석 아래, 추이 그래프 위에만 있어야 한다.
        self.assertLess(markup.index('id="lifestyleToday"'), markup.index('id="lifestyleReport"'))
        self.assertLess(markup.index('id="lifestyleReport"'), markup.index('class="lifestyle-periods"'))
        self.assertLess(markup.index('class="lifestyle-periods"'), markup.index('id="lifestyleTrends"'))
        for days in ("7", "30", "90", "180", "365"):
            self.assertIn(f'data-lifestyle-days="{days}"', markup)
        # 처음 들어가면 1주일부터 본다. 마크업의 active와 스크립트 기본값이 같아야 한다.
        self.assertIn('<button type="button" class="active" data-lifestyle-days="7">', markup)
        self.assertEqual(markup.count('class="active" data-lifestyle-days='), 1)
        self.assertIn("const LIFESTYLE_DEFAULT_DAYS = 7;", script)
        self.assertIn("let lifestyleDays = LIFESTYLE_DEFAULT_DAYS;", script)
        # 로그아웃 뒤 다시 들어와도 기본값에서 시작한다.
        self.assertIn("lifestyleDays = LIFESTYLE_DEFAULT_DAYS;\n  elements.lifestylePeriods", script)
        self.assertIn(".today-card-value", styles)
        self.assertIn("function renderLifestyleToday", script)
        self.assertIn("function renderLifestyleTrends", script)
        self.assertIn("buildTrendTable(series, days)", script)

    def test_lifestyle_ai_analysis_runs_only_on_button_click(self) -> None:
        """건강검진 탭처럼 버튼을 눌러야만 AI 분석을 요청하고 결과 영역이 열린다."""
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn('<button id="lifestyleReportButton" class="report-button" type="button">AI 요약분석</button>', markup)
        self.assertIn('<div id="lifestyleReport" class="lifestyle-report" aria-live="polite" hidden></div>', markup)
        self.assertIn("/me/lifestyle/report?domain=${encodeURIComponent(tab)}", script)
        self.assertIn('elements.lifestyleReportButton.addEventListener("click", () => loadLifestyleReport(true));', script)
        # 화면을 그릴 때는 분석을 부르지 않는다. 버튼 클릭만 유일한 실행 경로다.
        self.assertEqual(script.count("loadLifestyleReport("), 2)
        # 분석 구간은 서비스가 정한다. 화면이 기간을 실어 보내면 안 된다.
        self.assertNotIn("report?domain=${encodeURIComponent(tab)}&window_days", script)
        self.assertNotIn("lifestyleReportKey", script)
        self.assertIn("""  if (!state) {
    elements.lifestyleReport.replaceChildren();
    elements.lifestyleReport.hidden = true;
    return;
  }""", script)
        # 응답을 기다리는 사이 다른 탭으로 옮기면 그 탭 화면을 덮어쓰지 않는다.
        self.assertIn("if (tab === activeLifestyleTab) renderLifestyleReport();", script)

    def test_lifestyle_today_values_use_metric_cards(self) -> None:
        """당일 수치를 항목별 카드로 그리고 구간 평균과의 차이를 함께 보여준다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('card.className = "today-card";', script)
        self.assertIn('"today-card-value"', script)
        self.assertIn('"today-card-delta"', script)
        # 오르는 게 좋은지 나쁜지는 항목마다 달라 방향만 알린다.
        self.assertIn('`${gap > 0 ? "▲" : "▼"}', script)
        self.assertIn('"평균과 비슷"', script)
        # 당일 기록이 없는 항목은 마지막 기록일을 알려준다.
        self.assertIn('card.classList.add("is-empty");', script)
        self.assertIn(".today-card { position: relative;", styles)
        self.assertIn(".today-card-delta.flat", styles)
        # 숫자 하나로는 방향을 알 수 없어 카드 안에 최근 흐름을 곁들인다.
        self.assertIn("function buildSparkline", script)
        self.assertIn('class: "today-card-spark"', script)
        self.assertIn(".today-card-spark-line", styles)
        self.assertIn(".today-card:hover", styles)

    def test_blood_pressure_shares_one_today_card(self) -> None:
        """수축기와 이완기는 따로 읽을 일이 없어 '121/79' 한 카드로 묶는다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn('pairedWith: "diastolic", pairedLabel: "혈압"', script)
        self.assertIn("return `${text}/${otherText}`;", script)
        # 짝을 합치고 남은 쪽은 카드 목록에서 뺀다.
        self.assertIn("merged.add(partner.key);", script)
        self.assertIn("filter((item) => !merged.has(item.key))", script)
        # 그래프와 수치표는 그대로 둘로 나눠 본다.
        self.assertIn('{ title: "혈압", metrics: ["systolic", "diastolic"] }', script)

    def test_sleep_tab_shows_every_stage(self) -> None:
        """조회만 하고 버려지던 수면 단계를 항목으로 살려 구성 막대로 본다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        # 저장소가 내려주는 키는 *_minutes다. 짧은 이름으로 읽으면 값이 조용히 빈다.
        for key in ("deep_sleep_minutes", "light_sleep_minutes",
                    "rem_sleep_minutes", "awake_minutes"):
            with self.subTest(key=key):
                self.assertIn(f"detail_data?.{key}", script)
        self.assertNotIn("detail_data?.deep_sleep_min ", script)
        self.assertNotIn("detail_data?.awake_min ", script)
        # 단계는 서로 견줘야 뜻이 생기므로 쌓아서 보여 준다.
        self.assertIn('title: "수면시간 및 단계", chart: "stack"', script)
        self.assertIn("function buildStackedChart", script)
        # 누적 막대가 총 수면시간까지 보여 주므로 수면시간 단독 그래프는 두지 않는다.
        self.assertNotIn('{ title: "수면시간", metrics: ["sleepHours"] }', script)
        # 총 수면시간은 쌓지 않고 표에만 앞세운다. 단계의 합이 아니라 견줄 값이다.
        self.assertIn('metrics: ["deepSleep", "lightSleep", "remSleep", "awake"]', script)
        self.assertIn('columns: ["sleepHours", "deepSleep", "lightSleep", "remSleep", "awake"]', script)
        self.assertIn("group.columns ? toSeries(group.columns) : series", script)
        self.assertIn("buildTrendTable(tableSeries, days)", script)
        self.assertIn("group.cards || group.columns || group.metrics", script)
        # 단계는 서로 견줘야 뜻이 생기므로 카드로는 두지 않고 그래프·표에서만 본다.
        self.assertIn('cards: ["sleepHours"]', script)
        self.assertIn(".data-chart-bar.stack", styles)
        self.assertIn(".data-chart-segment.s3", styles)
        # 단계 색은 이 그래프 안에서만 덮어쓴다. 전역 계열 색을 바꾸면 혈압 미니그래프까지 물든다.
        self.assertIn('palette: "sleep-stages"', script)
        self.assertIn(".data-chart.sleep-stages {", styles)
        for color in ("#3816ba", "#7653f4", "#b19ff7", "#ff5e8e"):
            with self.subTest(color=color):
                self.assertIn(color, styles)

    def test_sleep_composition_axis_reads_in_hours_within_the_data_range(self) -> None:
        """수면 구성 축은 분이 아니라 시간으로 읽고, 값이 놓인 구간에만 눈금을 긋는다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        # 분으로 쌓되 축은 시간으로 환산해 읽는다.
        self.assertIn('unit: "시간", divisor: 60, step: 1, major: 3, min: 3, max: 9', script)
        self.assertIn("buildStackedChart(group.title, series, group.axis, days, gapDate)", script)
        # 3·6·9시간을 늘 보여 주고, 값이 벗어날 때만 3시간 단위로 넓힌다.
        self.assertIn("function stackedAxisTicks", script)
        self.assertIn("major: 3, min: 3, max: 9", script)
        self.assertIn("Math.min(baseLow, Math.floor(Math.min(...scaled) / major) * major)", script)
        self.assertIn("Math.max(baseHigh, Math.ceil(Math.max(...scaled) / major) * major)", script)
        # 3시간 배수는 실선에 숫자, 사이는 점선에 숫자 없음.
        self.assertIn("ticks.filter((tick) => tick % major === 0)", script)
        self.assertIn('tick % major === 0 ? "data-chart-guide solid" : "data-chart-guide"', script)
        self.assertIn(".data-chart-guide.solid", styles)
        # 맨 위 눈금(9시간)이 컨테이너 밖으로 나가 잘리지 않도록 위에서부터 잰다.
        self.assertIn("function chartGuideTop", script)
        self.assertIn("guide.style.top = `${chartGuideTop(tick, max)}px`;", script)
        self.assertNotIn("guide.style.bottom", script)

    def test_weekly_buckets_read_as_month_and_week(self) -> None:
        """3개월 구간의 x축은 날짜가 아니라 '7월1주'처럼 읽는다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function weekOfMonthLabel", script)
        self.assertIn("function formatBucketDate", script)
        # 목요일은 늘 그 주가 더 많이 걸친 달에 있다. 그 달과 주차로 이름을 붙인다.
        self.assertIn("monday.getTime() + 3 * 24 * 60 * 60 * 1000", script)
        self.assertIn("Math.floor((thursday.getUTCDate() - 1) / 7) + 1", script)
        self.assertIn("`${thursday.getUTCMonth() + 1}월${week}주`", script)
        # 그래프 셋과 표가 모두 같은 표기를 쓴다.
        self.assertIn("buildLineChart(group.title, series, days, gapDate)", script)
        self.assertIn("buildStackedChart(group.title, series, group.axis, days, gapDate)", script)
        self.assertIn("buildLifestyleBarChart(group.title, series[0], series[0].points, days, gapDate)", script)
        self.assertIn("value: (row) => formatBucketDate(row.date, days)", script)

    def test_sparse_buckets_are_dimmed_for_daily_totals(self) -> None:
        """기록이 절반도 안 되는 주는 일평균이 부풀므로 흐리게 그린다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        # 묶음마다 며칠이 들어갔는지 남겨야 판단할 수 있다.
        self.assertIn("count: values.length", script)
        self.assertIn("span: bucketSpan(date, days)", script)
        # 하루 누적 지표만 해당한다. 체중·혈압은 며칠 비어도 정상이다.
        self.assertIn('metric.daily === "sum" && point.span > 1 && point.count * 2 < point.span', script)
        self.assertIn('"data-chart-bar is-sparse"', script)
        self.assertIn(".data-chart-bar.is-sparse", styles)
        # 몇 일치인지 마우스로 확인할 수 있어야 한다.
        self.assertIn("function bucketCoverageText", script)
        self.assertIn("일 중 ${point.count}일 기록", script)

    def test_late_starting_records_get_a_blank_slot_and_notice(self) -> None:
        """고른 기간보다 기록이 늦게 시작했으면 직전 한 칸을 비우고 언제부터인지 알린다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        # 고른 기간의 시작과 첫 기록을 견줘 판단한다.
        self.assertIn("function windowStartBucket", script)
        self.assertIn("windowStartBucket(latestDate, days) < firstBucket", script)
        # 직전 묶음 한 칸만 비운다.
        self.assertIn("function previousBucket", script)
        self.assertIn("const gapDate = startsLate ? previousBucket(firstBucket, days) : \"\";", script)
        self.assertIn("function buildEmptyChartSlot", script)
        self.assertIn('"data-chart-item is-blank"', script)
        self.assertIn(".data-chart-item.is-blank", styles)
        # 그래프 셋 모두 빈칸을 받는다.
        self.assertIn("buildStackedChart(group.title, series, group.axis, days, gapDate)", script)
        self.assertIn("buildLineChart(group.title, series, days, gapDate)", script)
        self.assertIn("buildLifestyleBarChart(group.title, series[0], series[0].points, days, gapDate)", script)
        # 안내는 그래프 바로 위에 붙고 조사도 받침에 맞춘다.
        self.assertIn("부터 기록되었습니다.", script)
        self.assertIn("function withTopicParticle", script)
        self.assertIn(".data-section-note", styles)

    def test_bar_chart_spreads_across_the_available_width(self) -> None:
        """막대가 몇 개든 꺾은선처럼 너비를 채워야 한다. 고정 너비면 왼쪽에 몰린다."""
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("flex: 1 1 28px; min-width: 18px", styles)
        self.assertNotIn("flex: 0 0 28px", styles)
        # 칸이 넓어져도 막대까지 굵어지지 않도록 너비를 묶고 가운데에 세운다.
        self.assertIn("max-width: 34px; margin: 0 auto", styles)

    def test_lifestyle_trend_metrics_match_backend_units(self) -> None:
        """그래프 항목의 단위 환산이 백엔드 분석과 같은지 확인한다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        # lifestyle_exercise.distance_m만 미터라 km로 나눈다.
        self.assertIn("Number(row.distance_m) / 1000", script)
        self.assertIn("Number(row.duration_sec) / 60", script)
        self.assertIn("value: (row) => row.active_distance_km", script)
        # 주 시작일은 UTC로 계산해야 toISOString이 날짜를 하루 당기지 않는다.
        self.assertIn('new Date(`${text}T00:00:00Z`)', script)
        self.assertIn("current.getUTCDay()", script)

    def test_lifestyle_report_shows_state_and_actions_only(self) -> None:
        """사용자 화면은 '현재 상태'와 '지금 신경 쓰면 좋은 것' 두 덩어리로만 읽힌다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ADMIN_FRONTEND_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

        # 검진 리포트와 섞이지 않도록 생활건강 렌더 함수 본문만 떼어 확인한다.
        start = script.index("function renderLifestyleReport(")
        body = script[start:script.index("\nfunction ", start + 1)]
        self.assertIn("report.current_state", body)
        self.assertIn("report.key_points", body)
        self.assertIn("report.actions", body)
        self.assertIn("지금 신경 쓰면 좋은 것", body)
        self.assertIn(".lifestyle-report-actions", styles)
        # 항목별 수치와 날짜를 늘어놓던 자리는 없앴다. 자리가 있으면 모델이 채운다.
        for removed in ("report.metrics", "report.patterns", "report.anomalies",
                        "overall_analysis", "report.summary", "항목별 변화", "눈에 띈 날"):
            with self.subTest(removed=removed):
                self.assertNotIn(removed, body)
        for gone in ("buildReportMetricItem", "buildReportAnomalyItem", "formatReportNumber"):
            with self.subTest(removed=gone):
                self.assertNotIn(gone, script)
        # 참고범위 한계는 화면에서도 밝힌다.
        self.assertIn("참고범위는 일반 성인 기준이며", script)

    def test_lifestyle_analysis_window_is_fixed_and_separate_from_the_graph(self) -> None:
        """AI 분석은 서비스가 정한 구간을 쓰고, 기간 버튼은 그래프에만 적용된다."""
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        # 그래프 조회는 여전히 사용자가 고른 기간을 따른다.
        self.assertIn("/me/lifestyle?window_days=${lifestyleDays}", script)
        # 안내는 추상적인 문구 대신 이 탭이 무엇을 보는지 적는다.
        self.assertIn('<span id="lifestyleAnalysisScope" class="lifestyle-block-note"></span>', markup)
        self.assertNotIn("최근 흐름 전체를 봅니다", markup)
        self.assertIn("function lifestyleAnalysisScopeText", script)
        # 지표 이름은 그래프 그룹 제목에서 가져와 한 곳에서만 관리한다.
        self.assertIn("(lifestyleTabConfigs[activeLifestyleTab] || {}).groups || []", script)
        self.assertIn("외 ${rest}개", script)
        # 구간은 서비스가 정하므로 한 번 돌려 본 뒤에만 적는다.
        self.assertIn("최근 ${state.recentDays}일과 전체 ${state.windowDays}일`", script)
        self.assertIn("아래 기간 버튼은 그래프에만 적용됩니다.", script)
        self.assertIn("최근 ${state.recentDays}일과 전체 ${state.windowDays}일", script)
        # 새 기록이 들어와 기준일이 바뀌면 옛 분석은 버린다.
        self.assertIn("cached.latestDate !== today.latestDate", script)
        self.assertIn("lifestyleReports.delete(activeLifestyleTab);", script)

    def test_verification_panel_is_shared_and_swaps_labels_per_tab(self) -> None:
        """검증 패널은 같은 뼈대를 쓰고 단계·지표 이름만 탭에 맞춰 바뀐다."""
        markup = (ADMIN_FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        # 뼈대는 하나다. 검진 전용 id 대신 자리 표시 속성을 쓴다.
        for step in ("latest", "history", "analysis", "result"):
            self.assertIn(f'data-dashboard-step-label="{step}"', markup)
            self.assertIn(f'data-dashboard-step-status="{step}"', markup)
        for index in range(4):
            self.assertIn(f'data-dashboard-metric-label="{index}"', markup)
            self.assertIn(f'data-dashboard-metric-value="{index}"', markup)
        self.assertNotIn('id="dashboardCheckupCount"', markup)
        self.assertNotIn("elements.dashboardCheckupCount", script)

        # 탭별 라벨과 교체 시점.
        self.assertIn('title: "검진 분석 검증"', script)
        self.assertIn('title: "생활건강 분석 검증"', script)
        self.assertIn('metrics: ["분석 항목", "범위 이탈", "이상 지점", "관리 필요"]', script)
        self.assertIn("applyDashboardPreset(tab);", script)

    def test_lifestyle_report_logs_into_verification_panel(self) -> None:
        """생활건강 AI 요약분석도 검진과 같은 형식으로 단계와 지표를 남긴다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function renderLifestyleDashboard", script)
        self.assertIn('finishDashboardRun("lifestyle"', script)
        self.assertIn('failDashboardRun("lifestyle", message);', script)
        # 검진과 같은 소요 시간 표기를 쓴다.
        self.assertIn("formatElapsed(timings.window_seconds)", script)
        self.assertIn("formatElapsed(timings.ai_seconds)", script)
        # 지표는 서비스가 내려준 계산 결과에서 센다. 전체 구간 신호를 기준으로 한다.
        self.assertIn("(metric.full || {}).out_of_range_days > 0", script)
        self.assertIn("(metric.anomalies || []).length", script)
        # 탭을 오갔다 돌아와도 그 탭의 로그가 남아야 하므로 초기화는 기록하지 않는다.
        self.assertIn('setDashboardStep(step, "대기 중", "pending", false)', script)

    def test_verification_panel_keeps_the_full_statistics(self) -> None:
        """사용자 화면에서 뺀 통계는 개발자 검증 패널에 그대로 남아야 한다."""
        script = (ADMIN_FRONTEND_ROOT / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn('["항목별 계산 근거와 코드 판정", verification.analysis_input || {}]', script)
        self.assertIn('["이상 지점으로 잡힌 날"', script)
        self.assertIn('["함께 움직인 항목", (verification.analysis_input || {}).co_movements || []]', script)
        # 어떤 판 프롬프트로 만든 결과인지 로그에 남긴다.
        self.assertIn("프롬프트 v${payload.prompt_version", script)
        self.assertIn("prompt_version: verification.prompt_version", script)
        # 조회 상한에 걸려 오래된 기록이 잘렸다면 그 사실도 남긴다.
        self.assertIn("payload.data_truncated", script)

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


    @patch("app.admin_frontend.requests.request")
    def test_lifestyle_report_proxy_uses_main_api(self, request: Mock) -> None:
        """생활건강 탭별 AI 분석 요청과 조회 조건을 메인 API로 중계한다."""
        backend_response = Mock(
            status_code=200,
            content=b'{"success":true,"domain":"bio","window_days":180}',
            headers={"content-type": "application/json"},
            raw=Mock(headers=Mock(getlist=Mock(return_value=[]))),
        )
        request.return_value = backend_response

        response = TestClient(app).post("/me/lifestyle/report", params={"domain": "bio"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["domain"], "bio")
        self.assertEqual(
            request.call_args.args[:2],
            ("POST", "http://localhost:8000/me/lifestyle/report?domain=bio"),
        )


if __name__ == "__main__":
    unittest.main()
