"""생활건강 탭별 AI 분석의 수치 계산 테스트.

설명 문장은 Gemini가 만들지만 당일 값과 구간 통계는 서비스가 직접 계산한다.
그 계산이 화면 표기와 같은 단위로 나오는지 확인한다.

작성자: 고수연
"""

import unittest

from app.services.lifestyle_report import LifestyleReportService


LIFESTYLE_WINDOW = {
    "window_days": 30,
    "bio": {
        "since": "2026-08-28",
        "until": "2026-09-01",
        "rows": [
            {"measured_at": "2026-09-01T07:00:00", "bio_type": "weight", "value": 70.4, "detail_data": {}},
            {"measured_at": "2026-08-28T07:00:00", "bio_type": "weight", "value": 71.0, "detail_data": {}},
            {"measured_at": "2026-09-01T07:20:00", "bio_type": "bmi", "value": 23.4, "detail_data": {}},
            {
                "measured_at": "2026-09-01T07:10:00",
                "bio_type": "blood_pressure",
                "value": 121,
                "detail_data": {"systolic": 121, "diastolic": 79, "pulse": 70},
            },
            {
                "measured_at": "2026-09-01T08:00:00",
                "bio_type": "blood_glucose",
                "value": 95,
                "detail_data": {"fasting": True},
            },
            {
                "measured_at": "2026-08-30T13:00:00",
                "bio_type": "blood_glucose",
                "value": 132,
                "detail_data": {"fasting": False},
            },
        ],
    },
    "sleep": {
        "since": "2026-09-01",
        "until": "2026-09-01",
        "rows": [
            {
                "measured_at": "2026-09-01T23:00:00",
                "bio_type": "sleep",
                "value": 7.2,
                "detail_data": {"sleep_score": 82, "deep_sleep_min": 70, "awake_min": 12},
            }
        ],
    },
    "activity": {
        "since": "2026-09-01",
        "until": "2026-09-01",
        "rows": [
            {
                "record_date": "2026-09-01",
                "steps": 8200,
                "floors_climbed": 7,
                "active_time": 64,
                "active_distance_km": 5.9,
                "active_calories": 320,
            }
        ],
    },
    "exercise": {
        "since": "2026-09-01",
        "until": "2026-09-01",
        "rows": [
            {
                "record_date": "2026-09-01",
                "exercise_type": "running",
                "duration_sec": 1800,
                "distance_m": 5000,
                "calories": 310,
            }
        ],
    },
    "food": {
        "since": "2026-09-01",
        "until": "2026-09-01",
        "rows": [
            {"consumed_at": "2026-09-01T08:00:00", "calories": 420, "carbohydrate": 50,
             "protein": 15, "total_fat": 12, "sodium": 520, "sugar": 9},
            {"consumed_at": "2026-09-01T12:30:00", "calories": 680, "carbohydrate": 95,
             "protein": 22, "total_fat": 18, "sodium": 980, "sugar": 11},
        ],
    },
    "water": {
        "since": "2026-09-01",
        "until": "2026-09-01",
        "rows": [
            {"consumed_at": "2026-09-01T09:00:00", "water_amount": 500},
            {"consumed_at": "2026-09-01T15:00:00", "water_amount": 350},
        ],
    },
}


def _metric(analysis: dict, name: str) -> dict:
    return next(item for item in analysis["metrics"] if item["metric"] == name)


class LifestyleAnalysisTest(unittest.TestCase):
    """탭마다 당일 값과 구간 통계를 화면과 같은 단위로 계산한다."""

    def test_bio_tab_splits_blood_pressure_and_glucose_items(self) -> None:
        analysis = LifestyleReportService.build_analysis("bio", LIFESTYLE_WINDOW, 30)

        self.assertEqual(analysis["latest_date"], "2026-09-01")
        self.assertEqual(_metric(analysis, "수축기 혈압")["latest"], 121)
        self.assertEqual(_metric(analysis, "이완기 혈압")["latest"], 79)
        self.assertEqual(_metric(analysis, "공복 혈당")["latest"], 95)
        # 체중은 이틀치라 당일 값과 구간 평균이 갈린다.
        weight = _metric(analysis, "체중")
        self.assertEqual(weight["latest"], 70.4)
        self.assertEqual(weight["average"], 70.7)
        self.assertEqual(weight["days"], 2)

    def test_metric_without_record_on_latest_date_has_no_latest_value(self) -> None:
        """항목마다 마지막 기록일이 달라도 당일 값은 당일 것만 채운다."""
        analysis = LifestyleReportService.build_analysis("bio", LIFESTYLE_WINDOW, 30)

        glucose_after = _metric(analysis, "식후 혈당")
        self.assertIsNone(glucose_after["latest"])
        self.assertEqual(glucose_after["latest_date"], "2026-08-30")
        self.assertEqual(glucose_after["average"], 132)

    def test_activity_tab_converts_exercise_units(self) -> None:
        """운동 기록은 초를 분으로, 미터를 km로 바꿔 화면 표기와 맞춘다."""
        analysis = LifestyleReportService.build_analysis("activity", LIFESTYLE_WINDOW, 30)

        self.assertEqual(_metric(analysis, "운동시간")["latest"], 30)
        self.assertEqual(_metric(analysis, "운동거리")["latest"], 5)
        # lifestyle_activity.distance_m은 km로 적재돼 환산하지 않는다.
        self.assertEqual(_metric(analysis, "이동거리")["latest"], 5.9)
        self.assertEqual(_metric(analysis, "걸음 수")["latest"], 8200)

    def test_nutrition_tab_sums_same_day_records(self) -> None:
        """하루에 여러 번 먹은 기록은 당일 합계로 묶는다."""
        analysis = LifestyleReportService.build_analysis("nutrition", LIFESTYLE_WINDOW, 30)

        self.assertEqual(_metric(analysis, "섭취칼로리")["latest"], 1100)
        self.assertEqual(_metric(analysis, "나트륨")["latest"], 1500)
        self.assertEqual(_metric(analysis, "수분 섭취")["latest"], 850)

    def test_sleep_tab_reads_detail_data_items(self) -> None:
        analysis = LifestyleReportService.build_analysis("sleep", LIFESTYLE_WINDOW, 30)

        self.assertEqual(_metric(analysis, "수면시간")["latest"], 7.2)
        self.assertEqual(_metric(analysis, "수면점수")["latest"], 82)
        self.assertEqual(_metric(analysis, "깊은수면")["latest"], 70)
        self.assertEqual(_metric(analysis, "깬 시간")["latest"], 12)

    def test_empty_window_produces_no_metrics(self) -> None:
        """기록이 없으면 항목을 만들지 않아 라우터가 400으로 막을 수 있다."""
        analysis = LifestyleReportService.build_analysis("bio", {}, 30)

        self.assertEqual(analysis["metrics"], [])
        self.assertEqual(analysis["latest_date"], "")


if __name__ == "__main__":
    unittest.main()
