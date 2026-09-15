"""홈 브리핑의 근거를 검증한다. 작성자: 고수연.

브리핑의 숫자는 모델이 아니라 서비스가 센다. 그 숫자와 화면에 나갈 문자열이 맞는지
여기서 본다. 표준 라이브러리만 쓰므로 CI의 내부 계약 검증에서 그대로 돈다.
"""
import unittest
from datetime import date, timedelta

from app.services import health_briefing as briefing

BASE = date(2026, 9, 14)


def _day(offset: int) -> str:
    return (BASE - timedelta(days=offset)).isoformat()


def _window(**rows) -> dict:
    """비어 있는 창에 필요한 갈래만 채운다."""
    empty = {"rows": [], "truncated": False}
    window = {key: dict(empty) for key in ("sleep", "activity", "exercise", "bio", "food")}
    for key, value in rows.items():
        window[key] = {"rows": value, "truncated": False}
    return window


def _points(plan: dict[str, int | None]) -> list[dict]:
    return [{"score_date": day, "total_score": value} for day, value in plan.items()]


class MetricTest(unittest.TestCase):
    """화면에 그대로 나갈 문자열. 앱이 숫자와 단위를 조립하지 않는다."""

    def test_each_kind_reads_the_way_the_screen_shows_it(self):
        self.assertEqual("7시간 12분", briefing._metric("sleep", 7.2))
        self.assertEqual("45분", briefing._metric("sleep", 0.75))
        self.assertEqual("8시간", briefing._metric("sleep", 8.0))
        self.assertEqual("5,920보", briefing._metric("activity", 5920))
        self.assertEqual("1,850kcal", briefing._metric("nutrition", 1850.4))
        self.assertEqual("62.5kg", briefing._metric("bio", 62.47))
        self.assertEqual("55점", briefing._metric("score", 55))

    def test_change_states_the_direction(self):
        self.assertEqual("+42분", briefing._change("sleep", 7.2, 6.5))
        self.assertEqual("-30분", briefing._change("sleep", 6.5, 7.0))
        self.assertEqual("-2,180보", briefing._change("activity", 5920, 8100))
        self.assertEqual("+3점", briefing._change("score", 58, 55))
        self.assertEqual("-0.4kg", briefing._change("bio", 62.1, 62.5))

    def test_a_difference_too_small_to_name_says_so(self):
        """반올림해서 0이 되는 차이를 '+0분'이라 적으면 변화가 있는 것처럼 읽힌다."""
        self.assertEqual("변화 없음", briefing._change("sleep", 7.0, 7.004))
        self.assertEqual("변화 없음", briefing._change("activity", 5920, 5920))
        self.assertEqual("변화 없음", briefing._change("bio", 62.5, 62.52))


class EvidenceTest(unittest.TestCase):
    def test_gathers_the_last_two_records_of_each_kind(self):
        window = _window(
            sleep=[{"measured_at": _day(1), "value": 6.5},
                   {"measured_at": _day(0), "value": 7.2}],
            activity=[{"record_date": _day(1), "steps": 8100},
                      {"record_date": _day(0), "steps": 5920}])
        facts = briefing.evidence(window, [], _day(0), _day(0))

        self.assertEqual("7시간 12분", facts["sleep"]["metric"])
        self.assertEqual("+42분", facts["sleep"]["change"])
        self.assertEqual("-2,180보", facts["activity"]["change"])
        self.assertEqual(_day(1), facts["activity"]["previous_date"])

    def test_a_kind_without_records_is_left_out(self):
        """자리를 비워 두면 모델이 채우려 든다. 아예 넘기지 않는다."""
        window = _window(activity=[{"record_date": _day(0), "steps": 5920}])
        facts = briefing.evidence(window, [], _day(0), _day(0))

        self.assertEqual(["activity"], list(facts))

    def test_one_record_alone_still_counts(self):
        """오늘 처음 잰 값도 보여 준다. 견줄 것이 없을 뿐이다."""
        window = _window(bio=[{"measured_at": _day(0), "bio_type": "weight", "value": 62.5}])
        facts = briefing.evidence(window, [], _day(0), _day(0))

        self.assertEqual("62.5kg", facts["bio"]["metric"])
        self.assertEqual("", facts["bio"]["change"])
        self.assertIsNone(facts["bio"]["previous"])

    def test_an_old_record_is_used_when_there_is_nothing_newer(self):
        """체중은 매일 재지 않는다. 마지막으로 잰 값을 쓴다."""
        window = _window(bio=[{"measured_at": _day(30), "bio_type": "weight", "value": 62.5}])
        facts = briefing.evidence(window, [], _day(0), _day(0))

        self.assertEqual(_day(30), facts["bio"]["date"])

    def test_readings_on_one_day_are_averaged(self):
        window = _window(bio=[{"measured_at": _day(0), "bio_type": "weight", "value": 62.0},
                              {"measured_at": _day(0), "bio_type": "weight", "value": 63.0}])
        self.assertEqual("62.5kg", briefing.evidence(window, [], _day(0), _day(0))["bio"]["metric"])

    def test_another_bio_type_is_not_mistaken_for_weight(self):
        window = _window(bio=[{"measured_at": _day(0), "bio_type": "bmi", "value": 22.0}])
        self.assertEqual({}, briefing.evidence(window, [], _day(0), _day(0)))

    def test_the_score_follows_its_own_date_limit(self):
        """분석일로 적힌 점수가 곧 오늘의 점수다. 기록 상한과 묶으면 어제 점수가 뜬다."""
        points = _points({_day(1): 55, _day(0): 58})
        facts = briefing.evidence(_window(), points, _day(1), _day(0))

        self.assertEqual(_day(0), facts["score"]["date"])
        self.assertEqual("58점", facts["score"]["metric"])
        self.assertEqual("+3점", facts["score"]["change"])

    def test_days_without_a_total_are_not_compared(self):
        """기록이 모자라 총점이 없는 날은 견줄 값이 아니다."""
        points = _points({_day(2): 55, _day(1): None, _day(0): 58})
        facts = briefing.evidence(_window(), points, _day(0), _day(0))

        self.assertEqual(_day(2), facts["score"]["previous_date"])


class ContractTest(unittest.TestCase):
    def test_the_keys_match_the_output_contract(self):
        """모델이 고를 수 있는 키와 근거를 모으는 키가 같아야 한다."""
        from app.schemas.health_briefing import BriefingSection

        annotation = BriefingSection.model_fields["key"].annotation
        self.assertEqual(set(briefing.KEYS), set(annotation.__args__))

    def test_every_key_has_a_label(self):
        self.assertEqual(set(briefing.KEYS), set(briefing._LABELS))


if __name__ == "__main__":
    unittest.main()
