"""홈 화면 '오늘의 AI 건강 브리핑'의 근거를 모은다. 작성자: 고수연.

브리핑에 나오는 숫자는 전부 여기서 만든다. 모델에게는 말만 맡긴다.

모델이 적은 숫자를 그대로 화면에 내보내면 틀린 값을 사용자가 읽는다. "어제보다 42분 더
잤어요"가 실제로 42분이었는지 아무도 확인하지 못한다. 그래서 숫자는 서비스가 세고, 화면에
나가는 `metric`·`change` 문자열까지 여기서 완성한다. 모델은 그 값을 받아 문장을 쓴다.

표준 라이브러리만 쓴다. `health_score`와 같은 이유다. CI의 내부 계약 검증은 fastapi와
httpx만 설치하고 도는데, 여기에 무거운 의존성이 붙으면 브리핑 근거를 테스트할 수 없다.
"""

from typing import Any

from app.services import health_score as score

# 화면이 아는 다섯 갈래다. 앱의 영역 목록·아이콘·색이 이 키에 붙어 있다.
KEYS = ("score", "sleep", "activity", "nutrition", "bio")

_LABELS = {
    "score": "종합점수",
    "sleep": "수면",
    "activity": "걸음",
    "nutrition": "섭취 열량",
    "bio": "체중",
}


def evidence(window: dict[str, Any], points: list[dict[str, Any]],
             as_of: str, score_date: str) -> dict[str, dict[str, Any]]:
    """다섯 갈래의 최근 값과 그 전 값을 모은다. 기록이 없는 갈래는 넣지 않는다.

    날짜 상한이 둘인 것에 이유가 있다. `as_of`는 원천 기록의 상한으로, 분석일 당일
    기록이 빠지므로 보통 분석일의 전날이다. 반면 `score_date`는 점수의 상한인데, 분석일로
    적힌 점수가 곧 그 전날까지의 기록으로 낸 오늘의 점수다. 둘을 같은 날로 묶으면 홈에
    어제 점수가 뜬다.

    상한에 해당하는 날의 기록이 없으면 그보다 앞의 마지막 기록을 쓴다. 매일 재지 않는
    체중 같은 것을 위해서다.
    """
    daily = {
        "sleep": score._daily_sum(window, "sleep", "measured_at", "value"),
        "activity": score._daily_sum(window, "activity", "record_date", "steps"),
        "nutrition": score._daily_sum(window, "food", "consumed_at", "calories"),
        "bio": _bio_daily(window, "weight"),
        "score": _score_daily(points),
    }
    gathered: dict[str, dict[str, Any]] = {}
    for key in KEYS:
        recent = _last_two(daily[key], score_date if key == "score" else as_of)
        if not recent:
            continue
        (day, value), previous = recent
        gathered[key] = {
            "key": key,
            "label": _LABELS[key],
            "date": day,
            "value": round(value, 2),
            "metric": _metric(key, value),
            "previous_date": previous[0] if previous else "",
            "previous": round(previous[1], 2) if previous else None,
            "change": _change(key, value, previous[1]) if previous else "",
        }
    return gathered


def _score_daily(points: list[dict[str, Any]]) -> dict[str, float]:
    """계열에서 총점이 선 날만 모은다. 총점이 없는 날은 견줄 것이 없다."""
    return {point["score_date"]: float(point["total_score"])
            for point in points if point.get("total_score") is not None}


def _bio_daily(window: dict[str, Any], bio_type: str) -> dict[str, float]:
    """생체 기록 한 종류의 일별 평균. 하루에 여러 번 잰 값을 묶는다."""
    days: dict[str, list[float]] = {}
    for row in score._rows(window, "bio"):
        if row.get("bio_type") != bio_type:
            continue
        day = score._day(row.get("measured_at"))
        value = score._number(row.get("value"))
        if not day or value is None:
            continue
        days.setdefault(day, []).append(value)
    return {day: sum(values) / len(values) for day, values in days.items()}


def _last_two(days: dict[str, float], as_of: str):
    """기준일까지의 마지막 두 기록. 하나뿐이면 앞의 것은 비운다."""
    recent = sorted((day, value) for day, value in days.items() if day <= as_of)
    if not recent:
        return None
    return recent[-1], (recent[-2] if len(recent) > 1 else None)


def _metric(key: str, value: float) -> str:
    """화면에 그대로 나갈 문자열. 앱이 숫자와 단위를 조립하지 않는다."""
    if key == "score":
        return f"{value:.0f}점"
    if key == "sleep":
        return _hours(value * 60)
    if key == "activity":
        return f"{value:,.0f}보"
    if key == "nutrition":
        return f"{value:,.0f}kcal"
    return f"{value:.1f}kg"


def _change(key: str, value: float, previous: float) -> str:
    """직전 기록과의 차이. 방향을 부호로 밝히고 같으면 그렇다고 적는다."""
    gap = value - previous
    if key == "sleep":
        minutes = round(gap * 60)
        return "변화 없음" if not minutes else f"{'+' if minutes > 0 else '-'}{_hours(abs(minutes))}"
    if key == "score":
        points = round(gap)
        return "변화 없음" if not points else f"{points:+.0f}점"
    if key == "bio":
        return "변화 없음" if abs(gap) < 0.05 else f"{gap:+.1f}kg"
    unit = "보" if key == "activity" else "kcal"
    rounded = round(gap)
    return "변화 없음" if not rounded else f"{rounded:+,.0f}{unit}"


def _hours(minutes: float) -> str:
    """분을 '7시간 12분'으로 읽는다. 한 시간이 안 되면 시간 자리를 쓰지 않는다."""
    total = round(minutes)
    hours, rest = divmod(total, 60)
    if not hours:
        return f"{rest}분"
    return f"{hours}시간 {rest}분" if rest else f"{hours}시간"
