"""합성 데이터로 내부 건강 계약과 정규화를 검증한다. 작성자: 김진우."""
import os
import unittest
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from app.internal import app
from app.health_analysis import AnalysisRequest, checkup_service, normalize_window
from app.core.state import state
from app.services import checkup_report


class HealthAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "x" * 40})
        self.env.start()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer " + "x" * 40}
        self.body = {"contractVersion": "1.0", "category": "activity", "analysisDate": "2026-09-10",
                     "cutoff": "2026-09-09T15:00:00Z", "records": {}}

    def tearDown(self):
        checkup_service.cache_clear()
        state.pop("vector_search", None)
        self.env.stop()

    def test_checkup_service_uses_the_shared_vector_search(self):
        shared = object()
        state["vector_search"] = shared
        checkup_service.cache_clear()

        with patch.object(checkup_report, "CheckupReportService") as service:
            checkup_service()

        service.assert_called_once_with(max_retries=0, vector_search=shared)

    def test_requires_internal_auth(self):
        self.assertEqual(401, self.client.post("/internal/health/analyses", json=self.body).status_code)

    def test_passes_once_and_does_not_expose_trace(self):
        with patch("app.health_analysis.generate", new_callable=AsyncMock, return_value={"status": "generated", "report": {"headline": "합성"}}) as work:
            result = self.client.post("/internal/health/analyses", json=self.body, headers=self.headers)
        self.assertEqual(200, result.status_code)
        work.assert_awaited_once()
        self.assertNotIn("verification", result.json())

    def test_errors_do_not_echo_health_or_provider_input(self):
        with patch("app.health_analysis.generate", new_callable=AsyncMock, side_effect=ValueError("합성 비공개 값")) as work:
            result = self.client.post("/internal/health/analyses", json=self.body, headers=self.headers)
        self.assertEqual(503, result.status_code)
        self.assertNotIn("합성 비공개 값", result.text)
        work.assert_awaited_once()

    def test_normalizes_meters_and_excludes_next_day(self):
        body = {**self.body, "records": {"activity": [
            {"record_date": "2026-09-09", "distance_m": 2500, "steps": 3000},
            {"record_date": "2026-09-10", "distance_m": 5000}]}}
        rows = normalize_window(AnalysisRequest(**body))["activity"]["rows"]
        self.assertEqual(1, len(rows))
        self.assertEqual(2.5, rows[0]["active_distance_km"])
        self.assertIsNone(rows[0]["active_calories"])

    def test_normalizes_body_composition_without_dropping_weight(self):
        body = {**self.body, "category": "bio", "records": {"bio": [
            {"measured_at": "2026-09-08T23:00:00Z", "bio_type": "body_composition", "weight_kg": 60, "bmi_value": 22}]}}
        rows = normalize_window(AnalysisRequest(**body))["bio"]["rows"]
        self.assertEqual(["weight", "bmi"], [r["bio_type"] for r in rows])
        self.assertEqual("2026-09-09", rows[0]["measured_at"])

    def test_score_category_returns_a_score_not_a_report(self):
        """점수는 모델을 부르지 않는 순수 계산이라 report가 아니라 score로 돌려준다.

        기록이 모자라면 status가 data_insufficient이고, 왜인지는 reasons에 남는다.
        작성자: 고수연.
        """
        body = {**self.body, "category": "score", "records": {}}
        result = self.client.post("/internal/health/analyses", json=body, headers=self.headers)

        self.assertEqual(200, result.status_code)
        payload = result.json()
        self.assertEqual("data_insufficient", payload["status"])
        self.assertIsNone(payload["score"]["total_score"])
        self.assertIn("sleep_insufficient", payload["score"]["reasons"])
        self.assertNotIn("report", payload)

    def test_score_reads_through_the_day_before_the_analysis_date(self):
        """normalize_window가 분석일 당일을 빼므로 창을 전날에 맞춘다. 날짜는 분석일이다."""
        sleep = []
        for offset in range(1, 15):
            day = date(2026, 9, 10) - timedelta(days=offset)
            sleep.append({"start_at": f"{day.isoformat()}T23:00:00+09:00",
                          "end_at": f"{(day + timedelta(days=1)).isoformat()}T07:00:00+09:00",
                          "total_sleep_minutes": 450})
        activity = [{"record_date": (date(2026, 9, 10) - timedelta(days=offset)).isoformat(),
                     "steps": 9000} for offset in range(1, 15)]
        bio = [{"measured_at": "2026-09-05T00:00:00Z", "bio_type": "bmi", "bmi_value": 22}]
        body = {**self.body, "category": "score", "age": 35,
                "records": {"sleep": sleep, "activity": activity, "bio": bio}}

        payload = self.client.post("/internal/health/analyses", json=body,
                                   headers=self.headers).json()
        self.assertEqual("generated", payload["status"])
        self.assertEqual("2026-09-10", payload["score"]["score_date"])
        self.assertEqual(100, payload["score"]["total_score"])

    def test_score_days_returns_one_point_per_day_ending_on_the_analysis_date(self):
        """서버가 그래프용 행을 한 번에 채울 수 있어야 한다. 작성자: 고수연.

        계열의 마지막 날은 분석일이고, score는 그 마지막 날과 같은 값이다.
        """
        body = {**self.body, "category": "score", "records": {}, "scoreDays": 5}
        payload = self.client.post("/internal/health/analyses", json=body,
                                   headers=self.headers).json()

        self.assertEqual(["2026-09-06", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"],
                         [point["score_date"] for point in payload["points"]])
        self.assertEqual(payload["points"][-1], payload["score"])

    def test_score_without_score_days_still_returns_a_single_day(self):
        """기본값 1이면 예전 계약 그대로다. 서버가 필드를 안 보내도 깨지지 않는다."""
        body = {**self.body, "category": "score", "records": {}}
        payload = self.client.post("/internal/health/analyses", json=body,
                                   headers=self.headers).json()

        self.assertEqual(1, len(payload["points"]))
        self.assertEqual("2026-09-10", payload["score"]["score_date"])

    def test_reads_the_stored_sex_spelling(self):
        """저장소는 'Male'·'Female'로 적는다. 소문자만 받으면 성별이 통째로 빠진다.

        모르는 값은 거절하지 않고 비운다. 생활건강의 normalize_sex와 같은 규칙이다.
        작성자: 고수연.
        """
        for given, expected in (("Female", "female"), ("male", "male"),
                                ("여성", None), ("", None), (None, None)):
            self.assertEqual(expected, AnalysisRequest(**{**self.body, "sex": given}).sex)

    def test_rejects_unknown_fields_and_naive_cutoff(self):
        for delta in ({"userId": "다른 사용자"}, {"cutoff": "2026-09-10T00:00:00"},
                      {"cutoff": "2026-09-10T01:00:00+09:00"}):
            result = self.client.post("/internal/health/analyses", json={**self.body, **delta}, headers=self.headers)
            self.assertEqual(422, result.status_code)


if __name__ == "__main__":
    unittest.main()
