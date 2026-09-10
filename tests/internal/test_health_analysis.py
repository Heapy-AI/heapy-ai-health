"""합성 데이터로 내부 건강 계약과 정규화를 검증한다. 작성자: 김진우."""
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from app.internal import app
from app.health_analysis import AnalysisRequest, normalize_window


class HealthAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "x" * 40})
        self.env.start()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer " + "x" * 40}
        self.body = {"contractVersion": "1.0", "category": "activity", "analysisDate": "2026-09-10",
                     "cutoff": "2026-09-09T15:00:00Z", "records": {}}

    def tearDown(self):
        self.env.stop()

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

    def test_rejects_unknown_fields_and_naive_cutoff(self):
        for delta in ({"userId": "다른 사용자"}, {"cutoff": "2026-09-10T00:00:00"},
                      {"cutoff": "2026-09-10T01:00:00+09:00"}):
            result = self.client.post("/internal/health/analyses", json={**self.body, **delta}, headers=self.headers)
            self.assertEqual(422, result.status_code)


if __name__ == "__main__":
    unittest.main()
