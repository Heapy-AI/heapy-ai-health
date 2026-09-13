"""취침·기상 시각을 다루는 공용 도구.

`lifestyle_report`와 `lifestyle_score`가 함께 쓴다. 원래 `lifestyle_report` 안에 있었는데
그 모듈이 최상단에서 langchain을 import해서, 점수 계산만 하려 해도 LLM 의존성이 통째로
딸려왔다. CI의 `tests/internal`은 fastapi와 httpx만 깔고 도는 가벼운 구성이라 그대로는
점수 테스트를 거기 둘 수 없었다. 그래서 표준 라이브러리만 쓰는 이 모듈로 갈라냈다.

시각은 자정에서 되감기는 값이라 보통의 평균·표준편차를 쓰면 틀린다. 23시 50분과
0시 10분의 평균은 12시가 아니라 자정이다. 그래서 각도로 바꿔 단위벡터로 다루는
원형 통계를 쓴다. 이 모듈의 존재 이유가 대부분 거기에 있다.

이름 앞의 밑줄은 `lifestyle_report` 시절 그대로 두었다. 그 모듈 안에서 쓰이는 자리가
많아 이름을 바꾸면 호출부를 전부 손대야 하는데, 옮기는 작업과 이름을 바꾸는 작업을
한 번에 하면 무엇이 깨졌는지 가리기 어려워진다.

작성자: 고수연
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import fmean
from typing import Any

# 기록은 UTC로 저장된다. 취침·기상 시각은 사용자가 사는 시간대로 읽어야 뜻이 통한다.
# 한국 사용자 기준 서비스라 KST로 고정한다. 다른 지역을 지원하게 되면 여기를 바꾼다.
_LOCAL_TIMEZONE = timezone(timedelta(hours=9))

# 취침·기상 시각의 규칙성을 가르는 문턱(분). 원형 표준편차로 잰다.
_CLOCK_STEADY_MINUTES = 30
_CLOCK_LOOSE_MINUTES = 60
# 주중과 주말의 시각 차이를 '다르다'고 볼 문턱(분).
_CLOCK_WEEKEND_SHIFT_MINUTES = 45


def _day(value: Any) -> str:
    """record_date·measured_at·consumed_at을 모두 날짜 10자리로 맞춘다."""
    return str(value or "")[:10]


def _clock_minutes(value: Any) -> float | None:
    """timestamp에서 그날의 몇 분째인지만 꺼낸다. 날짜는 버린다.

    문자열을 잘라 읽으면 안 된다. UTC로 저장된 새벽 1시 20분이 T16:20:00+00:00이라
    그대로 읽으면 오후 4시 20분이 된다. 시각으로 파싱해 지역 시간으로 옮겨야 한다.
    """
    try:
        moment = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    # 시간대가 붙어 있지 않으면 이미 지역 시간으로 적힌 값으로 본다.
    if moment.tzinfo is not None:
        moment = moment.astimezone(_LOCAL_TIMEZONE)
    return moment.hour * 60 + moment.minute


def _clock_stats(minutes: list[float]) -> dict[str, Any] | None:
    """시각의 대표값과 흔들림을 원형 통계로 잰다.

    시각은 자정에서 되감기는 값이라 선형 평균을 쓰면 안 된다. 23시 50분과 0시 10분의
    평균은 12시가 아니라 자정이다. 그래서 각도로 바꿔 단위벡터로 평균을 낸다.
    """
    if len(minutes) < 2:
        return None
    angles = [minute / 1440 * 2 * math.pi for minute in minutes]
    x = fmean(math.cos(angle) for angle in angles)
    y = fmean(math.sin(angle) for angle in angles)
    radius = math.hypot(x, y)
    if radius < 1e-9:
        # 시각이 하루에 고르게 흩어져 대표값을 말할 수 없는 경우다.
        return None
    typical = (math.atan2(y, x) / (2 * math.pi) * 1440) % 1440
    # 원형 표준편차. radius가 1에 가까울수록 시각이 한곳에 모여 있다.
    deviation = 1440 / (2 * math.pi) * math.sqrt(max(-2 * math.log(radius), 0.0))
    return {"typical_minutes": round(typical), "spread_minutes": round(deviation)}


def _clock_text(minutes: float) -> str:
    """분을 오전/오후 표기로 바꾼다. 화면 카드와 같은 형식이다."""
    hour, minute = divmod(int(round(minutes)) % 1440, 60)
    meridiem = "오전" if hour < 12 else "오후"
    display = hour % 12 or 12
    return f"{meridiem} {display}:{minute:02d}"


def _clock_regularity_text(spread: float) -> str:
    if spread <= _CLOCK_STEADY_MINUTES:
        return "일정함"
    return "보통" if spread <= _CLOCK_LOOSE_MINUTES else "들쭉날쭉함"


def _clock_gap(later: float, earlier: float) -> float:
    """두 시각 사이의 최단 거리(분). 자정을 넘어가도 어긋나지 않게 잰다."""
    gap = (later - earlier) % 1440
    return gap - 1440 if gap > 720 else gap
