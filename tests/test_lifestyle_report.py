"""생활건강 탭별 AI 분석의 계산·신호·프롬프트 테스트.

설명 문장은 Gemini가 만들지만 수치 계산과 좋고 나쁨 판정은 서비스가 직접 한다.
계산이 화면 표기와 같은 단위로 나오는지, 통계가 사람 말로 잘 옮겨지는지,
그리고 원시 통계가 프롬프트로 새지 않는지를 확인한다.

작성자: 고수연
"""

import unittest
from datetime import date, timedelta

from app.services.lifestyle_report import (
    PROMPT_VERSION,
    _clock_minutes,
    STATUS_CAUTION,
    STATUS_GOOD,
    STATUS_MANAGE,
    STATUS_UNKNOWN,
    LifestyleReportService,
    _clock_stats,
    _clock_text,
    _prompt_view,
)
from app.services.prompts import lifestyle_report_v1 as prompt_v1
from app.services.prompts import lifestyle_report_v2 as prompt_v2
from app.services.prompts import lifestyle_report_v3 as prompt_v3


def _bio_days(bio_type: str, values: dict[str, float], detail_key: str = "") -> list[dict]:
    """날짜별 값 하나짜리 생체 기록을 만든다."""
    rows = []
    for date, value in values.items():
        detail = {detail_key: value} if detail_key else {}
        rows.append({"measured_at": f"{date}T07:00:00", "bio_type": bio_type,
                     "value": value, "detail_data": detail})
    return rows


def _exercise_window(days: int = 28, plan: tuple[tuple[int, str, int], ...] = (
    (2, "walking", 45), (5, "walking", 40), (9, "running", 30),
    (12, "indoor_cycling", 50), (16, "walking", 45), (23, "running", 35),
)) -> dict:
    """활동은 매일, 운동은 드문드문 기록된 구간. 빈도를 재는 쪽을 확인하는 데 쓴다."""
    end = date(2026, 9, 1)
    return {
        "window_days": days,
        "activity": {"rows": [
            {"record_date": str(end - timedelta(days=back)), "steps": 8000,
             "active_calories": 320}
            for back in range(days)
        ]},
        "exercise": {"rows": [
            {"record_date": f"{end - timedelta(days=back)}T18:00:00",
             "exercise_type": kind, "duration_sec": minutes * 60,
             "distance_m": 4000, "calories": minutes * 6}
            for back, kind, minutes in plan
        ]},
    }


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
                "detail_data": {"sleep_score": 82, "deep_sleep_minutes": 70,
                                "light_sleep_minutes": 240, "rem_sleep_minutes": 95,
                                "awake_minutes": 12},
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
            {"consumed_at": "2026-09-01T08:00:00", "meal_type": "breakfast",
             "calories": 420, "carbohydrate": 50, "protein": 15, "total_fat": 12,
             "sodium": 520, "sugar": 9, "saturated_fat": 4, "dietary_fiber": 3,
             "potassium": 480, "calcium": 190},
            {"consumed_at": "2026-09-01T12:30:00", "meal_type": "lunch",
             "calories": 680, "carbohydrate": 95, "protein": 22, "total_fat": 18,
             "sodium": 980, "sugar": 11, "saturated_fat": 6, "dietary_fiber": 5,
             "potassium": 720, "calcium": 210},
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
        analysis = LifestyleReportService.build_analysis("bio", LIFESTYLE_WINDOW)

        self.assertEqual(analysis["latest_date"], "2026-09-01")
        self.assertEqual(_metric(analysis, "수축기 혈압")["latest"], 121)
        self.assertEqual(_metric(analysis, "이완기 혈압")["latest"], 79)
        self.assertEqual(_metric(analysis, "공복 혈당")["latest"], 95)
        # 체중은 이틀치라 당일 값과 구간 평균이 갈린다.
        weight = _metric(analysis, "체중")
        self.assertEqual(weight["latest"], 70.4)
        self.assertEqual(weight["full"]["average"], 70.7)
        self.assertEqual(weight["full"]["days"], 2)

    def test_metric_without_record_on_latest_date_has_no_latest_value(self) -> None:
        """항목마다 마지막 기록일이 달라도 당일 값은 당일 것만 채운다."""
        analysis = LifestyleReportService.build_analysis("bio", LIFESTYLE_WINDOW)

        glucose_after = _metric(analysis, "식후 혈당")
        self.assertIsNone(glucose_after["latest"])
        self.assertEqual(glucose_after["latest_date"], "2026-08-30")
        self.assertEqual(glucose_after["full"]["average"], 132)

    def test_activity_tab_converts_exercise_units(self) -> None:
        """운동 기록은 초를 분으로, 미터를 km로 바꿔 화면 표기와 맞춘다."""
        analysis = LifestyleReportService.build_analysis("activity", LIFESTYLE_WINDOW)

        self.assertEqual(_metric(analysis, "운동시간")["latest"], 30)
        self.assertEqual(_metric(analysis, "운동거리")["latest"], 5)
        self.assertEqual(_metric(analysis, "걸음 수")["latest"], 8200)

    def test_exercise_is_measured_by_how_often_not_by_daily_minutes(self) -> None:
        """운동시간 계열에는 운동한 날만 점이 있다. 하루 기준 참고범위는 뜻이 어긋난다.

        한 번에 45분씩 해도 한 달에 두 번이면 권고에 한참 못 미치는데, 하루 21분
        기준으로 재면 '늘 양호'로 나온다. 그래서 참고범위를 떼고 빈도로 따로 잰다.
        """
        analysis = LifestyleReportService.build_analysis("activity", _exercise_window())

        self.assertEqual(_metric(analysis, "운동시간")["reference"], "")
        habit = analysis["exercise_habit"]
        self.assertIsNotNone(habit)
        # 사람이 헤아리는 단위로 넘긴다. 원시 통계는 넘기지 않는다.
        self.assertIn("한 달에", habit["frequency"])
        self.assertIn("한 번에", habit["session"])
        self.assertIn("150분", habit["guideline"])

    def test_exercise_shortfall_is_counted_in_sessions_not_minutes(self) -> None:
        """'운동을 늘리세요'는 조언이 아니다. 몇 번 더인지를 코드가 센다."""
        # 28일에 6번, 한 번에 40분쯤. 주당 약 60분이라 권고(150분)에 못 미친다.
        habit = LifestyleReportService.build_analysis(
            "activity", _exercise_window())["exercise_habit"]

        self.assertIn("못 미친다", habit["guideline"])
        self.assertIn("번쯤 더 하면 닿는다", habit["shortfall"])

        # 넉넉히 하는 사람에게는 더 하라고 하지 않는다.
        enough = LifestyleReportService.build_analysis("activity", _exercise_window(
            plan=tuple((back, "running", 60) for back in range(0, 28, 2)),
        ))["exercise_habit"]
        self.assertIn("채우고 있다", enough["guideline"])
        self.assertNotIn("shortfall", enough)

    def test_exercise_change_is_measured_per_calendar_week(self) -> None:
        """늘고 주는 것은 달력 날짜로 나눠 잰다. 운동한 날만 이어 붙이면 빈도가 안 보인다."""
        # 앞 두 달은 주 3번, 최근 한 달은 주 1번. 한 번의 길이는 40분으로 똑같다.
        plan = tuple((back, "walking", 40) for back in range(30, 90, 2))
        plan += tuple((back, "walking", 40) for back in range(0, 30, 7))
        habit = LifestyleReportService.build_analysis(
            "activity", _exercise_window(days=90, plan=plan))["exercise_habit"]

        self.assertIn("줄었다", habit["change"])
        # 한 번에 하는 길이는 그대로이니 길이를 두고 줄었다고 하면 안 된다.
        self.assertIn("40분", habit["session"])

    def test_exercise_change_says_so_when_nothing_changed(self) -> None:
        """안 변한 것도 알려야 한다. 비워 두면 모델이 다른 신호에서 변화를 지어낸다."""
        plan = tuple((back, "walking", 40) for back in range(0, 90, 3))
        habit = LifestyleReportService.build_analysis(
            "activity", _exercise_window(days=90, plan=plan))["exercise_habit"]

        self.assertIn("예전과 비슷하다", habit["change"])

    def test_exercise_weekend_habit_points_at_the_empty_side(self) -> None:
        """주말을 이미 채운 사람에게 주말에 하라고 하면 쓸모없는 조언이 된다."""
        from datetime import date as _date, timedelta as _delta

        end = _date(2026, 9, 1)
        weekends = [back for back in range(90)
                    if (end - _delta(days=back)).isoweekday() >= 6]
        habit = LifestyleReportService.build_analysis("activity", _exercise_window(
            days=90, plan=tuple((back, "walking", 40) for back in weekends),
        ))["exercise_habit"]

        self.assertIn("주말에 몰려 있다", habit["weekend_habit"])

    def test_macro_ratios_are_judged_by_energy_not_by_weight(self) -> None:
        """탄수화물 300g이 많은지는 얼마나 먹었느냐에 딸려 다녀 그 자체로 말할 수 없다."""
        analysis = LifestyleReportService.build_analysis("nutrition", LIFESTYLE_WINDOW)
        labels = [metric["metric"] for metric in analysis["metrics"]]

        for name in ("탄수화물 비중", "단백질 비중", "지방 비중"):
            with self.subTest(metric=name):
                self.assertIn(name, labels)
        # 2025 한국인 영양소 섭취기준 에너지적정비율. 2020년 값(55~65 · 7~20)에서 바뀌었다.
        self.assertEqual(_metric(analysis, "탄수화물 비중")["reference"], "50~65 %")
        self.assertEqual(_metric(analysis, "단백질 비중")["reference"], "10~20 %")
        self.assertEqual(_metric(analysis, "지방 비중")["reference"], "15~30 %")
        # 포화지방산은 19세 이상 총에너지의 7% 미만.
        self.assertEqual(_metric(analysis, "포화지방 비중")["reference"], "7 % 미만")

        # 지방만 9kcal/g이라 무게 비율과 열량 비율이 갈린다. 열량 쪽을 쓴다.
        window = {"food": {"rows": [
            {"consumed_at": f"2026-09-0{day}T12:00:00", "meal_type": "lunch",
             "calories": 1000, "carbohydrate": 100, "protein": 50, "total_fat": 50}
            for day in range(1, 6)
        ]}}
        ratios = LifestyleReportService.build_analysis("nutrition", window)
        # 열량으로는 400 / 200 / 450 → 38 / 19 / 43 %. 무게로는 50 / 25 / 25 %.
        self.assertEqual(round(_metric(ratios, "지방 비중")["latest"]), 43)
        self.assertEqual(round(_metric(ratios, "탄수화물 비중")["latest"]), 38)

    def test_new_nutrients_follow_the_2025_korean_reference(self) -> None:
        """2025 한국인 영양소 섭취기준. 기록에 있는데도 안 보던 값들을 살렸다."""
        analysis = LifestyleReportService.build_analysis("nutrition", LIFESTYLE_WINDOW)

        # 식이섬유 충분섭취량은 남자 30g, 여자 20~25g. 성별을 모르므로 낮은 쪽에 문턱을 둔다.
        self.assertEqual(_metric(analysis, "식이섬유")["reference"], "25 g 이상")
        # 칼륨 충분섭취량 3,500mg (남녀 같음).
        self.assertEqual(_metric(analysis, "칼륨")["reference"], "3500 mg 이상")
        # 칼슘 권장섭취량은 남자 800mg, 여자 650~750mg.
        self.assertEqual(_metric(analysis, "칼슘")["reference"], "700 mg 이상")

    def test_saturated_fat_is_not_counted_twice_in_the_denominator(self) -> None:
        """포화지방은 지방 안에 이미 들어 있다. 분모에 더하면 같은 열량을 두 번 센다."""
        window = {"food": {"rows": [
            {"consumed_at": f"2026-09-0{day}T12:00:00", "calories": 1000,
             "carbohydrate": 100, "protein": 50, "total_fat": 50, "saturated_fat": 20}
            for day in range(1, 6)
        ]}}
        analysis = LifestyleReportService.build_analysis("nutrition", window)

        # 총열량 400 + 200 + 450 = 1,050kcal. 포화지방 20g = 180kcal → 17%.
        self.assertEqual(round(_metric(analysis, "포화지방 비중")["latest"]), 17)
        # 지방 전체는 43%. 포화는 그 안에 들어 있으므로 더 작아야 한다.
        self.assertLess(_metric(analysis, "포화지방 비중")["latest"],
                        _metric(analysis, "지방 비중")["latest"])

    def test_prompt_lists_the_urgent_metrics_first(self) -> None:
        """항목이 열넷으로 늘었다. 넉 줄 안에 담기려면 급한 것이 앞에 와야 한다."""
        from app.services.lifestyle_report import _prompt_view

        view = _prompt_view(LifestyleReportService.build_analysis("nutrition", LIFESTYLE_WINDOW))
        levels = [(m.get("recent") or m.get("full") or {}).get("level", "")
                  for m in view["metrics"]]
        rank = {"기준을 크게 벗어남": 0, "기준을 조금 벗어남": 1,
                "기준 범위 안": 2, "기준 없음": 3}

        self.assertEqual([rank[level] for level in levels],
                         sorted(rank[level] for level in levels))

    def test_macro_pairs_are_arithmetic_not_habit(self) -> None:
        """비중 셋은 합이 100이라 하나가 오르면 다른 하나는 반드시 내려간다."""
        from app.services.lifestyle_report import _TRIVIAL_CO_MOVEMENTS

        for left, right in (
            ("탄수화물 비중", "지방 비중"),
            ("탄수화물", "지방 비중"),
            ("섭취칼로리", "탄수화물"),
            ("탄수화물", "당"),
        ):
            with self.subTest(pair=(left, right)):
                self.assertIn(frozenset({left, right}), _TRIVIAL_CO_MOVEMENTS)

    def test_meal_pattern_says_where_the_sodium_comes_from(self) -> None:
        """'나트륨을 줄이세요'는 어디를 손댈지 알려 주지 않는다."""
        window = {"food": {"rows": [
            row
            for day in range(1, 8)
            for row in (
                {"consumed_at": f"2026-09-0{day}T08:00:00", "meal_type": "breakfast",
                 "calories": 200, "sodium": 100},
                {"consumed_at": f"2026-09-0{day}T12:00:00", "meal_type": "lunch",
                 "calories": 800, "sodium": 900},
                {"consumed_at": f"2026-09-0{day}T19:00:00", "meal_type": "dinner",
                 "calories": 1000, "sodium": 1600},
            )
        ]}}
        meals = LifestyleReportService.build_analysis("nutrition", window)["meal_pattern"]

        self.assertIn("저녁", meals["sodium_source"])
        self.assertEqual(meals["heaviest"], "저녁이 가장 크다")
        # 하루 열량의 10%뿐인 아침은 짚어 주되 거른 것으로 단정하지 않는다.
        self.assertIn("아침", meals["light_meal"])

    def test_meal_pattern_clears_snacks_when_they_add_nothing(self) -> None:
        """간식을 먹은 날에도 하루 총량이 그대로면 간식은 범인이 아니다."""
        rows = []
        for day in range(1, 11):
            date = f"2026-09-{day:02d}"
            snack = day % 2 == 0
            rows.append({"consumed_at": f"{date}T12:00:00", "meal_type": "lunch",
                         "calories": 900 if snack else 1000, "sodium": 500})
            rows.append({"consumed_at": f"{date}T19:00:00", "meal_type": "dinner",
                         "calories": 900, "sodium": 500})
            if snack:
                rows.append({"consumed_at": f"{date}T16:00:00", "meal_type": "snack",
                             "calories": 100, "sodium": 50})
        meals = LifestyleReportService.build_analysis(
            "nutrition", {"food": {"rows": rows}})["meal_pattern"]

        self.assertEqual(meals["snack_effect"],
                         "간식을 먹은 날과 안 먹은 날의 하루 열량이 비슷하다")

    def test_meal_pattern_only_exists_on_the_nutrition_tab(self) -> None:
        for domain in ("bio", "activity", "sleep"):
            with self.subTest(domain=domain):
                analysis = LifestyleReportService.build_analysis(domain, LIFESTYLE_WINDOW)
                self.assertIsNone(analysis["meal_pattern"])

    def test_exercise_habit_only_exists_on_the_activity_tab(self) -> None:
        """탭마다 보는 것이 다르다. 다른 탭에 자리를 만들면 모델이 채운다."""
        for domain in ("bio", "nutrition", "sleep"):
            with self.subTest(domain=domain):
                analysis = LifestyleReportService.build_analysis(domain, LIFESTYLE_WINDOW)
                self.assertIsNone(analysis["exercise_habit"])

    def test_activity_analysis_drops_what_merely_tracks_steps(self) -> None:
        """계단·활동시간·이동거리는 걸음 수를 따라 움직여 새 이야기가 되지 않는다.

        화면에서도 뺐으므로 분석에 남겨 두면 사용자가 확인할 수 없는 항목을 두고 말하게 된다.
        """
        analysis = LifestyleReportService.build_analysis("activity", LIFESTYLE_WINDOW)
        labels = [metric["metric"] for metric in analysis["metrics"]]

        for gone in ("계단", "활동시간", "이동거리"):
            with self.subTest(metric=gone):
                self.assertNotIn(gone, labels)
        self.assertEqual(labels, ["걸음 수", "활동칼로리", "운동시간", "운동거리", "운동칼로리"])

    def test_nutrition_tab_sums_same_day_records(self) -> None:
        """하루에 여러 번 먹은 기록은 당일 합계로 묶는다."""
        analysis = LifestyleReportService.build_analysis("nutrition", LIFESTYLE_WINDOW)

        self.assertEqual(_metric(analysis, "섭취칼로리")["latest"], 1100)
        self.assertEqual(_metric(analysis, "나트륨")["latest"], 1500)
        self.assertEqual(_metric(analysis, "수분 섭취")["latest"], 850)

    def test_sleep_tab_reads_detail_data_items(self) -> None:
        """수면 단계는 저장소가 내려주는 *_minutes 키로 읽어야 한다.

        deep_sleep_min처럼 짧은 이름으로 읽으면 값이 조용히 비어 화면에서 사라진다.
        """
        analysis = LifestyleReportService.build_analysis("sleep", LIFESTYLE_WINDOW)

        self.assertEqual(_metric(analysis, "수면시간")["latest"], 7.2)
        self.assertEqual(_metric(analysis, "수면점수")["latest"], 82)
        self.assertEqual(_metric(analysis, "깊은수면")["latest"], 70)
        self.assertEqual(_metric(analysis, "얕은수면")["latest"], 240)
        self.assertEqual(_metric(analysis, "REM수면")["latest"], 95)
        self.assertEqual(_metric(analysis, "뒤척임")["latest"], 12)

    def test_sleep_tab_covers_every_fetched_column(self) -> None:
        """조회해 놓고 화면에 안 쓰는 수면 컬럼이 없어야 한다."""
        analysis = LifestyleReportService.build_analysis("sleep", LIFESTYLE_WINDOW)

        self.assertEqual(
            [item["metric"] for item in analysis["metrics"]],
            ["수면시간", "수면점수", "깊은수면", "얕은수면", "REM수면", "뒤척임",
             "깊은수면 비중", "REM수면 비중"],
        )

    def test_sleep_metric_keys_match_the_storage_contract(self) -> None:
        """저장소 정규화가 만드는 키와 분석이 읽는 키가 같은지 직접 맞춰 본다."""
        from app.services.supabase_personal_data import SupabasePersonalDataService

        normalized = SupabasePersonalDataService._normalize_domain("sleep", {
            "since": "", "until": "", "truncated": False,
            "rows": [{
                "measured_at": "2026-09-01T23:00:00", "total_sleep_minutes": 432,
                "awake_minutes": 12, "deep_sleep_minutes": 70,
                "light_sleep_minutes": 240, "rem_sleep_minutes": 95, "sleep_score": 82,
            }],
        })
        analysis = LifestyleReportService.build_analysis("sleep", {"sleep": normalized})

        # 키가 어긋나면 해당 항목이 통째로 빠지므로 개수로 잡힌다.
        self.assertEqual(len(analysis["metrics"]), 8)
        self.assertEqual(_metric(analysis, "수면시간")["latest"], 7.2)
        self.assertEqual(_metric(analysis, "얕은수면")["latest"], 240)

    def test_empty_window_produces_no_metrics(self) -> None:
        """기록이 없으면 항목을 만들지 않아 라우터가 400으로 막을 수 있다."""
        analysis = LifestyleReportService.build_analysis("bio", {})

        self.assertEqual(analysis["metrics"], [])
        self.assertEqual(analysis["latest_date"], "")


class LifestyleStatusTest(unittest.TestCase):
    """참고범위 판정은 코드가 계산한다. AI는 이 값을 바꾸지 못한다."""

    def _bio_analysis(self, rows: list[dict]) -> dict:
        return LifestyleReportService.build_analysis("bio", {"bio": {"rows": rows}})

    def test_range_metric_marks_good_caution_and_manage(self) -> None:
        """적정 범위형 항목은 양호·주의·관리 필요를 경계값으로 가른다."""
        # 수축기 혈압 참고범위 90~119, 주의 구간 80~139.
        analysis = self._bio_analysis(_bio_days("blood_pressure", {
            "2026-08-01": 110, "2026-08-02": 130, "2026-08-03": 150, "2026-08-04": 115,
        }, "systolic"))
        systolic = _metric(analysis, "수축기 혈압")
        by_date = {item["date"]: item for item in systolic["anomalies"]}

        self.assertEqual(systolic["latest_status"], STATUS_GOOD)
        self.assertEqual(by_date["2026-08-02"]["status"], STATUS_CAUTION)
        self.assertEqual(by_date["2026-08-03"]["status"], STATUS_MANAGE)
        self.assertEqual(systolic["full"]["out_of_range_days"], 2)

    def test_metric_without_reference_stays_unjudged(self) -> None:
        """기준을 정할 수 없는 항목은 판정하지 않고 추세만 남긴다."""
        analysis = self._bio_analysis(_bio_days("weight", {
            "2026-08-01": 70.0, "2026-08-02": 71.0, "2026-08-03": 72.0, "2026-08-04": 73.0,
        }))
        weight = _metric(analysis, "체중")

        self.assertEqual(weight["reference"], "")
        self.assertEqual(weight["latest_status"], STATUS_UNKNOWN)
        self.assertEqual(weight["full"]["current_status"], STATUS_UNKNOWN)
        self.assertEqual(weight["full"]["out_of_range_days"], 0)
        self.assertEqual(weight["anomalies"], [])
        self.assertEqual(weight["full"]["direction"], "조금씩 오르는 흐름")

    def test_past_and_present_are_compared_by_half(self) -> None:
        """구간을 반으로 갈라 과거에 좋았는지 지금은 어떤지를 판정으로 남긴다."""
        analysis = self._bio_analysis(_bio_days("blood_pressure", {
            "2026-08-01": 110, "2026-08-02": 112, "2026-08-03": 130, "2026-08-04": 132,
        }, "systolic"))
        systolic = _metric(analysis, "수축기 혈압")

        self.assertEqual(systolic["full"]["earlier_average"], 111)
        self.assertEqual(systolic["full"]["earlier_status"], STATUS_GOOD)
        self.assertEqual(systolic["full"]["recent_average"], 131)
        self.assertEqual(systolic["full"]["current_status"], STATUS_CAUTION)
        self.assertEqual(systolic["full"]["change"], 20)
        self.assertEqual(systolic["full"]["direction"], "뚜렷하게 높아지는 흐름")

    def test_short_series_skips_half_comparison(self) -> None:
        """양쪽에 2점씩 없으면 전후반 비교를 하지 않고 데이터 부족으로 남긴다."""
        analysis = self._bio_analysis(_bio_days("blood_pressure", {
            "2026-08-01": 110, "2026-08-02": 118,
        }, "systolic"))
        systolic = _metric(analysis, "수축기 혈압")

        self.assertIsNone(systolic["full"]["earlier_average"])
        self.assertIsNone(systolic["full"]["change"])
        self.assertEqual(systolic["full"]["direction"], "판단하기 이름")
        self.assertEqual(systolic["full"]["confidence"], "부족")

    def test_spike_day_is_reported_with_both_reasons(self) -> None:
        """평소와 크게 다르면서 범위도 벗어난 날은 두 사유를 함께 남긴다."""
        values = {f"2026-08-{day:02d}": 110.0 for day in range(1, 11)}
        values["2026-08-05"] = 175.0
        analysis = self._bio_analysis(_bio_days("blood_pressure", values, "systolic"))
        spike = _metric(analysis, "수축기 혈압")["anomalies"][0]

        self.assertEqual(spike["date"], "2026-08-05")
        self.assertEqual(spike["status"], STATUS_MANAGE)
        self.assertIn("구간 평균과 크게 차이남", spike["reasons"])
        self.assertTrue(any("참고범위" in reason for reason in spike["reasons"]))

    def test_chronically_out_of_range_metric_reports_one_example(self) -> None:
        """늘 범위 밖인 항목은 같은 날을 늘어놓지 않고 예시 하루만 남긴다."""
        values = {f"2026-08-{day:02d}": 150.0 for day in range(1, 11)}
        analysis = self._bio_analysis(_bio_days("blood_pressure", values, "systolic"))
        systolic = _metric(analysis, "수축기 혈압")

        self.assertEqual(systolic["full"]["out_of_range_days"], 10)
        self.assertEqual(len(systolic["anomalies"]), 1)

    def test_coverage_ratio_flags_sparse_records(self) -> None:
        """기록이 드문 항목은 coverage_ratio로 총량을 단정할 수 없음을 알린다."""
        analysis = LifestyleReportService.build_analysis("nutrition", {
            "food": {"rows": [
                {"consumed_at": "2026-08-01T12:00:00", "calories": 900, "sodium": 3400},
                {"consumed_at": "2026-08-15T12:00:00", "calories": 900, "sodium": 3400},
            ]},
        })
        calories = _metric(analysis, "섭취칼로리")

        self.assertEqual(calories["full"]["days"], 2)
        # 영양 탭의 전체 구간은 90일이다.
        self.assertEqual(calories["full"]["coverage_ratio"], 0.02)
        self.assertEqual(calories["kind"], "accumulation")

    def test_long_series_is_downsampled_for_the_prompt(self) -> None:
        """1년 구간이어도 프롬프트에 넣는 계열은 상한을 넘지 않는다."""
        values = {f"2026-{month:02d}-{day:02d}": 110.0
                  for month in (1, 2, 3) for day in range(1, 29)}
        analysis = self._bio_analysis(_bio_days("blood_pressure", values, "systolic"))
        systolic = _metric(analysis, "수축기 혈압")

        self.assertEqual(systolic["full"]["days"], 84)
        self.assertTrue(systolic["series_downsampled"])
        self.assertLessEqual(len(systolic["series"]), 30)
        # 처음과 끝은 솎아내지 않는다.
        self.assertEqual(systolic["series"][0]["date"], "2026-01-01")
        self.assertEqual(systolic["series"][-1]["date"], "2026-03-28")


class LifestyleSignalTest(unittest.TestCase):
    """통계를 사람 말로 옮겨 두는 층. 모델이 숫자를 베끼지 않게 하는 장치다."""

    def _bio_analysis(self, rows: list[dict]) -> dict:
        return LifestyleReportService.build_analysis("bio", {"bio": {"rows": rows}})

    def test_steady_rise_reads_as_a_trend_even_when_the_percentage_is_small(self) -> None:
        """의미 있는 변화 폭은 항목마다 다르다. 체중 1%대 상승도 흐름으로 읽혀야 한다."""
        values = {f"2026-08-{day:02d}": 70.0 + day * 0.06 for day in range(1, 31)}
        weight = _metric(self._bio_analysis(_bio_days("weight", values)), "체중")

        self.assertEqual(weight["full"]["direction"], "조금씩 오르는 흐름")
        self.assertEqual(weight["full"]["stability"], "안정적")

    def test_tiny_wobble_on_a_flat_metric_is_not_called_a_trend(self) -> None:
        """제 수준 대비 미미한 움직임은 표준편차만 작다고 흐름으로 부르지 않는다."""
        values = {f"2026-08-{day:02d}": 72.0 + (0.1 if day % 2 else -0.1) for day in range(1, 31)}
        heart = _metric(self._bio_analysis(_bio_days("heart_rate", values)), "심박수")

        self.assertEqual(heart["full"]["direction"], "큰 변화 없음")
        self.assertEqual(heart["full"]["level"], "기준 범위 안")

    def test_repeated_breach_is_described_by_frequency_and_run_length(self) -> None:
        """한 번 벗어난 것과 계속 벗어나는 것은 뜻이 다르므로 빈도와 연속 횟수로 구분한다."""
        values = {f"2026-08-{day:02d}": 150.0 for day in range(1, 11)}
        systolic = _metric(self._bio_analysis(_bio_days("blood_pressure", values, "systolic")), "수축기 혈압")

        self.assertEqual(systolic["full"]["frequency"], "거의 매번")
        self.assertEqual(systolic["full"]["longest_out_of_range_run"], 10)
        self.assertEqual(systolic["full"]["level"], "기준을 크게 벗어남")

    def test_sparse_records_lower_confidence(self) -> None:
        """기록이 적으면 추세를 단정하지 못하도록 confidence로 알린다."""
        short = self._bio_analysis(_bio_days("weight", {"2026-08-01": 70.0, "2026-08-02": 70.5}))
        self.assertEqual(_metric(short, "체중")["full"]["confidence"], "부족")

        sparse = LifestyleReportService.build_analysis("nutrition", {"food": {"rows": [
            {"consumed_at": f"2026-08-{day:02d}T12:00:00", "calories": 900} for day in (1, 5, 9, 13)
        ]}})
        self.assertEqual(_metric(sparse, "섭취칼로리")["full"]["confidence"], "부족")

    def test_weekend_difference_is_reported_in_plain_words(self) -> None:
        """주말에 몰아 자는 습관은 전체 평균만 봐서는 보이지 않는다."""
        values = {}
        for day in range(1, 29):
            date = f"2026-09-{day:02d}"
            weekend = __import__("datetime").date.fromisoformat(date).isoweekday() >= 6
            values[date] = 9.0 if weekend else 6.0
        rows = [{"measured_at": f"{d}T23:00:00", "bio_type": "sleep", "value": v,
                 "detail_data": {}} for d, v in values.items()]
        analysis = LifestyleReportService.build_analysis("sleep", {"sleep": {"rows": rows}})

        self.assertEqual(_metric(analysis, "수면시간")["weekly_pattern"], "주말이 더 높음")

    def test_weekday_weekend_needs_both_sides(self) -> None:
        """한쪽에 이틀도 없으면 견줄 값이 아니다."""
        rows = [{"measured_at": f"2026-09-{day:02d}T23:00:00", "bio_type": "sleep",
                 "value": 7.0, "detail_data": {}} for day in (1, 2, 3)]
        analysis = LifestyleReportService.build_analysis("sleep", {"sleep": {"rows": rows}})

        self.assertEqual(_metric(analysis, "수면시간")["weekly_pattern"], "판단하기 이름")

    def test_clock_reads_utc_records_in_local_time(self) -> None:
        """기록은 UTC로 저장된다. 문자열을 잘라 읽으면 새벽이 오후가 된다."""
        # 새벽 1시 20분(KST)은 전날 16시 20분(UTC)으로 저장된다.
        self.assertEqual(_clock_text(_clock_minutes("2026-09-01T16:20:00+00:00")), "오전 1:20")
        self.assertEqual(_clock_text(_clock_minutes("2026-09-01T22:10:00+00:00")), "오전 7:10")
        # 시간대가 없으면 이미 지역 시간으로 적힌 값으로 본다.
        self.assertEqual(_clock_text(_clock_minutes("2026-09-01T01:20:00")), "오전 1:20")
        self.assertIsNone(_clock_minutes("날짜 아님"))

    def test_clock_average_wraps_around_midnight(self) -> None:
        """시각은 자정에서 되감긴다. 선형 평균을 쓰면 정반대 시각이 나온다."""
        # 23:50과 00:10의 평균은 정오가 아니라 자정이다.
        stats = _clock_stats([23 * 60 + 50, 10])

        self.assertEqual(_clock_text(stats["typical_minutes"]), "오전 12:00")
        self.assertLessEqual(stats["spread_minutes"], 20)

    def test_clock_spread_tells_regular_from_erratic(self) -> None:
        """같은 시각에 자는 사람과 들쭉날쭉한 사람이 갈려야 한다."""
        steady = _clock_stats([60, 65, 55, 70, 50])
        erratic = _clock_stats([60, 300, 1380, 180, 720])

        self.assertLess(steady["spread_minutes"], erratic["spread_minutes"])
        self.assertLessEqual(steady["spread_minutes"], 30)

    def test_sleep_timing_reads_bedtime_and_waketime(self) -> None:
        """취침·기상 시각의 규칙성과 주중·주말 차이를 잰다."""
        rows = []
        for day in range(1, 29):
            date = f"2026-09-{day:02d}"
            weekend = __import__("datetime").date.fromisoformat(date).isoweekday() >= 6
            bed = "03:00" if weekend else "01:00"
            wake = "11:00" if weekend else "07:00"
            rows.append({
                "measured_at": f"{date}T{bed}:00", "bio_type": "sleep", "value": 6.0,
                "detail_data": {"start_at": f"{date}T{bed}:00", "end_at": f"{date}T{wake}:00"},
            })
        timing = LifestyleReportService.build_analysis("sleep", {"sleep": {"rows": rows}})["sleep_timing"]

        self.assertEqual(timing["bedtime_typical"], "오전 1:34")
        # 주중 1시 · 주말 3시라 흔들림이 45분쯤 된다.
        self.assertEqual(timing["bedtime_regularity"], "보통")
        self.assertEqual(timing["bedtime_weekend"], "주말에 취침이 늦어짐")
        self.assertEqual(timing["waketime_weekend"], "주말에 기상이 늦어짐")

    def test_sleep_timing_needs_the_times(self) -> None:
        """시각이 없는 기록만 있으면 취침·기상 분석을 만들지 않는다."""
        rows = [{"measured_at": f"2026-09-{day:02d}T23:00:00", "bio_type": "sleep",
                 "value": 7.0, "detail_data": {}} for day in range(1, 11)]
        analysis = LifestyleReportService.build_analysis("sleep", {"sleep": {"rows": rows}})

        self.assertIsNone(analysis["sleep_timing"])

    def test_sleep_timing_only_exists_on_the_sleep_tab(self) -> None:
        for domain in ("bio", "activity", "nutrition"):
            with self.subTest(domain=domain):
                analysis = LifestyleReportService.build_analysis(domain, LIFESTYLE_WINDOW)
                self.assertIsNone(analysis["sleep_timing"])

    def test_co_movement_pairs_items_inside_the_same_tab(self) -> None:
        """탭 안에서 함께 움직인 짝을 찾는다. 다른 탭과는 엮지 않는다."""
        rows = []
        for day in range(1, 21):
            date = f"2026-08-{day:02d}"
            rows += _bio_days("weight", {date: 70.0 + day * 0.1})
            rows += _bio_days("bmi", {date: 23.0 + day * 0.03})
            rows += _bio_days("heart_rate", {date: 72.0 + (2 if day % 2 else -2)})
        pairs = self._bio_analysis(rows)["co_movements"]
        paired = {tuple(sorted(item["metrics"])): item for item in pairs}

        self.assertIn(("BMI", "체중"), paired)
        self.assertEqual(paired[("BMI", "체중")]["relation"], "같은 방향으로 움직임")
        # 무관하게 튀는 항목은 짝으로 엮지 않는다.
        self.assertNotIn(("심박수", "체중"), paired)

    def test_constant_series_does_not_break_co_movement(self) -> None:
        """값이 내내 같으면 상관을 정의할 수 없다. 오류 대신 짝에서 빠져야 한다."""
        rows = []
        for day in range(1, 11):
            date = f"2026-08-{day:02d}"
            rows += _bio_days("weight", {date: 70.0})
            rows += _bio_days("bmi", {date: 23.0})

        self.assertEqual(self._bio_analysis(rows)["co_movements"], [])


class LifestylePromptTest(unittest.TestCase):
    """프롬프트 v2.0은 탭마다 다른 지침을 주고, 원시 통계는 넘기지 않는다."""

    def _prompt(self, domain: str) -> str:
        analysis = LifestyleReportService.build_analysis(domain, LIFESTYLE_WINDOW)
        return LifestyleReportService.build_prompt(domain, analysis)

    def test_output_contract_leaves_no_room_to_pad(self) -> None:
        """자리가 있으면 모델이 채운다. 빈칸을 줄여 되풀이와 뜬구름 조언을 막는다."""
        from app.schemas.lifestyle_report import LifestyleReportContent

        self.assertEqual(set(LifestyleReportContent.model_fields),
                         {"headline", "current_state", "actions"})
        self.assertEqual(
            LifestyleReportContent.model_fields["actions"].metadata[0].max_length, 2)

    def test_prompt_allows_the_reference_range_once(self) -> None:
        """참고범위는 자기 위치를 가늠하는 데 쓸모가 있어 한 번은 허용한다."""
        prompt = self._prompt("sleep")

        self.assertIn("딱 한 번만 쓸 수 있다", prompt)
        # 금지 목록에서는 빠졌다.
        self.assertNotIn("상관계수, 참고범위 수치, 측정 날짜", prompt)
        # 개수를 채우려고 일반 조언을 덧붙이지 못하게 막는다.
        self.assertIn("개수를 채우려고 데이터에 없는 일반 조언을 덧붙이지 마라", prompt)
        self.assertIn("actions: 0~2개", prompt)
        self.assertNotIn("key_points", prompt)

    def test_actions_must_be_concrete(self) -> None:
        """'일찍 주무세요'는 조언이 아니다. 몇 시에 자면 되는지가 조언이다."""
        prompt = self._prompt("sleep")

        self.assertIn('"일찍 주무세요"는 조언이 아니다', prompt)
        self.assertIn("오늘 당장 할 수 있는 모습으로 적어라", prompt)

    def test_active_prompt_is_version_four(self) -> None:
        self.assertEqual(PROMPT_VERSION, "4.0")

    def test_earlier_prompts_are_kept_for_comparison(self) -> None:
        """이전 판을 지우지 않아야 여러 판을 견주고 되돌릴 수 있다."""
        for module, version in ((prompt_v1, "1.0"), (prompt_v2, "2.0"), (prompt_v3, "3.0")):
            with self.subTest(version=version):
                self.assertEqual(module.VERSION, version)
                self.assertIn("bio", module.DOMAIN_GUIDES)
                self.assertTrue(module.COMMON_RULES.strip())

    def test_sleep_guide_judges_quality_by_stage_share(self) -> None:
        """잠의 길이는 시간으로, 잠의 질은 단계 비중으로 말하게 한다."""
        prompt = self._prompt("sleep")

        self.assertIn("수면시간과 수면점수를 나란히 놓고 비교하지 마라", prompt)
        self.assertIn("잠의 길이는 시간으로, 잠의 질은 단계 비중으로 말하라", prompt)
        self.assertIn("분 단위 단계(깊은수면·얕은수면·REM수면)는 참고범위가 없다", prompt)
        # 기기의 점수 산출식은 공개되지 않는다. 특정 단계를 원인으로 못박으면 안 된다.
        self.assertNotIn("REM수면이 낮으면", prompt)
        self.assertNotIn("깊은수면이 낮으면", prompt)
        self.assertIn("co_movements에 수면점수와 함께 움직인 항목이 잡혔다면", prompt)
        # 총량과 구성요소가 같이 움직이는 것은 당연하다.
        self.assertIn("총량과 그 구성요소가 같이 움직이는 것은 당연한 일", prompt)

    def test_sleep_stages_are_judged_by_share_not_minutes(self) -> None:
        """분수만으로는 좋고 나쁨을 말할 수 없다. 총 수면 대비 비중이라야 판정이 선다."""
        # 6시간 자면서 REM 60분은 16.7%로 권장(20~25%)에 못 미친다.
        rows = [{
            "measured_at": f"2026-09-{day:02d}T23:00:00", "bio_type": "sleep", "value": 6.0,
            "detail_data": {"deep_sleep_minutes": 54, "light_sleep_minutes": 200,
                            "rem_sleep_minutes": 60, "awake_minutes": 20, "sleep_score": 70},
        } for day in range(1, 15)]
        analysis = LifestyleReportService.build_analysis("sleep", {"sleep": {"rows": rows}})

        # 분으로 보는 항목은 여전히 판정하지 않는다.
        self.assertEqual(_metric(analysis, "REM수면")["full"]["level"], "기준 없음")
        # 비중으로 보면 판정이 선다.
        rem_share = _metric(analysis, "REM수면 비중")
        self.assertEqual(rem_share["reference"], "20~25 %")
        self.assertEqual(rem_share["full"]["level"], "기준을 조금 벗어남")
        self.assertEqual(rem_share["full"]["frequency"], "거의 매번")
        # 깊은수면 54분은 15%라 권장(13~23%) 안이다.
        self.assertEqual(_metric(analysis, "깊은수면 비중")["full"]["level"], "기준 범위 안")

    def test_share_needs_the_total(self) -> None:
        """총 수면시간이 없으면 비중을 낼 수 없다. 0으로 나누지 않는다."""
        rows = [{"measured_at": f"2026-09-{day:02d}T23:00:00", "bio_type": "sleep", "value": 0,
                 "detail_data": {"rem_sleep_minutes": 60}} for day in range(1, 8)]
        analysis = LifestyleReportService.build_analysis("sleep", {"sleep": {"rows": rows}})

        self.assertNotIn("REM수면 비중", [item["metric"] for item in analysis["metrics"]])

    def test_trivial_pairs_never_reach_the_model(self) -> None:
        """쓰지 말라고 한 짝을 재료로 건네면 모델은 그것을 쓴다. 아예 넘기지 않는다."""
        rows = []
        for day in range(1, 29):
            # 잠이 길수록 점수도 오르고 단계도 함께 길어지는, 흔한 모양이다.
            total = 5.0 + (day % 7) * 0.5
            rows.append({
                "measured_at": f"2026-09-{day:02d}T23:00:00", "bio_type": "sleep", "value": total,
                "detail_data": {"sleep_score": 50 + total * 5,
                                "deep_sleep_minutes": total * 9,
                                "light_sleep_minutes": total * 34,
                                "rem_sleep_minutes": total * 12,
                                "awake_minutes": total * 4},
            })
        pairs = LifestyleReportService.build_analysis("sleep", {"sleep": {"rows": rows}})["co_movements"]
        found = {frozenset(item["metrics"]) for item in pairs}

        self.assertNotIn(frozenset({"수면시간", "수면점수"}), found)
        for stage in ("깊은수면", "얕은수면", "REM수면", "뒤척임"):
            with self.subTest(stage=stage):
                self.assertNotIn(frozenset({"수면시간", stage}), found)

    def test_bedtime_target_is_computed_not_left_to_the_model(self) -> None:
        """시각 뺄셈은 자정을 넘나들어 모델이 틀리기 쉽다. 코드가 계산해 넘긴다."""
        rows = []
        for day in range(1, 29):
            date = f"2026-09-{day:02d}"
            # 매일 0시 40분에 자고 7시 10분에 일어난다. 6시간 30분이라 권장에 못 미친다.
            rows.append({
                "measured_at": f"{date}T00:40:00+09:00", "bio_type": "sleep", "value": 6.5,
                "detail_data": {"start_at": f"{date}T00:40:00+09:00",
                                "end_at": f"{date}T07:10:00+09:00"},
            })
        timing = LifestyleReportService.build_analysis("sleep", {"sleep": {"rows": rows}})["sleep_timing"]

        # 기상 7:10에서 7시간을 빼면 0:10이다.
        self.assertEqual(timing["waketime_typical"], "오전 7:10")
        self.assertEqual(timing["bedtime_target"], "오전 12:10")
        self.assertEqual(timing["bedtime_shift"], "지금보다 30분쯤 일찍")

    def test_bedtime_target_stays_quiet_when_already_enough(self) -> None:
        """이미 권장 시간을 채우고 있으면 취침을 당기라고 하지 않는다."""
        rows = [{"measured_at": f"2026-09-{day:02d}T23:00:00+09:00", "bio_type": "sleep",
                 "value": 8.0,
                 "detail_data": {"start_at": f"2026-09-{day:02d}T23:00:00+09:00",
                                 "end_at": f"2026-09-{day:02d}T07:00:00+09:00"}}
                for day in range(1, 29)]
        timing = LifestyleReportService.build_analysis("sleep", {"sleep": {"rows": rows}})["sleep_timing"]

        self.assertEqual(timing["bedtime_shift"], "지금 취침 시각으로도 닿는다")

    def test_sleep_prompt_ties_the_score_to_stage_shares(self) -> None:
        """점수·시간·비중을 따로 늘어놓지 말고 어느 쪽이 원인에 가까운지 말하게 한다."""
        prompt = self._prompt("sleep")

        self.assertIn("비중은 기준 안인데 점수가 낮다면 구성이 아니라 잠의 길이가", prompt)
        self.assertIn("단정하지는 마라", prompt)
        # 막연한 '일찍 자라' 대신 계산된 시각을 그대로 쓰게 한다.
        self.assertIn("bedtime_target이 있으면", prompt)

    def test_activity_prompt_separates_exercise_from_daily_movement(self) -> None:
        """한 번에 오래 하는데 모자란 것이면 '더 오래'가 아니라 '한 번 더'가 맞다."""
        prompt = self._prompt("activity")

        self.assertIn("운동은 활동과 갈라서 말하라", prompt)
        self.assertIn("운동시간 항목의 수치가 아니라 이것을 쓰라", prompt)
        self.assertIn('"한 번 더 나가 보세요"가 맞는 말이다', prompt)
        self.assertIn('"운동을 늘리세요"는 조언이 아니다', prompt)
        # 운동한 날만 이어 붙인 계열의 direction을 운동량으로 읽지 못하게 막는다.
        self.assertIn("운동이 늘었는지 줄었는지는 **오직 이것으로만** 말하라", prompt)
        self.assertIn('"운동량이 줄고 있다"고 쓰면 틀린 말이 된다', prompt)
        self.assertIn("늘릴 여지는 비어 있는 쪽에 있다", prompt)
        # 기록이 없는 것을 게으름으로 읽지 않게 막는다.
        self.assertIn("기록을 안 했을 수도 있다", prompt)

    def test_nutrition_prompt_uses_shares_and_meals(self) -> None:
        """그램으로 균형을 말할 수 없고, 총량만으로는 어디를 손댈지 알 수 없다."""
        prompt = self._prompt("nutrition")

        self.assertIn("균형을 말할 때는 그램이 아니라 이 비중으로 말하라", prompt)
        # 셋은 합이 100이라 따로 세면 같은 사실을 두 번 말하게 된다.
        self.assertIn("어느 쪽으로 치우쳤는지 한 번만 말하라", prompt)
        self.assertIn("저녁 국물부터 줄여보세요", prompt)
        # 간식을 애먼 범인으로 지목하지 못하게 막는다.
        self.assertIn("간식을 문제로 지목하지 마라", prompt)
        self.assertIn("기록을 안 했을 수도 있다", prompt)

    def test_prompt_teaches_how_to_connect_sentences(self) -> None:
        """'하나의 이야기로 묶어라'만으로는 한 문장에 한 항목씩 나열했다."""
        prompt = self._prompt("bio")

        self.assertIn("한 문장에 한 항목씩 늘어놓으면 나열이지 이야기가 아니다", prompt)
        self.assertIn("그래서·반면·그런데·다만", prompt)
        self.assertIn("서로 어긋나 보이는 값이 있으면", prompt)

    def test_sleep_prompt_carries_bedtime_and_waketime(self) -> None:
        """취침·기상 시각은 잠의 길이만으로는 안 보이는 것이라 프롬프트에 넘긴다."""
        prompt = self._prompt("sleep")

        self.assertIn("sleep_timing은 취침·기상 시각을 따로 잰 값이다", prompt)
        self.assertIn("regularity가 \'들쭉날쭉함\'이면 몇 시간 잤는지보다 그것이 먼저다", prompt)
        # 시각 통계 원본은 넘기지 않는다. 대표 시각과 판정어만 간다.
        self.assertNotIn("spread_minutes", prompt)
        self.assertNotIn("typical_minutes", prompt)

    def test_every_prompt_mentions_the_weekday_weekend_split(self) -> None:
        """주중·주말 차이는 모든 탭에서 쓸 수 있는 재료다."""
        for domain in ("bio", "activity", "nutrition", "sleep"):
            with self.subTest(domain=domain):
                self.assertIn("weekly_pattern은 주중과 주말의 차이다", self._prompt(domain))

    def test_each_domain_gets_only_its_own_guide(self) -> None:
        guides = {
            "bio": "[생체기록 탭]",
            "activity": "[활동기록 탭]",
            "nutrition": "[영양기록 탭]",
            "sleep": "[수면기록 탭]",
        }
        for domain, marker in guides.items():
            with self.subTest(domain=domain):
                prompt = self._prompt(domain)
                self.assertIn(marker, prompt)
                for other, other_marker in guides.items():
                    if other != domain:
                        self.assertNotIn(other_marker, prompt)

    def test_prompt_keeps_the_safety_and_no_re_judging_rules(self) -> None:
        """판정은 코드 몫이고 진단은 하지 않는다는 규칙은 판이 바뀌어도 남는다."""
        for domain in ("bio", "activity", "nutrition", "sleep"):
            with self.subTest(domain=domain):
                prompt = self._prompt(domain)
                self.assertIn("재판정하지 말고", prompt)
                self.assertIn("질환을 단정하거나 겁주지 마라", prompt)
                self.assertIn("일반 성인 기준", prompt)

    def test_prompt_bans_statistics_dumping_and_abstract_advice(self) -> None:
        """v2.0의 핵심은 통계 나열과 뜬구름 조언을 둘 다 막는 것이다."""
        prompt = self._prompt("bio")

        self.assertIn("전반·후반 평균, 증감량과 증감률, 변동계수, 기록률", prompt)
        self.assertIn("여러 날을 늘어놓지 마라", prompt)
        self.assertIn("추상적인 조언만 쓰지 마라", prompt)
        self.assertIn("반드시 데이터에서 찾은 것을 말하라", prompt)
        self.assertIn("30초 안에 읽고", prompt)

    def test_raw_statistics_never_reach_the_prompt(self) -> None:
        """줄 재료가 없으면 나열할 수도 없다. 원시 통계는 프롬프트에 넣지 않는다."""
        prompt = self._prompt("bio")

        for leaked in ("earlier_average", "recent_average", "change_rate", '"cv"',
                       "stdev", "out_of_range_days", '"series"', "minimum", "maximum",
                       "deviation_sigma", "coefficient"):
            with self.subTest(field=leaked):
                self.assertNotIn(leaked, prompt)

    def test_prompt_carries_the_plain_language_signals_instead(self) -> None:
        """원시 통계 대신 같은 뜻을 담은 자연어 표현을 넘긴다."""
        prompt = self._prompt("bio")

        for signal in ("level", "frequency", "direction", "stability", "confidence", "co_movements"):
            with self.subTest(signal=signal):
                self.assertIn(f'"{signal}"', prompt)

    def test_prompt_shows_at_most_one_example_day_per_metric(self) -> None:
        """날짜 나열을 막으려면 예시 날짜를 항목당 하나만 줘야 한다."""
        # 소수의 날만 벗어나야 만성 필터에 걸리지 않고 여러 건이 남는다.
        values = {f"2026-08-{day:02d}": 110.0 for day in range(1, 21)}
        values.update({"2026-08-05": 145.0, "2026-08-11": 152.0, "2026-08-17": 149.0})
        analysis = LifestyleReportService.build_analysis(
            "bio", {"bio": {"rows": _bio_days("blood_pressure", values, "systolic")}})
        view = _prompt_view(analysis)
        systolic = next(item for item in view["metrics"] if item["metric"] == "수축기 혈압")

        # 계산 결과에는 여러 건이 남아 있지만 프롬프트에는 한 건만 간다.
        self.assertGreater(len(_metric(analysis, "수축기 혈압")["anomalies"]), 1)
        self.assertEqual(len(systolic["example_day"]), 1)

    def test_full_statistics_stay_available_for_verification(self) -> None:
        """사용자 화면에서 뺀 통계는 개발자 검증 화면에서 그대로 볼 수 있어야 한다."""
        analysis = LifestyleReportService.build_analysis("bio", LIFESTYLE_WINDOW)
        weight = _metric(analysis, "체중")

        for kept in ("series", "anomalies", "latest", "latest_status"):
            with self.subTest(field=kept):
                self.assertIn(kept, weight)
        for kept in ("earlier_average", "recent_average", "change", "change_rate", "cv",
                     "stdev", "out_of_range_days", "coverage_ratio", "covered_range"):
            with self.subTest(field=kept):
                self.assertIn(kept, weight["full"])


if __name__ == "__main__":
    unittest.main()
