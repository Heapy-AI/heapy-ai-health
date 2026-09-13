"""HEAPY 생활습관 관리 점수 - v2.0 수면점수를 삼성기반이 아니라 heapy 자체 점수로 계산하도록 교체

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

POLICY_VERSION = "heapy-lifestyle-v2"

# 만 20세 미만은 성인 기준을 그대로 대기 어렵다. v1과 같은 판단이다.
_MIN_SUPPORTED_AGE = 20

# ── 총점 가중치 ───────────────────────────────────────────────────────────
# v1이 정한 배분을 그대로 잇는다. 원칙은 '오늘 바꿀 수 있는 것에 무게를 준다'이다.
# 수면과 활동은 어젯밤·오늘 행동으로 움직이지만 BMI는 몇 달이 걸린다. 그래서 BMI는
# 방향만 알려주는 10%다. 어느 문헌도 이 배분을 정해 주지 않는다. 서비스가 정한 값이다.
_WEIGHTS = {"sleep": 0.45, "activity": 0.45, "bmi": 0.10}

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


def calculate(
    window: dict[str, Any],
    age: int | None = None,
    as_of: str = "",
    checkups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """하루치 관리 점수를 낸다.

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


def bmi_score(value: float) -> float:
    """생체 탭의 양호·주의 경계를 그대로 점수로 옮긴다.

    양호 범위 안이면 만점이다. 거기서 주의 경계까지 100→60으로 떨어지고, 그보다 더
    벗어나면 0까지 내려간다. 마른 쪽과 찐 쪽의 주의 폭이 달라 각각의 폭으로 잰다.
    """
    if _BMI_GOOD_LOW <= value <= _BMI_GOOD_HIGH:
        return 100.0
    if value < _BMI_GOOD_LOW:
        good, caution = _BMI_GOOD_LOW, _BMI_CAUTION_LOW
        distance, caution_width = good - value, good - caution
    else:
        good, caution = _BMI_GOOD_HIGH, _BMI_CAUTION_HIGH
        distance, caution_width = value - good, caution - good
    if distance <= caution_width:
        return _interpolate(distance, 0.0, caution_width, 100.0, _BMI_CAUTION_SCORE)
    return _interpolate(distance - caution_width, 0.0, _BMI_ZERO_MARGIN,
                        _BMI_CAUTION_SCORE, 0.0)


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
    """세 성분이 다 서고 결격이 없을 때만 총점을 낸다."""
    complete = not reasons and set(components) == set(_WEIGHTS)
    total = (
        round(sum(components[name]["score"] * _WEIGHTS[name] for name in _WEIGHTS))
        if complete else None
    )
    return {
        "policy_version": POLICY_VERSION,
        "score_date": base,
        "total_score": total,
        "components": components,
        "weights": dict(_WEIGHTS),
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
