"""HEAPY 오늘의 건강 종합 점수 - v2.0 수면점수를 삼성기반이 아니라 heapy 자체 점수로 계산하도록 교체

백엔드 Java의 `heapy-lifestyle-v1`을 이 모듈로 옮긴다. 활동과 BMI는 v1의 식을 그대로
잇고, 수면만 바꾼다.

v1의 수면 성분은 수면시간 하나로만 계산했다. 그런데 수면시간은 이미 화면에 항목으로
있어서, 점수로 다시 보여줘도 같은 말을 두 번 하는 셈이었다. 같은 7시간을 자도 매일
같은 시각에 자는 사람과 새벽 1시에 잤다 11시에 잤다 하는 사람은 다른데, 그 차이가
점수에 전혀 드러나지 않았다.

그래서 수면을 네 가지로 가른다.
    충분성      얼마나 잤는가                      (미국수면재단 7~9시간)
    규칙성      늘 같은 시각에 자고 일어나는가      (취침·기상 시각의 원형 표준편차)
    안정성      날마다 수면시간이 들쭉날쭉하지 않은가 (일별 수면시간의 표준편차)
    사회적 시차 주중과 주말의 수면 중점이 어긋나는가 (midsleep 차이)

**삼성헬스의 수면점수(`sleep_score`)와 수면 단계는 쓰지 않는다.** 기기가 자체 기준으로
매긴 값이라 의학 기준이 아니고, 무엇보다 미연동 사용자에게는 없다. 점수에 넣으면
연동자와 미연동자의 점수를 견줄 수 없다. 직접 입력 API가 수면에서 받는 것은
`startAt`·`endAt`·`totalSleepMinutes` 셋뿐이고(백엔드 HealthRecordInput), 위 네 가지는
모두 이 셋만으로 계산된다.

단계와 기기 점수를 버리는 것은 아니다. 생활건강 수면 탭의 항목과 AI 해석 문장에서는
그대로 쓴다. 점수는 사용자 모두에게 같은 기준으로 산출되어야 하므로 고정하며, 설명은 가진 데이터를 다 써도 된다.

계산 결과는 백엔드 `lifestyle_daily_scores` 테이블의 열에 그대로 대응한다. 저장과
배치, 조회는 지금처럼 Spring이 맡고 이 모듈은 계산만 한다.

작성자: 고수연
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean, pstdev
from typing import Any

from app.services.sleep_clock import (
    _CLOCK_LOOSE_MINUTES,
    _CLOCK_STEADY_MINUTES,
    _CLOCK_WEEKEND_SHIFT_MINUTES,
    _clock_gap,
    _clock_minutes,
    _clock_stats,
    _clock_text,
    _day,
)

POLICY_VERSION = "heapy-health-v1"

# 만 20세 미만은 성인 기준을 그대로 대기 어렵다. v1과 같은 판단이다.
_MIN_SUPPORTED_AGE = 20

# ── 총점 가중치 ───────────────────────────────────────────────────────────
# v1이 정한 배분을 그대로 잇는다. 원칙은 '오늘 바꿀 수 있는 것에 무게를 준다'이다.
# 수면과 활동은 어젯밤·오늘 행동으로 움직이지만 BMI는 몇 달이 걸린다. 그래서 BMI는
# 방향만 알려주는 10%다. 어느 문헌도 이 배분을 정해 주지 않는다. 서비스가 정한 값이다.
_WEIGHTS = {"sleep": 0.40, "activity": 0.40, "bmi": 0.10, "metabolic": 0.10}

# 수면·활동·BMI는 없으면 총점을 내지 않는다. 대사는 혈압계·혈당계가 있어야 쌓이는 값이라
# 선택으로 둔다. 없으면 남은 가중치를 다시 정규화한다.
_REQUIRED_COMPONENTS = ("sleep", "activity", "bmi")

# ── 대사 하위 가중치 ──────────────────────────────────────────────────────
# 혈압과 공복혈당은 근거의 두께가 비슷해 반씩 나눈다. 한쪽만 있으면 그쪽만으로 낸다.
_METABOLIC_WEIGHTS = {"blood_pressure": 0.50, "glucose": 0.50}

# ── 수면 하위 가중치 ──────────────────────────────────────────────────────
# 근거가 두꺼운 순서대로 준다. 충분성만 기관 권고(미국수면재단)가 있고 나머지 셋은
# 관찰 연구 수준이다. 이 배분도 서비스가 정한 값이다.
_SLEEP_WEIGHTS = {
    "duration": 0.50,
    "regularity": 0.25,
    "stability": 0.15,
    "social_jetlag": 0.10,
}

# ── 성분별 조회 구간과 최소 기록 일수 ──────────────────────────────────────
# 충분성은 '요즘 얼마나 자는가'라 짧게 본다.
# 8일인 것은 수면 기록이 창 길이만큼 들어오지 않기 때문이다. 분석일 당일 기록이 빠지고,
# 자정을 넘겨 끝난 잠도 cutoff에 걸려 빠진다. 그래서 8일을 잡아야 최근 한 주가 온전히 남는다.
_DURATION_WINDOW_DAYS = 8
_DURATION_MIN_DAYS = 5
# 흔들림을 재는 세 성분은 7일로는 표본이 모자라다. 14일이면 주말도 넉넉히 4일 들어온다.
_SPREAD_WINDOW_DAYS = 14
_SPREAD_MIN_DAYS = 5
_WEEKDAY_MIN_DAYS = 3
_WEEKEND_MIN_DAYS = 2
# 활동은 v1의 14일 중 7일을 그대로 잇는다.
_ACTIVITY_WINDOW_DAYS = 14
_ACTIVITY_MIN_DAYS = 7
# 이보다 오래된 BMI는 지금을 말해 주지 못한다. v1과 같다.
_BMI_STALE_DAYS = 90
# 검진 BMI는 더 오래된 것도 받는다. 국가 건강검진이 연 1회라 90일로 자르면 거의 걸리지
# 않는데, 체중계를 쓰지 않는 사용자에게는 이것이 유일한 측정이다.
_CHECKUP_BMI_STALE_DAYS = 365
# 검진 결과에서 BMI 항목을 찾는 말. 검진 리포트(checkup_report)가 쓰는 것과 같다.
_BMI_ITEM_KEYWORDS = ("bmi", "체질량")

# ── 충분성 ────────────────────────────────────────────────────────────────
# 7~9시간은 미국수면재단 성인 권장이다. 판정기준 문서의 수면시간 항목과 같은 값이다.
_GOOD_HOURS_LOW = 7.0
_GOOD_HOURS_HIGH = 9.0
# 권장을 벗어났을 때 시간당 몇 점을 깎을지는 근거가 없다. 모자란 잠이 더 해롭다고 보아
# 짧은 쪽을 가파르게 깎는다. v1이 정한 기울기를 그대로 잇는다.
_SHORT_PENALTY_PER_HOUR = 25.0
_LONG_PENALTY_PER_HOUR = 15.0

# ── 규칙성 ────────────────────────────────────────────────────────────────
# 30분·60분은 생활건강 탭이 '일정함·보통·들쭉날쭉함'을 가르는 데 이미 쓰는 문턱이라
# 그대로 잇는다. 60분을 60점에 맞추고 120분에서 0점이 되게 두 토막으로 잇는다.
_REGULARITY_LOOSE_SCORE = 60.0
_REGULARITY_ZERO_MINUTES = 120.0

# ── 안정성 ────────────────────────────────────────────────────────────────
# 일별 수면시간의 표준편차. 어느 기관도 문턱을 정해 두지 않아 서비스가 정한 값이다.
_STABILITY_GOOD_MINUTES = 30.0
_STABILITY_ZERO_MINUTES = 90.0

# ── 사회적 시차 ───────────────────────────────────────────────────────────
# 45분은 생활건강 탭이 '주중과 주말이 다르다'고 보는 문턱이라 그대로 쓴다.
_JETLAG_ZERO_MINUTES = 120.0

# ── 활동 ──────────────────────────────────────────────────────────────────
# 8000걸음은 생활건강 탭의 걸음 수 참고범위와 같은 값이다. 운동 30분은 WHO 주 150분을
# 5일로 나눈 값이다. 둘 중 나은 쪽을 쓴다 — 걸어서 채우든 운동으로 채우든 같이 본다.
_STEPS_TARGET = 8000.0
_EXERCISE_TARGET_MINUTES = 30.0

# ── BMI ───────────────────────────────────────────────────────────────────
# 생활건강 생체 탭과 같은 경계를 쓴다. 같은 수치를 한 화면에서는 '주의'라 하고 점수에서는
# 만점으로 치면 사용자가 둘을 견줄 수 없다.
# 양호 18.5~22.9는 대한비만학회 아시아·태평양 기준의 정상 범위다. 23부터 과체중이라
# WHO 서구 기준(25)을 쓰면 안 된다.
_BMI_GOOD_LOW = 18.5
_BMI_GOOD_HIGH = 22.9
_BMI_CAUTION_LOW = 17.0
_BMI_CAUTION_HIGH = 24.9
# 주의 경계에서 몇 점으로 볼지. 규칙성과 같은 방식이다.
_BMI_CAUTION_SCORE = 60.0
# 주의 구간에서 이만큼 더 벗어나면 0점.
_BMI_ZERO_MARGIN = 5.0
# (0점, 주의, 양호, 양호, 주의, 0점) 여섯 점으로 밴드를 적는다.
_BMI_BAND = (_BMI_CAUTION_LOW - _BMI_ZERO_MARGIN, _BMI_CAUTION_LOW,
             _BMI_GOOD_LOW, _BMI_GOOD_HIGH,
             _BMI_CAUTION_HIGH, _BMI_CAUTION_HIGH + _BMI_ZERO_MARGIN)

# ── 대사 (혈압·공복혈당) ──────────────────────────────────────────────────
# 양호·주의 경계는 생활건강 생체 탭과 같다. 0점 자리는 주의 폭만큼 더 벗어난 지점으로
# 잡았는데, 그 결과가 학회의 다음 단계와 거의 맞아떨어진다.
#   수축기 159 · 이완기 99  → 대한고혈압학회 2기 고혈압(160/100)
#   공복혈당 151           → 당뇨 진단 기준(126)을 한참 넘어선 자리
_BP_SYSTOLIC_BAND = (70.0, 80.0, 90.0, 119.0, 139.0, 159.0)
_BP_DIASTOLIC_BAND = (40.0, 50.0, 60.0, 79.0, 89.0, 99.0)
_GLUCOSE_BAND = (50.0, 60.0, 70.0, 99.0, 125.0, 151.0)
# 밴드 밖으로 나갈 때 주의 경계에서 몇 점인지. BMI·규칙성과 같은 60점이다.
_BAND_CAUTION_SCORE = 60.0

# 생활 기록의 대사 수치도 BMI와 같은 유효 기간을 쓴다.
_METABOLIC_STALE_DAYS = _BMI_STALE_DAYS
_CHECKUP_METABOLIC_STALE_DAYS = _CHECKUP_BMI_STALE_DAYS
# 혈압·혈당은 한 번 잰 값으로 등급을 매기지 않는다. 대한고혈압학회 가정혈압 지침도
# 아침·저녁 2회씩 5~7일을 재서 평균하라고 한다. 커피 한 잔, 계단 오르기, 측정 직전의
# 대화로 10~20mmHg가 움직이기 때문이다. 그래서 최근 측정일에서 거슬러 이만큼을 평균한다.
# 지침의 5~7일보다 넉넉히 잡은 것은 사용자가 매일 재지 않아서다. 서비스가 정한 값이다.
_METABOLIC_AVERAGE_DAYS = 30
# 검진 결과에서 항목을 찾는 말. 기관마다 표기가 달라 코드로 고정하지 않는다.
_SYSTOLIC_ITEM_KEYWORDS = ("수축기", "systolic")
_DIASTOLIC_ITEM_KEYWORDS = ("이완기", "diastolic")
# 식후 혈당은 측정 시점이 지켜졌는지 알 수 없어 쓰지 않는다. 공복만 받는다.
_GLUCOSE_ITEM_KEYWORDS = ("공복혈당", "공복 혈당", "fasting glucose")


def calculate(
    window: dict[str, Any],
    age: int | None = None,
    as_of: str = "",
    checkups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """하루치 종합 점수를 낸다.

    `window`는 생활건강 분석이 쓰는 형태 그대로다. `as_of`를 주지 않으면 기록이 있는
    가장 늦은 날을 기준일로 삼는다.

    세 성분(수면·활동·BMI)이 모두 서야 총점을 낸다. 하나라도 비면 `total_score`는
    `None`이고 `reasons`에 이유가 남는다. `lifestyle_daily_scores` 테이블의 제약과
    같은 규칙이다. 다만 수면 **안쪽**의 네 가지는 기록이 모자라면 빼고 남은 가중치를
    다시 정규화한다. 사회적 시차 하나 없다고 점수를 통째로 못 내면 대부분의 사용자가
    점수를 보지 못하기 때문이다.
    """
    reasons: list[str] = []
    if age is None:
        reasons.append("age_unavailable")
    elif age < _MIN_SUPPORTED_AGE:
        reasons.append("age_not_supported")
    if any((window.get(key) or {}).get("truncated") for key in ("sleep", "activity", "exercise", "bio")):
        reasons.append("data_limit_exceeded")

    base = as_of or _latest_date(window)
    if not base:
        return _result(base, {}, reasons + ["no_record"])
    latest = date.fromisoformat(base)

    components: dict[str, Any] = {}
    sleep = _sleep(window, latest)
    if sleep:
        components["sleep"] = sleep
    else:
        reasons.append("sleep_insufficient")

    activity = _activity(window, latest)
    if activity:
        components["activity"] = activity
    else:
        reasons.append("activity_insufficient")

    bmi, bmi_reason = _bmi(window, latest, checkups)
    if bmi:
        components["bmi"] = bmi
    else:
        reasons.append(bmi_reason)

    # 선택 성분이다. 없어도 사유를 남기지 않고 가중치만 다시 나눈다.
    metabolic = _metabolic(window, latest, checkups)
    if metabolic:
        components["metabolic"] = metabolic

    return _result(base, components, reasons)


def calculate_series(
    window: dict[str, Any],
    since: str,
    until: str,
    age: int | None = None,
    checkups: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """기준일을 하루씩 옮겨 가며 계산한다. 배치가 최근 며칠치를 한 번에 채울 때 쓴다."""
    start, end = date.fromisoformat(since), date.fromisoformat(until)
    points = []
    day = start
    while day <= end:
        points.append(calculate(window, age, day.isoformat(), checkups))
        day += timedelta(days=1)
    return points


# ── 수면 ──────────────────────────────────────────────────────────────────

def duration_score(hours: float) -> float:
    """하루치 수면시간(시간)을 0~100으로 옮긴다."""
    if hours < _GOOD_HOURS_LOW:
        return _clamp(100 - (_GOOD_HOURS_LOW - hours) * _SHORT_PENALTY_PER_HOUR)
    if hours > _GOOD_HOURS_HIGH:
        return _clamp(100 - (hours - _GOOD_HOURS_HIGH) * _LONG_PENALTY_PER_HOUR)
    return 100.0


def regularity_score(spread_minutes: float) -> float:
    """시각의 원형 표준편차를 0~100으로 옮긴다.

    30분까지는 만점이다. 거기서 60분까지 100→60으로 떨어지고 120분에서 0이 된다.
    두 토막으로 나눈 것은 '보통'과 '들쭉날쭉함'의 뜻 차이를 점수에도 남기기 위해서다.
    """
    if spread_minutes <= _CLOCK_STEADY_MINUTES:
        return 100.0
    if spread_minutes <= _CLOCK_LOOSE_MINUTES:
        return _interpolate(spread_minutes, _CLOCK_STEADY_MINUTES, _CLOCK_LOOSE_MINUTES,
                            100.0, _REGULARITY_LOOSE_SCORE)
    return _interpolate(spread_minutes, _CLOCK_LOOSE_MINUTES, _REGULARITY_ZERO_MINUTES,
                        _REGULARITY_LOOSE_SCORE, 0.0)


def stability_score(deviation_minutes: float) -> float:
    """일별 수면시간의 표준편차(분)를 0~100으로 옮긴다."""
    return _interpolate(deviation_minutes, _STABILITY_GOOD_MINUTES, _STABILITY_ZERO_MINUTES,
                        100.0, 0.0)


def social_jetlag_score(gap_minutes: float) -> float:
    """주중·주말 수면 중점 차이(분)를 0~100으로 옮긴다. 어느 쪽으로 밀렸는지는 보지 않는다."""
    return _interpolate(abs(gap_minutes), _CLOCK_WEEKEND_SHIFT_MINUTES, _JETLAG_ZERO_MINUTES,
                        100.0, 0.0)


def _sleep(window: dict[str, Any], latest: date) -> dict[str, Any] | None:
    """네 가지를 각각 재고 가중평균한다. 충분성이 없으면 수면 성분 자체를 내지 않는다."""
    marks = _sleep_marks(window)
    recent = _within(marks, latest, _DURATION_WINDOW_DAYS)
    spread = _within(marks, latest, _SPREAD_WINDOW_DAYS)

    hours = [mark["hours"] for mark in recent if mark["hours"] is not None]
    if len(hours) < _DURATION_MIN_DAYS:
        return None

    parts: dict[str, Any] = {
        "duration": {
            "score": round(fmean(duration_score(value) for value in hours), 1),
            "recorded_days": len(hours),
            "mean_hours": round(fmean(hours), 2),
        }
    }
    missing: list[str] = []

    regularity = _regularity(spread)
    if regularity:
        parts["regularity"] = regularity
    else:
        missing.append("regularity")

    minutes = [mark["hours"] * 60 for mark in spread if mark["hours"] is not None]
    if len(minutes) >= _SPREAD_MIN_DAYS:
        deviation = pstdev(minutes)
        parts["stability"] = {
            "score": round(stability_score(deviation), 1),
            "recorded_days": len(minutes),
            "deviation_minutes": round(deviation),
        }
    else:
        missing.append("stability")

    jetlag = _social_jetlag(spread)
    if jetlag:
        parts["social_jetlag"] = jetlag
    else:
        missing.append("social_jetlag")

    filled = sum(_SLEEP_WEIGHTS[name] for name in parts)
    score = sum(parts[name]["score"] * _SLEEP_WEIGHTS[name] for name in parts) / filled
    return {
        "score": round(score, 1),
        "recorded_days": len(hours),
        "required_days": _DURATION_MIN_DAYS,
        "parts": parts,
        "weights": {name: _SLEEP_WEIGHTS[name] for name in parts},
        # 가중치의 몇 할이 실제로 채워졌는지. 1.0이 아니면 일부만 반영한 점수다.
        "coverage": round(filled, 2),
        "missing_parts": missing,
    }


def _sleep_marks(window: dict[str, Any]) -> list[dict[str, Any]]:
    """수면 행을 날짜·수면시간·취침/기상 시각으로 간추린다. 하루에 여럿이면 가장 긴 기록을 쓴다."""
    best: dict[str, dict[str, Any]] = {}
    for row in _rows(window, "sleep"):
        day = _day(row.get("measured_at"))
        if not day:
            continue
        detail = row.get("detail_data") if isinstance(row.get("detail_data"), dict) else {}
        mark = {
            "date": day,
            "hours": _number(row.get("value")),
            "bedtime": _clock_minutes(detail.get("start_at")),
            "waketime": _clock_minutes(detail.get("end_at")),
        }
        kept = best.get(day)
        if kept is None or (mark["hours"] or 0) > (kept["hours"] or 0):
            best[day] = mark
    return [best[day] for day in sorted(best)]


def _regularity(marks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """취침과 기상 시각의 규칙성을 각각 재서 평균한다. 한쪽만 있으면 그 한쪽으로 낸다."""
    scores: list[float] = []
    detail: dict[str, Any] = {}
    for key in ("bedtime", "waketime"):
        minutes = [mark[key] for mark in marks if mark[key] is not None]
        if len(minutes) < _SPREAD_MIN_DAYS:
            continue
        stats = _clock_stats(minutes)
        if not stats:
            continue
        scores.append(regularity_score(stats["spread_minutes"]))
        detail[f"{key}_typical"] = _clock_text(stats["typical_minutes"])
        detail[f"{key}_spread_minutes"] = stats["spread_minutes"]
        detail[f"{key}_days"] = len(minutes)
    if not scores:
        return None
    return {
        "score": round(fmean(scores), 1),
        "recorded_days": max(detail.get("bedtime_days", 0), detail.get("waketime_days", 0)),
        **detail,
    }


def _social_jetlag(marks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """주중과 주말의 수면 중점이 얼마나 어긋나는지.

    사회적 시차는 취침이나 기상 한쪽이 아니라 수면 중점(midsleep)으로 재는 것이 문헌의
    정의다. 늦게 자고 늦게 일어나는 주말을 한 값으로 잡아 준다.
    """
    weekday: list[float] = []
    weekend: list[float] = []
    for mark in marks:
        middle = _midsleep(mark)
        if middle is None:
            continue
        try:
            iso = date.fromisoformat(mark["date"]).isoweekday()
        except ValueError:
            continue
        (weekend if iso >= 6 else weekday).append(middle)
    if len(weekday) < _WEEKDAY_MIN_DAYS or len(weekend) < _WEEKEND_MIN_DAYS:
        return None
    weekday_stats, weekend_stats = _clock_stats(weekday), _clock_stats(weekend)
    if not weekday_stats or not weekend_stats:
        return None
    gap = _clock_gap(weekend_stats["typical_minutes"], weekday_stats["typical_minutes"])
    return {
        "score": round(social_jetlag_score(gap), 1),
        "recorded_days": len(weekday) + len(weekend),
        "gap_minutes": round(gap),
        "weekday_midsleep": _clock_text(weekday_stats["typical_minutes"]),
        "weekend_midsleep": _clock_text(weekend_stats["typical_minutes"]),
    }


def _midsleep(mark: dict[str, Any]) -> float | None:
    """취침과 기상의 한가운데 시각(분). 자정을 넘어가도 앞으로 흐르게 잰다."""
    start, end = mark["bedtime"], mark["waketime"]
    if start is None or end is None:
        return None
    # 잠은 언제나 앞으로 흐른다. 최단 거리가 아니라 순방향 거리를 써야 한다.
    forward = (end - start) % 1440
    if forward == 0:
        return None
    return (start + forward / 2) % 1440


# ── 활동 ──────────────────────────────────────────────────────────────────

def activity_score(steps: float | None, exercise_minutes: float | None) -> float | None:
    """걸음과 운동 중 나은 쪽을 쓴다. 둘 다 없으면 그날은 점수가 없다."""
    scores = []
    if steps is not None:
        scores.append(min(steps / _STEPS_TARGET, 1) * 100)
    if exercise_minutes is not None:
        scores.append(min(exercise_minutes / _EXERCISE_TARGET_MINUTES, 1) * 100)
    return max(scores) if scores else None


def _activity(window: dict[str, Any], latest: date) -> dict[str, Any] | None:
    """걸음과 운동을 날짜별로 합쳐 점수를 내고 14일 평균을 낸다."""
    steps = _daily_sum(window, "activity", "record_date", "steps")
    exercise = _daily_sum(window, "exercise", "record_date", "duration_sec", divisor=60)
    since = (latest - timedelta(days=_ACTIVITY_WINDOW_DAYS - 1)).isoformat()
    end = latest.isoformat()

    scores = []
    for day in sorted(set(steps) | set(exercise)):
        if not since <= day <= end:
            continue
        score = activity_score(steps.get(day), exercise.get(day))
        if score is not None:
            scores.append(score)
    if len(scores) < _ACTIVITY_MIN_DAYS:
        return None
    return {
        "score": round(fmean(scores), 1),
        "recorded_days": len(scores),
        "required_days": _ACTIVITY_MIN_DAYS,
        "steps_target": _STEPS_TARGET,
        "exercise_target_minutes": _EXERCISE_TARGET_MINUTES,
    }


# ── BMI ───────────────────────────────────────────────────────────────────

def bmi_notice(source: str, measured_date: str) -> str:
    """검진 BMI로 계산했을 때 화면에 그대로 내보낼 한 줄.

    문구를 화면이 조립하지 않게 서비스가 만들어 준다. 판정과 표현이 따로 놀기 시작하는
    자리가 여기다. 생활 기록으로 계산했으면 굳이 밝힐 것이 없어 빈 문자열이다.
    """
    if source != "checkup":
        return ""
    try:
        measured = date.fromisoformat(measured_date)
    except ValueError:
        return "체중 기록이 없어 건강검진의 BMI로 계산되었습니다"
    return (f"체중 기록이 없어 {measured.year}년 {measured.month}월 "
            "건강검진의 BMI로 계산되었습니다")


def band_score(value: float, band: tuple[float, ...]) -> float:
    """생체 탭의 양호·주의 경계를 그대로 점수로 옮긴다.

    밴드는 (0점, 주의, 양호, 양호, 주의, 0점) 여섯 점이다. 양호 범위 안이면 만점이고,
    거기서 주의 경계까지 100→60으로 떨어진 뒤 0점 자리까지 더 내려간다. 낮은 쪽과 높은
    쪽의 폭이 항목마다 달라 각각의 폭으로 잰다.
    """
    zero_low, caution_low, good_low, good_high, caution_high, zero_high = band
    if good_low <= value <= good_high:
        return 100.0
    if value < good_low:
        good, caution, zero = good_low, caution_low, zero_low
        distance, caution_width, zero_width = good - value, good - caution, caution - zero
    else:
        good, caution, zero = good_high, caution_high, zero_high
        distance, caution_width, zero_width = value - good, caution - good, zero - caution
    if distance <= caution_width:
        return _interpolate(distance, 0.0, caution_width, 100.0, _BAND_CAUTION_SCORE)
    return _interpolate(distance - caution_width, 0.0, zero_width, _BAND_CAUTION_SCORE, 0.0)


def bmi_score(value: float) -> float:
    """BMI를 0~100으로 옮긴다. 양호 18.5~22.9, 주의 17·24.9."""
    return band_score(value, _BMI_BAND)


def blood_pressure_score(systolic: float, diastolic: float) -> float:
    """수축기와 이완기 중 **나쁜 쪽**으로 정한다.

    대한고혈압학회 기준이 수축기 '또는' 이완기 중 나쁜 쪽으로 등급을 매긴다. 따로 점수를
    내어 평균하면 124/78인 날에 한쪽만 깎여 탭의 판정과 어긋난다.
    """
    return min(band_score(systolic, _BP_SYSTOLIC_BAND),
               band_score(diastolic, _BP_DIASTOLIC_BAND))


def glucose_score(value: float) -> float:
    """공복 혈당을 0~100으로 옮긴다. 양호 70~99, 주의 60·125."""
    return band_score(value, _GLUCOSE_BAND)


def _bmi(window: dict[str, Any], latest: date,
         checkups: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any] | None, str]:
    """기준일까지의 마지막 BMI를 쓴다. 생활 기록에 없으면 건강검진에서 가져온다.

    체중계를 쓰지 않는 사용자는 `lifestyle_bio`에 BMI가 쌓이지 않는다. 그러면 수면과
    활동을 아무리 잘해도 총점이 나오지 않는다. 검진에는 BMI가 반드시 있으므로 이것을
    대체 출처로 쓴다. 대신 어디서 온 값인지 `source`에 남겨 화면이 밝힐 수 있게 한다.

    둘 다 있으면 더 최근 것을 쓴다. 오래되어 쓸 수 없는 값만 있었다면 `bmi_stale`,
    아예 없었다면 `bmi_missing`이다.
    """
    found, usable = False, []
    for day, value in _bio_bmi(window, latest):
        found = True
        if date.fromisoformat(day) >= latest - timedelta(days=_BMI_STALE_DAYS - 1):
            usable.append((day, value, "lifestyle"))
    for day, value in _checkup_bmi(checkups, latest):
        found = True
        if date.fromisoformat(day) >= latest - timedelta(days=_CHECKUP_BMI_STALE_DAYS - 1):
            usable.append((day, value, "checkup"))

    if not usable:
        return None, "bmi_stale" if found else "bmi_missing"
    day, value, source = max(usable)
    return {
        "score": round(bmi_score(value), 1),
        "measured_date": day,
        "value": value,
        "source": source,
        "notice": bmi_notice(source, day),
        "reference": f"{_BMI_GOOD_LOW:g}~{_BMI_GOOD_HIGH:g}",
    }, ""


# ── 대사 ──────────────────────────────────────────────────────────────────

def _metabolic(window: dict[str, Any], latest: date,
               checkups: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """혈압과 공복혈당. 둘 다 없으면 성분 자체를 내지 않는다.

    혈압계·혈당계가 없으면 생활 기록에 쌓이지 않는 값이라 선택 성분이다. 대신 검진에는
    반드시 있으므로 BMI와 같은 방식으로 검진을 대체 출처로 쓴다. 한쪽만 있으면 그쪽만으로
    내고 남은 가중치를 다시 정규화한다.
    """
    parts: dict[str, Any] = {}

    pressure = _measurement_average(_bio_pressure(window, latest),
                                    _checkup_pressure(checkups, latest), latest)
    if pressure:
        day, (systolic, diastolic), source, days = pressure
        parts["blood_pressure"] = {
            "score": round(blood_pressure_score(systolic, diastolic), 1),
            "measured_date": day, "source": source, "recorded_days": days,
            "systolic": round(systolic, 1), "diastolic": round(diastolic, 1),
            "reference": f"{_BP_SYSTOLIC_BAND[2]:g}~{_BP_SYSTOLIC_BAND[3]:g}"
                         f"/{_BP_DIASTOLIC_BAND[2]:g}~{_BP_DIASTOLIC_BAND[3]:g}",
        }

    glucose = _measurement_average(_bio_glucose(window, latest),
                                   _checkup_glucose(checkups, latest), latest)
    if glucose:
        day, value, source, days = glucose
        parts["glucose"] = {
            "score": round(glucose_score(value), 1),
            "measured_date": day, "source": source, "recorded_days": days,
            "value": round(value, 1),
            "reference": f"{_GLUCOSE_BAND[2]:g}~{_GLUCOSE_BAND[3]:g}",
        }

    if not parts:
        return None
    filled = sum(_METABOLIC_WEIGHTS[name] for name in parts)
    score = sum(parts[name]["score"] * _METABOLIC_WEIGHTS[name] for name in parts) / filled
    return {
        "score": round(score, 1),
        "parts": parts,
        "weights": {name: _METABOLIC_WEIGHTS[name] for name in parts},
        "coverage": round(filled, 2),
        "missing_parts": [name for name in _METABOLIC_WEIGHTS if name not in parts],
    }


def _measurement_average(lifestyle: list[tuple[str, Any]], checkup: list[tuple[str, Any]],
                         latest: date) -> tuple[str, Any, str, int] | None:
    """쓸 수 있는 측정을 평균해 하나의 대표값으로 만든다.

    생활 기록이 유효 기간 안에 하나라도 있으면 **생활 기록만** 쓴다. 의료기관 측정과 가정
    측정은 조건이 달라(백의고혈압) 섞어 평균하면 둘 다 아닌 값이 된다.

    돌려주는 것은 (최근 측정일, 대표값, 출처, 평균에 든 날 수)다.
    """
    fresh = [(day, value) for day, value in lifestyle
             if date.fromisoformat(day) >= latest - timedelta(days=_METABOLIC_STALE_DAYS - 1)]
    if fresh:
        days = _daily_means(fresh)
        newest = max(days)
        since = (date.fromisoformat(newest)
                 - timedelta(days=_METABOLIC_AVERAGE_DAYS - 1)).isoformat()
        window = [value for day, value in days.items() if day >= since]
        return newest, _mean_value(window), "lifestyle", len(window)

    # 검진은 회차당 한 번이라 평균할 것이 없다. 가장 최근 회차를 그대로 쓴다.
    usable = [(day, value) for day, value in checkup
              if date.fromisoformat(day)
              >= latest - timedelta(days=_CHECKUP_METABOLIC_STALE_DAYS - 1)]
    if not usable:
        return None
    day, value = max(usable, key=lambda item: item[0])
    return day, value, "checkup", 1


def _daily_means(records: list[tuple[str, Any]]) -> dict[str, Any]:
    """하루에 여러 번 잰 값을 그날 평균으로 묶는다.

    아침에 높고 저녁에 낮은 것이 혈압이다. 한쪽만 집으면 같은 날 기록으로도 점수가
    크게 갈린다. 생활건강 탭이 쓰는 daily='mean'과 같은 규칙이다.
    """
    by_day: dict[str, list[Any]] = {}
    for day, value in records:
        by_day.setdefault(day, []).append(value)
    return {day: _mean_value(values) for day, values in by_day.items()}


def _mean_value(values: list[Any]) -> Any:
    """혈압처럼 두 수치가 한 쌍인 값도 각각 평균한다."""
    if isinstance(values[0], tuple):
        return tuple(fmean(value[index] for value in values)
                     for index in range(len(values[0])))
    return fmean(values)


def _bio_pressure(window: dict[str, Any], latest: date) -> list[tuple[str, tuple[float, float]]]:
    """생활 기록의 혈압. 수축기와 이완기가 한 행에 함께 들어온다."""
    records = []
    for row in _rows(window, "bio"):
        if row.get("bio_type") != "blood_pressure":
            continue
        day = _day(row.get("measured_at"))
        detail = row.get("detail_data") if isinstance(row.get("detail_data"), dict) else {}
        systolic, diastolic = _number(detail.get("systolic")), _number(detail.get("diastolic"))
        if day and systolic and diastolic and day <= latest.isoformat():
            records.append((day, (systolic, diastolic)))
    return records


def _bio_glucose(window: dict[str, Any], latest: date) -> list[tuple[str, float]]:
    """생활 기록의 공복 혈당. 식후 기록은 측정 시점을 믿을 수 없어 쓰지 않는다."""
    records = []
    for row in _rows(window, "bio"):
        if row.get("bio_type") != "blood_glucose":
            continue
        detail = row.get("detail_data") if isinstance(row.get("detail_data"), dict) else {}
        if detail.get("fasting") is not True:
            continue
        day = _day(row.get("measured_at"))
        value = _number(row.get("value"))
        if day and value and day <= latest.isoformat():
            records.append((day, value))
    return records


def _checkup_pressure(checkups: list[dict[str, Any]] | None,
                      latest: date) -> list[tuple[str, tuple[float, float]]]:
    """검진의 혈압. 수축기와 이완기가 따로 적힌 회차만 쓴다."""
    records = []
    for day, results in _checkup_rounds(checkups, latest):
        systolic = _checkup_value(results, _SYSTOLIC_ITEM_KEYWORDS)
        diastolic = _checkup_value(results, _DIASTOLIC_ITEM_KEYWORDS)
        if systolic and diastolic:
            records.append((day, (systolic, diastolic)))
    return records


def _checkup_glucose(checkups: list[dict[str, Any]] | None,
                     latest: date) -> list[tuple[str, float]]:
    records = []
    for day, results in _checkup_rounds(checkups, latest):
        value = _checkup_value(results, _GLUCOSE_ITEM_KEYWORDS)
        if value:
            records.append((day, value))
    return records


def _checkup_rounds(checkups: list[dict[str, Any]] | None,
                    latest: date) -> list[tuple[str, list[dict[str, Any]]]]:
    """기준일까지의 검진 회차만 날짜와 함께 돌려준다."""
    rounds = []
    for checkup in checkups or []:
        day = _day(checkup.get("date"))
        if day and day <= latest.isoformat():
            rounds.append((day, checkup.get("results") or []))
    return rounds


def _checkup_value(results: list[dict[str, Any]], keywords: tuple[str, ...]) -> float | None:
    """검진 결과에서 이름에 이 말이 든 첫 항목의 수치를 꺼낸다."""
    for result in results:
        text = f"{result.get('item_code') or ''} {result.get('item_name') or ''}".casefold()
        if any(keyword in text for keyword in keywords):
            return _number(result.get("value"))
    return None


def _bio_bmi(window: dict[str, Any], latest: date) -> list[tuple[str, float]]:
    """생활 기록의 BMI. 체중계나 체성분계로 잰 값이다."""
    records = []
    for row in _rows(window, "bio"):
        if row.get("bio_type") != "bmi":
            continue
        day = _day(row.get("measured_at"))
        value = _number(row.get("value"))
        if day and value and day <= latest.isoformat():
            records.append((day, value))
    return records


def _checkup_bmi(checkups: list[dict[str, Any]] | None,
                 latest: date) -> list[tuple[str, float]]:
    """검진 회차에서 BMI 항목만 골라낸다. 항목 이름은 기관마다 달라 말로 찾는다."""
    records = []
    for checkup in checkups or []:
        day = _day(checkup.get("date"))
        if not day or day > latest.isoformat():
            continue
        for result in checkup.get("results") or []:
            text = f"{result.get('item_code') or ''} {result.get('item_name') or ''}".casefold()
            if not any(keyword in text for keyword in _BMI_ITEM_KEYWORDS):
                continue
            value = _number(result.get("value"))
            if value:
                records.append((day, value))
                break
    return records


# ── 공통 ──────────────────────────────────────────────────────────────────

def _result(base: str, components: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    """필수 성분이 다 서고 결격이 없을 때 총점을 낸다.

    대사는 선택이라 없어도 총점이 나온다. 그때는 남은 가중치를 다시 정규화한다.
    `coverage`가 1.0이 아니면 일부 성분만 반영한 점수다.
    """
    complete = not reasons and all(name in components for name in _REQUIRED_COMPONENTS)
    filled = sum(_WEIGHTS[name] for name in components if name in _WEIGHTS)
    total = (
        round(sum(components[name]["score"] * _WEIGHTS[name] for name in components) / filled)
        if complete and filled else None
    )
    return {
        "policy_version": POLICY_VERSION,
        "score_date": base,
        "total_score": total,
        "components": components,
        "weights": {name: _WEIGHTS[name] for name in components if name in _WEIGHTS},
        "coverage": round(filled, 2),
        "reasons": reasons,
    }


def _rows(window: dict[str, Any], source: str) -> list[dict[str, Any]]:
    return (window.get(source) or {}).get("rows") or []


def _daily_sum(
    window: dict[str, Any],
    source: str,
    date_key: str,
    value_key: str,
    divisor: float = 1,
) -> dict[str, float]:
    """하루에 여러 건인 누적 항목을 날짜별로 합친다."""
    days: dict[str, float] = {}
    for row in _rows(window, source):
        day = _day(row.get(date_key))
        value = _number(row.get(value_key))
        if not day or value is None:
            continue
        days[day] = days.get(day, 0.0) + value / divisor
    return days


def _latest_date(window: dict[str, Any]) -> str:
    """기록이 있는 가장 늦은 날. 성분마다 갈릴 수 있어 전체에서 가장 늦은 날을 쓴다."""
    days = []
    for source, key in (("sleep", "measured_at"), ("activity", "record_date"),
                        ("exercise", "record_date"), ("bio", "measured_at")):
        days.extend(filter(None, (_day(row.get(key)) for row in _rows(window, source))))
    return max(days, default="")


def _within(marks: list[dict[str, Any]], latest: date, days: int) -> list[dict[str, Any]]:
    """기준일에서 거슬러 days일 안에 든 기록만 고른다."""
    since = (latest - timedelta(days=days - 1)).isoformat()
    return [mark for mark in marks if since <= mark["date"] <= latest.isoformat()]


def _number(value: Any) -> float | None:
    """숫자가 아니거나 음수면 기록이 없는 것으로 본다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value >= 0 else None


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _interpolate(value: float, good: float, zero: float, high: float, low: float) -> float:
    """good 이하면 high, zero 이상이면 low, 사이는 직선으로 잇는다."""
    if value <= good:
        return high
    if value >= zero:
        return low
    return high - (high - low) * (value - good) / (zero - good)
