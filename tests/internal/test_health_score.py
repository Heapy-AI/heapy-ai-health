"""생활습관 관리 점수 v2가 정한 대로 계산하는지 지킨다.

점수는 사용자에게 숫자 하나로 나가기 때문에 식이 조용히 바뀌면 알아채기 어렵다.
그래서 성분별 곡선의 경계값과 결격 규칙을 여기에 박아 둔다.

백엔드 Java v1에서 이어받은 값(활동·BMI·충분성 기울기)은 따로 표시해 둔다.
이 값들이 바뀌면 백엔드와 어긋난다는 뜻이므로 함께 고쳐야 한다.

작성자: 고수연
"""

import re
import unittest
from datetime import date, timedelta
from pathlib import Path

from app.services import health_score as score


BASE = date(2026, 9, 13)


def _sleep_rows(plan: dict[int, tuple[int, int, float]]) -> list[dict]:
    """{며칠 전: (취침 시, 취침 분, 수면시간)} 를 수면 행으로 바꾼다."""
    rows = []
    for offset, (bed_hour, bed_minute, hours) in plan.items():
        day = BASE - timedelta(days=offset)
        start = f"{day.isoformat()}T{bed_hour:02d}:{bed_minute:02d}:00+09:00"
        end_total = bed_hour * 60 + bed_minute + int(hours * 60)
        end_day = day + timedelta(days=end_total // 1440)
        hour, minute = divmod(end_total % 1440, 60)
        rows.append({
            "measured_at": day.isoformat(),
            "value": hours,
            "detail_data": {
                "start_at": start,
                "end_at": f"{end_day.isoformat()}T{hour:02d}:{minute:02d}:00+09:00",
            },
        })
    return rows


def _window(sleep: list[dict], steps: float = 9000, bmi: float = 22.0,
            bmi_days_ago: int = 3) -> dict:
    """세 성분이 모두 서는 기본 입력. 필요한 쪽만 덜어내며 쓴다."""
    return {
        "sleep": {"rows": sleep, "truncated": False},
        "activity": {"rows": [{"record_date": (BASE - timedelta(days=day)).isoformat(),
                               "steps": steps} for day in range(14)], "truncated": False},
        "exercise": {"rows": [], "truncated": False},
        "bio": {"rows": [{"measured_at": (BASE - timedelta(days=bmi_days_ago)).isoformat(),
                          "bio_type": "bmi", "value": bmi}], "truncated": False},
    }


def _steady(hours: float = 7.5, days: int = 14) -> list[dict]:
    """매일 같은 시각에 같은 만큼 자는 사람."""
    return _sleep_rows({day: (23, 0, hours) for day in range(days)})


class ComponentCurveTest(unittest.TestCase):
    """성분별 점수 곡선의 경계값."""

    def test_duration_follows_the_backend_slopes(self) -> None:
        """충분성은 백엔드 v1의 기울기를 그대로 잇는다. 바꾸면 백엔드와 어긋난다."""
        for hours, expected in ((7, 100), (8, 100), (9, 100), (6, 75), (5, 50), (3, 0),
                                (10, 85), (9.5, 92.5)):
            with self.subTest(hours=hours):
                self.assertAlmostEqual(score.duration_score(hours), expected)

    def test_regularity_bends_at_the_screen_thresholds(self) -> None:
        """30분·60분은 생활건강 탭이 '일정함·보통'을 가르는 문턱과 같은 값이다."""
        self.assertEqual(score.regularity_score(0), 100)
        self.assertEqual(score.regularity_score(30), 100)
        self.assertEqual(score.regularity_score(60), 60)
        self.assertEqual(score.regularity_score(120), 0)
        self.assertEqual(score.regularity_score(300), 0)
        # 두 토막이라 45분은 100과 60의 한가운데다.
        self.assertAlmostEqual(score.regularity_score(45), 80)

    def test_stability_and_jetlag_reach_zero_where_documented(self) -> None:
        self.assertEqual(score.stability_score(30), 100)
        self.assertEqual(score.stability_score(60), 50)
        self.assertEqual(score.stability_score(90), 0)
        # 45분은 '주중과 주말이 다르다'고 보기 시작하는 문턱이라 여기까지는 만점이다.
        self.assertEqual(score.social_jetlag_score(45), 100)
        self.assertEqual(score.social_jetlag_score(120), 0)
        # 어느 쪽으로 밀렸는지는 보지 않는다.
        self.assertEqual(score.social_jetlag_score(-90), score.social_jetlag_score(90))

    def test_activity_takes_the_better_of_steps_and_exercise(self) -> None:
        """백엔드 v1과 같다. 걸어서 채우든 운동으로 채우든 같이 본다."""
        self.assertEqual(score.activity_score(8000, None), 100)
        self.assertEqual(score.activity_score(4000, None), 50)
        self.assertEqual(score.activity_score(None, 30), 100)
        self.assertEqual(score.activity_score(2000, 30), 100)
        self.assertEqual(score.activity_score(16000, None), 100)
        self.assertIsNone(score.activity_score(None, None))

    def test_bmi_follows_the_bio_tab_bands(self) -> None:
        """생체 탭의 양호·주의 경계를 그대로 쓴다. 탭이 '주의'라 한 값이 만점이면 안 된다."""
        for value, expected in ((18.5, 100), (21, 100), (22.9, 100),   # 양호
                                (17, 60), (24.9, 60),                   # 주의 경계
                                (24, 78), (25, 58.8), (27, 34.8),       # 사이
                                (29.9, 0), (35, 0), (12, 0)):           # 바깥
            with self.subTest(bmi=value):
                self.assertAlmostEqual(score.bmi_score(value), expected, places=1)

    def test_bmi_does_not_use_the_western_cutoff(self) -> None:
        """23부터 과체중인 아시아·태평양 기준이다. WHO 서구 기준(25)을 쓰면 탭과 어긋난다."""
        self.assertLess(score.bmi_score(24), 100)


class SleepCompositionTest(unittest.TestCase):
    """수면을 넷으로 가른 것이 실제로 구별을 만드는지."""

    def test_same_hours_but_irregular_timing_scores_lower(self) -> None:
        """v2를 만든 이유다. v1은 둘을 같은 점수로 봤다."""
        steady = score.calculate(_window(_steady()), age=35, as_of=BASE.isoformat())
        erratic = score.calculate(
            _window(_sleep_rows({day: ((23, 0, 7.5) if day % 2 else (2, 30, 7.5))
                                 for day in range(14)})),
            age=35, as_of=BASE.isoformat())

        self.assertEqual(steady["components"]["sleep"]["parts"]["duration"]["score"],
                         erratic["components"]["sleep"]["parts"]["duration"]["score"])
        self.assertLess(erratic["components"]["sleep"]["score"],
                        steady["components"]["sleep"]["score"])
        self.assertLess(erratic["total_score"], steady["total_score"])

    def test_weekend_lie_in_shows_up_as_social_jetlag(self) -> None:
        """주중 23시·주말 새벽 2시에 자면 수면 중점이 네 시간 어긋난다."""
        plan = {}
        for offset in range(14):
            day = BASE - timedelta(days=offset)
            plan[offset] = (2, 0, 9.0) if day.isoweekday() >= 6 else (23, 0, 7.0)
        result = score.calculate(_window(_sleep_rows(plan)), age=35, as_of=BASE.isoformat())

        jetlag = result["components"]["sleep"]["parts"]["social_jetlag"]
        self.assertEqual(jetlag["gap_minutes"], 240)
        self.assertEqual(jetlag["score"], 0)

    def test_midsleep_crosses_midnight(self) -> None:
        """23:30에 자 7시간을 자면 수면 중점은 새벽 3시다. 선형 평균으로는 나오지 않는 값이다."""
        result = score.calculate(_window(_sleep_rows({day: (23, 30, 7.0) for day in range(14)})),
                                 age=35, as_of=BASE.isoformat())
        self.assertEqual(
            result["components"]["sleep"]["parts"]["social_jetlag"]["weekday_midsleep"],
            "오전 3:00")

    def test_missing_parts_renormalize_instead_of_voiding_the_score(self) -> None:
        """사회적 시차 하나 없다고 점수를 통째로 못 내면 대부분의 사용자가 점수를 못 본다."""
        rows = [{"measured_at": (BASE - timedelta(days=day)).isoformat(),
                 "value": 7.5, "detail_data": {}} for day in range(14)]
        result = score.calculate(_window(rows), age=35, as_of=BASE.isoformat())

        sleep = result["components"]["sleep"]
        self.assertIsNotNone(result["total_score"])
        self.assertEqual(sorted(sleep["missing_parts"]), ["regularity", "social_jetlag"])
        self.assertAlmostEqual(sleep["coverage"], 0.65)
        # 빠진 성분은 수면 안쪽 일이라 총점을 막는 reasons에는 올라가지 않는다.
        self.assertEqual(result["reasons"], [])


def _checkup(day: str, bmi: float | None = 24.1) -> list[dict]:
    """검진 회차 하나. BMI 항목 이름은 기관마다 다르다."""
    results = [{"item_code": "GLU", "item_name": "공복혈당", "value": 95}]
    if bmi is not None:
        results.insert(0, {"item_code": "BMI", "item_name": "체질량지수",
                           "value": bmi, "unit": "kg/m2"})
    return [{"date": day, "results": results}]


class CheckupBmiTest(unittest.TestCase):
    """체중계를 쓰지 않는 사용자도 점수를 받게 하는 길이다."""

    def _without_bio(self) -> dict:
        window = _window(_steady())
        window["bio"]["rows"] = []
        return window

    def test_checkup_fills_in_for_a_missing_bmi(self) -> None:
        """생활 기록에 BMI가 없으면 총점이 아예 나오지 않았다. 검진이 그 자리를 채운다."""
        blocked = score.calculate(self._without_bio(), age=35, as_of=BASE.isoformat())
        self.assertIsNone(blocked["total_score"])
        self.assertIn("bmi_missing", blocked["reasons"])

        filled = score.calculate(self._without_bio(), age=35, as_of=BASE.isoformat(),
                                 checkups=_checkup("2026-04-02"))
        self.assertIsNotNone(filled["total_score"])
        bmi = filled["components"]["bmi"]
        self.assertEqual("checkup", bmi["source"])
        self.assertEqual("2026-04-02", bmi["measured_date"])
        self.assertEqual(24.1, bmi["value"])

    def test_the_more_recent_measurement_wins(self) -> None:
        """둘 다 있으면 최근 것을 쓴다. 검진이 반년 전이면 어제 잰 체중계가 낫다."""
        result = score.calculate(_window(_steady()), age=35, as_of=BASE.isoformat(),
                                 checkups=_checkup("2026-04-02"))
        self.assertEqual("lifestyle", result["components"]["bmi"]["source"])

    def test_a_stale_lifestyle_record_falls_back_to_the_checkup(self) -> None:
        window = self._without_bio()
        window["bio"]["rows"] = [{"measured_at": "2026-01-05", "bio_type": "bmi", "value": 21.0}]
        result = score.calculate(window, age=35, as_of=BASE.isoformat(),
                                 checkups=_checkup("2026-04-02"))
        self.assertEqual("checkup", result["components"]["bmi"]["source"])

    def test_checkups_older_than_a_year_do_not_count(self) -> None:
        """국가 검진이 연 1회라 1년까지는 받지만 그보다 오래되면 지금을 말해 주지 못한다."""
        result = score.calculate(self._without_bio(), age=35, as_of=BASE.isoformat(),
                                 checkups=_checkup("2024-01-01"))
        self.assertIsNone(result["total_score"])
        self.assertIn("bmi_stale", result["reasons"])

    def test_a_checkup_without_a_bmi_item_is_not_a_source(self) -> None:
        result = score.calculate(self._without_bio(), age=35, as_of=BASE.isoformat(),
                                 checkups=_checkup("2026-04-02", bmi=None))
        self.assertIn("bmi_missing", result["reasons"])

    def test_a_checkup_value_carries_a_notice_for_the_user(self) -> None:
        """검진 BMI는 다음 검진까지 바뀌지 않는다. 왜 점수가 안 움직이는지 밝혀야 한다."""
        result = score.calculate(self._without_bio(), age=35, as_of=BASE.isoformat(),
                                 checkups=_checkup("2026-04-02"))
        notice = result["components"]["bmi"]["notice"]
        self.assertIn("2026년 4월", notice)
        self.assertIn("건강검진", notice)

    def test_a_lifestyle_value_carries_no_notice(self) -> None:
        """체중계로 잰 값은 굳이 밝힐 것이 없다."""
        result = score.calculate(_window(_steady()), age=35, as_of=BASE.isoformat())
        self.assertEqual("", result["components"]["bmi"]["notice"])

    def test_checkups_after_the_base_date_are_ignored(self) -> None:
        """아직 오지 않은 날의 검진으로 과거 점수를 매기지 않는다."""
        result = score.calculate(self._without_bio(), age=35, as_of="2026-03-01",
                                 checkups=_checkup("2026-04-02"))
        self.assertIn("bmi_missing", result["reasons"])


class DisqualificationTest(unittest.TestCase):
    """총점을 내지 않아야 할 때. lifestyle_daily_scores 테이블의 제약과 같은 규칙이다."""

    def _assert_blocked(self, result: dict, reason: str) -> None:
        self.assertIsNone(result["total_score"])
        self.assertIn(reason, result["reasons"])

    def test_each_missing_component_blocks_the_total(self) -> None:
        cases = {
            "sleep_insufficient": _window(_steady(days=4)),
            "activity_insufficient": None,
            "bmi_stale": _window(_steady(), bmi_days_ago=200),
        }
        short_activity = _window(_steady())
        short_activity["activity"]["rows"] = short_activity["activity"]["rows"][:3]
        cases["activity_insufficient"] = short_activity

        for reason, window in cases.items():
            with self.subTest(reason=reason):
                self._assert_blocked(score.calculate(window, age=35, as_of=BASE.isoformat()),
                                     reason)

        missing_bmi = _window(_steady())
        missing_bmi["bio"]["rows"] = []
        self._assert_blocked(score.calculate(missing_bmi, age=35, as_of=BASE.isoformat()),
                             "bmi_missing")

    def test_age_rules_follow_the_backend(self) -> None:
        """만 20세 미만은 성인 기준을 그대로 대기 어렵다. 백엔드 v1과 같은 판단이다."""
        window = _window(_steady())
        self._assert_blocked(score.calculate(window, age=None, as_of=BASE.isoformat()),
                             "age_unavailable")
        self._assert_blocked(score.calculate(window, age=17, as_of=BASE.isoformat()),
                             "age_not_supported")
        self.assertIsNotNone(
            score.calculate(window, age=20, as_of=BASE.isoformat())["total_score"])

    def test_truncated_input_blocks_the_total(self) -> None:
        """조회 상한에 걸려 기록이 잘렸으면 그 날의 점수를 확정하지 않는다."""
        window = _window(_steady())
        window["sleep"]["truncated"] = True
        self._assert_blocked(score.calculate(window, age=35, as_of=BASE.isoformat()),
                             "data_limit_exceeded")


class TotalTest(unittest.TestCase):
    def test_total_uses_the_backend_weights(self) -> None:
        """수면 .45 + 활동 .45 + BMI .10. 백엔드 v1의 배분을 그대로 잇는다."""
        self.assertEqual(score._WEIGHTS, {"sleep": 0.45, "activity": 0.45, "bmi": 0.10})
        self.assertAlmostEqual(sum(score._WEIGHTS.values()), 1.0)
        self.assertAlmostEqual(sum(score._SLEEP_WEIGHTS.values()), 1.0)

    def test_perfect_record_scores_one_hundred(self) -> None:
        result = score.calculate(_window(_steady()), age=35, as_of=BASE.isoformat())
        self.assertEqual(result["total_score"], 100)
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["policy_version"], "heapy-lifestyle-v2")

    def test_series_covers_every_day_in_the_range(self) -> None:
        window = _window(_steady())
        since = (BASE - timedelta(days=6)).isoformat()
        points = score.calculate_series(window, since, BASE.isoformat(), age=35)
        self.assertEqual(len(points), 7)
        self.assertEqual([point["score_date"] for point in points][0], since)
        self.assertEqual([point["score_date"] for point in points][-1], BASE.isoformat())


class DocumentTest(unittest.TestCase):
    """기준 문서가 코드의 실제 값을 그대로 적고 있는지 본다.

    점수는 숫자 하나로 나가기 때문에 문서와 코드가 갈라져도 화면에서는 드러나지 않는다.
    한쪽만 고치면 여기서 실패한다.
    """

    DOC = (Path(__file__).resolve().parents[2] / "docs" / "생활습관_관리점수_기준.md")

    def setUp(self) -> None:
        self.body = self.DOC.read_text(encoding="utf-8")

    def test_the_weights_are_written_down(self) -> None:
        weights = score._WEIGHTS
        self.assertIn(f"수면 × {weights['sleep']:.2f} + 활동 × {weights['activity']:.2f}"
                      f" + BMI × {weights['bmi']:.2f}", self.body)
        parts = score._SLEEP_WEIGHTS
        self.assertIn(f"충분성 × {parts['duration']:.2f} + 규칙성 × {parts['regularity']:.2f}"
                      f" + 안정성 × {parts['stability']:.2f}"
                      f" + 사회적 시차 × {parts['social_jetlag']:.2f}", self.body)

    def test_every_threshold_is_written_down(self) -> None:
        for text in (
            # 충분성
            f"{score._GOOD_HOURS_LOW:g}~{score._GOOD_HOURS_HIGH:g}시간",
            f"시간당 **−{score._SHORT_PENALTY_PER_HOUR:g}**",
            f"시간당 **−{score._LONG_PENALTY_PER_HOUR:g}**",
            # 규칙성
            f"| {score._CLOCK_STEADY_MINUTES}분 이하 | 100 |",
            f"| {score._CLOCK_LOOSE_MINUTES}분 | **{score._REGULARITY_LOOSE_SCORE:g}** ★ |",
            f"| {score._REGULARITY_ZERO_MINUTES:g}분 이상 | 0 |",
            # 안정성
            f"| {score._STABILITY_GOOD_MINUTES:g}분 이하 ★ | 100 |",
            f"| {score._STABILITY_ZERO_MINUTES:g}분 이상 ★ | 0 |",
            # 사회적 시차
            f"| {score._CLOCK_WEEKEND_SHIFT_MINUTES}분 이하 | 100 |",
            f"| {score._JETLAG_ZERO_MINUTES:g}분 이상 ★ | 0 |",
            # 활동·BMI
            f"{score._STEPS_TARGET:,.0f}걸음",
            f"| 운동시간 | {score._EXERCISE_TARGET_MINUTES:g}분 |",
            f"| {score._BMI_GOOD_LOW:g}~{score._BMI_GOOD_HIGH:g} | 100 |",
            f"| {score._BMI_CAUTION_LOW:g} 이하 · {score._BMI_CAUTION_HIGH:g} 이상"
            f" | **{score._BMI_CAUTION_SCORE:g}** ★ |",
            f"주의 경계에서 **{score._BMI_ZERO_MARGIN:g}**만큼 더 벗어남 ★",
        ):
            with self.subTest(text=text):
                self.assertIn(text, self.body)

    def test_the_windows_table_matches_the_code(self) -> None:
        for row in (
            f"| 충분성 | 최근 **{score._DURATION_WINDOW_DAYS}일** ★"
            f" | **{score._DURATION_MIN_DAYS}일** ★ |",
            f"| 규칙성·안정성 | 최근 **{score._SPREAD_WINDOW_DAYS}일** ★"
            f" | **{score._SPREAD_MIN_DAYS}일** ★ |",
            f"| 사회적 시차 | 최근 **{score._SPREAD_WINDOW_DAYS}일** ★"
            f" | 주중 **{score._WEEKDAY_MIN_DAYS}일** + 주말 **{score._WEEKEND_MIN_DAYS}일** ★ |",
            f"| 활동 | 최근 **{score._ACTIVITY_WINDOW_DAYS}일** ★"
            f" | **{score._ACTIVITY_MIN_DAYS}일** ★ |",
            f"| BMI (생활 기록) | **{score._BMI_STALE_DAYS}일** 이내 측정 ★ | 1건 |",
            f"| BMI (건강검진) | **{score._CHECKUP_BMI_STALE_DAYS}일** 이내 측정 ★ | 1건 |",
        ):
            with self.subTest(row=row):
                self.assertIn(row, self.body)

    def test_every_reason_the_code_emits_is_documented(self) -> None:
        """코드가 낼 수 있는 사유가 문서 표에 빠짐없이 있어야 한다."""
        emitted = set(re.findall(r'reasons\.append\("([a-z_]+)"\)',
                                 Path(score.__file__).read_text(encoding="utf-8")))
        emitted.update(re.findall(r'return None, "([a-z_]+)"',
                                  Path(score.__file__).read_text(encoding="utf-8")))
        emitted.add("no_record")
        self.assertTrue(emitted, "사유를 하나도 못 찾았다면 정규식이 코드와 어긋난 것이다")
        for reason in sorted(emitted):
            with self.subTest(reason=reason):
                self.assertIn(f"| `{reason}` |", self.body)

    def test_the_notice_wording_matches_the_service(self) -> None:
        """고지 문구는 사용자가 보는 말이다. 문서에 적힌 그대로 나가야 한다.

        문서는 날짜 자리를 `YYYY년 M월`로 비워 두므로 앞뒤 토막을 나누어 본다.
        """
        head, tail = score.bmi_notice("checkup", "2026-04-02").split("2026년 4월")
        self.assertIn(head.strip(), self.body)
        self.assertIn(tail.strip(), self.body)
        # 생활 기록으로 계산했으면 고지하지 않는다고 문서가 말한다.
        self.assertEqual("", score.bmi_notice("lifestyle", "2026-09-10"))

    def test_the_policy_version_is_named(self) -> None:
        self.assertIn(score.POLICY_VERSION, self.body)


if __name__ == "__main__":
    unittest.main()
