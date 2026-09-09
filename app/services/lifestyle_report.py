"""생활건강 탭별 AI 분석 서비스.

탭(생체·활동·영양·수면)마다 항목의 특성이 달라 분석 관점도 달라야 한다. 그래서
항목마다 '어느 쪽이 좋은지'와 참고범위를 들고 있고, 좋고 나쁨 판정은 코드가 규칙으로
계산한다. Gemini에는 계산 결과를 설명하는 일만 맡기고 재판정은 막는다. 검진 리포트
(services/checkup_report.py)가 DB status를 다루는 방식과 같은 원칙이다.

참고범위는 모두 '일반 성인' 기준이며 개인의 성별·나이·활동량을 반영하지 않는다.
기준을 하나로 정하기 어려운 항목(체중, 탄수화물, 지방, 깊은수면)은 일부러 비워
추세만 설명하게 한다. 틀린 판정보다 판단 보류가 낫다.

계산은 정밀하게 하되 프롬프트에는 압축해서 넘긴다. 통계값을 그대로 주면 모델이 그 숫자를
옮겨 적으므로, 서비스가 먼저 자연어 표현(level·frequency·direction·stability)으로 바꾸고
일별 계열은 아예 넘기지 않는다. 전체 계산 결과는 API 응답의 verification.analysis_input에
그대로 남아 개발자 검증 화면에서 확인할 수 있다.

작성자: 고수연
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from statistics import StatisticsError, correlation, fmean, median, pstdev
from time import perf_counter
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import MODEL
from app.schemas.lifestyle_report import LifestyleReportContent
from app.services.prompts import lifestyle_report_v4 as prompt_v4


# 쓰고 있는 프롬프트 판. 이전 판으로 되돌리려면 이 모듈만 바꾸면 된다.
# (v1.0은 출력 계약이 달라 LifestyleReportContentV1을 함께 써야 한다.)
ACTIVE_PROMPT = prompt_v4
PROMPT_VERSION = prompt_v4.VERSION

# 탭별 분석 구간. 화면의 기간 버튼과 무관하게 서비스가 정한다.
#
# full은 흐름을 보기 위한 구간, recent는 요즘을 보기 위한 구간이다. 둘을 함께 넘겨야
# "길게 보면 오르는 중이지만 최근 한 달은 잠잠하다"를 한 번에 말할 수 있다.
#
# 생체만 full이 긴 이유는 측정 주기 때문이다. 체중은 주 2회, 혈압은 주 1회, 혈당은
# 2주에 한 번 재는 것이 흔해서 90일로는 추세를 말할 표본이 모이지 않는다. 나머지 셋은
# 기기·앱이 매일 남기므로 90일이면 충분하고, 더 늘리면 오히려 요즘 습관이 묻힌다.
ANALYSIS_WINDOWS = {
    "bio": {"full": 180, "recent": 30},
    "activity": {"full": 90, "recent": 30},
    "nutrition": {"full": 90, "recent": 30},
    "sleep": {"full": 90, "recent": 30},
}


def analysis_window(domain: str) -> dict[str, int]:
    """탭의 분석 구간. 알 수 없는 탭은 가장 흔한 설정으로 돌려준다."""
    return ANALYSIS_WINDOWS.get(domain, {"full": 90, "recent": 30})


DOMAIN_LABELS = {
    "bio": "생체기록",
    "activity": "활동기록",
    "nutrition": "영양기록",
    "sleep": "수면기록",
}

# 코드가 계산하는 판정값. AI는 이 값을 바꾸지 못한다.
STATUS_GOOD = "양호"
STATUS_CAUTION = "주의"
STATUS_MANAGE = "관리 필요"
STATUS_UNKNOWN = "판단 보류"

# 전·후반을 나눠 비교하려면 양쪽에 최소 2점씩은 있어야 한다.
_MIN_DAYS_FOR_COMPARISON = 4
# 평소와 크게 다른 날을 고를 때 쓰는 표준편차 배수와, 항목당 보고 상한.
_ANOMALY_SIGMA = 2.0
_MAX_ANOMALIES_PER_METRIC = 5
# 구간의 이 비율을 넘게 범위 밖이면 '특정 날의 이상'이 아니라 수준 자체의 문제로 본다.
_CHRONIC_OUT_OF_RANGE_RATIO = 0.5
# 검증 패널에 남기는 계열 길이 상한. 1년 구간이면 일별 점이 너무 많아진다.
_MAX_SERIES_POINTS = 30
# 상관이 높아도 새 이야기가 안 되는 짝. 프롬프트로 "쓰지 마라"고만 하면 모델은
# 눈앞에 있는 재료를 쓴다. 그래서 아예 넘기지 않는다.
_TRIVIAL_CO_MOVEMENTS = {
    # 잠이 길면 점수도 오른다. 견주면 같은 말을 두 번 하게 된다.
    frozenset({"수면시간", "수면점수"}),
    # 총량과 그 구성요소. 같이 움직이는 것이 당연하다.
    frozenset({"수면시간", "깊은수면"}),
    frozenset({"수면시간", "얕은수면"}),
    frozenset({"수면시간", "REM수면"}),
    frozenset({"수면시간", "뒤척임"}),
    # 같은 값을 분과 비중으로 두 번 본 것이다.
    frozenset({"깊은수면", "깊은수면 비중"}),
    frozenset({"REM수면", "REM수면 비중"}),
}

# 같은 탭 안에서 함께 움직인 항목으로 볼 상관계수 문턱과 보고 상한.
_CO_MOVEMENT_THRESHOLD = 0.6
_MAX_CO_MOVEMENTS = 6
# 프롬프트에 예시로 넘기는 이상 지점 수. 날짜 나열을 부르지 않도록 최소로 준다.
_MAX_PROMPT_ANOMALIES = 1
# 기록은 UTC로 저장된다. 취침·기상 시각은 사용자가 사는 시간대로 읽어야 뜻이 통한다.
# 한국 사용자 기준 서비스라 KST로 고정한다. 다른 지역을 지원하게 되면 여기를 바꾼다.
_LOCAL_TIMEZONE = timezone(timedelta(hours=9))

# 취침·기상 시각의 규칙성을 가르는 문턱(분). 원형 표준편차로 잰다.
_CLOCK_STEADY_MINUTES = 30
_CLOCK_LOOSE_MINUTES = 60
# 주중과 주말의 시각 차이를 '다르다'고 볼 문턱(분).
_CLOCK_WEEKEND_SHIFT_MINUTES = 45
# WHO 성인 신체활동 권고. 하루로 나누지 않고 주 단위 그대로 쓴다.
_EXERCISE_WEEKLY_TARGET_MINUTES = 150
# 운동 종류 이름. lifestyle_exercise.exercise_type은 enum이 아니라 자유 문자열이라
# 새 값이 언제든 들어온다. 아는 것만 옮기고 모르는 값은 원문을 그대로 보여 준다.
_EXERCISE_KIND_NAMES = {
    "walking": "걷기",
    "running": "달리기",
    "hiking": "등산",
    "cycling": "자전거",
    "indoor_cycling": "실내 자전거",
    "swimming": "수영",
    "weight_machine": "웨이트",
    "yoga": "요가",
    "pilates": "필라테스",
    "climbing": "클라이밍",
    "badminton": "배드민턴",
    "tennis": "테니스",
    "golf": "골프",
    "dancing": "댄스",
    "treadmill": "러닝머신",
    "elliptical": "일립티컬",
    "stair_climbing": "계단 오르기",
    "other_workout": "기타 운동",
}
# 인사이트에 적을 종류 상한. 다 늘어놓으면 나열이 된다.
_MAX_EXERCISE_KINDS = 3
# 한 종류가 이 비율을 넘게 차지하면 '쏠려 있다'고 본다.
_EXERCISE_DOMINANT_RATIO = 0.6
# 주당 횟수가 달라졌다고 볼 문턱. 표본이 작아 둘을 모두 넘어야 변화로 본다.
_EXERCISE_CHANGE_PER_WEEK = 0.5
_EXERCISE_CHANGE_RATIO = 0.25
# 과거와 견주려면 양쪽 구간에 이만큼은 기록이 있어야 한다.
_EXERCISE_MIN_COMPARE_DAYS = 14
# 주말 실행률이 이만큼(%p) 차이 나야 '주말에 몰린다'고 본다.
_EXERCISE_WEEKEND_GAP = 20


def exercise_kind_name(kind: str) -> str:
    """모르는 종류는 옮기지 않고 원문을 그대로 돌려준다."""
    return _EXERCISE_KIND_NAMES.get(str(kind or "").strip().lower(), str(kind or "").strip())
# 이보다 덜 늦게 자면 굳이 취침을 당기라고 하지 않는다.
_BEDTIME_SHIFT_MINUTES = 15


def _number(value: Any) -> float | None:
    """수치로 쓸 수 있는 값만 float로 바꾼다. 참·거짓과 NaN은 값으로 보지 않는다."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _day(value: Any) -> str:
    """record_date·measured_at·consumed_at을 모두 날짜 10자리로 맞춘다."""
    return str(value or "")[:10]


def _detail(row: dict[str, Any], key: str) -> Any:
    """혈압의 이완기처럼 detail_data에만 담긴 값을 꺼낸다."""
    detail = row.get("detail_data")
    return detail.get(key) if isinstance(detail, dict) else None


def _stage_ratio(part: Any, total_hours: Any) -> float | None:
    """수면 단계를 총 수면 대비 비중(%)으로 바꾼다.

    분수만으로는 좋고 나쁨을 말할 수 없다. 6.5시간 잘 때의 깊은수면 60분(15%)과
    8시간 잘 때의 60분(12.5%)은 다르다. 참고범위도 비중으로만 정의돼 있다.
    """
    minutes = _number(part)
    hours = _number(total_hours)
    if minutes is None or not hours:
        return None
    return minutes / (hours * 60) * 100


def _scaled(value: Any, divisor: float) -> float | None:
    """초를 분으로, 미터를 km로 바꾸는 것처럼 단위만 환산한다."""
    number = _number(value)
    return None if number is None else number / divisor


class _Metric:
    """탭 화면의 세부 항목 하나.

    값 추출·일별 합산 방식과 함께, 좋고 나쁨을 가리는 기준을 들고 있다.

    direction
        higher  채울수록 좋은 항목 (걸음 수, 단백질)
        lower   적을수록 좋은 항목 (나트륨, 뒤척임)
        range   적정 범위가 있는 항목 (BMI, 수면시간, 혈당)
        trend   기준을 하나로 정할 수 없어 추세만 보는 항목 (체중, 지방)
    kind
        measurement  측정 시점의 값. 기록이 없는 날은 측정을 안 한 날이다.
        accumulation 하루 누적량. 기록 누락이 곧 과소 집계로 이어진다.
    caution_low·caution_high
        양호와 관리 필요 사이의 주의 구간 경계. 없으면 참고범위 밖은 모두 관리 필요로 본다.
    """

    def __init__(
        self,
        label: str,
        unit: str,
        source: str,
        date_key: str,
        value: Callable[[dict[str, Any]], Any],
        daily: str = "mean",
        keep: Callable[[dict[str, Any]], bool] | None = None,
        direction: str = "trend",
        kind: str = "measurement",
        low: float | None = None,
        high: float | None = None,
        caution_low: float | None = None,
        caution_high: float | None = None,
    ) -> None:
        self.label = label
        self.unit = unit
        self.source = source
        self.date_key = date_key
        self.value = value
        self.daily = daily
        self.keep = keep
        self.direction = direction
        self.kind = kind
        self.low = low
        self.high = high
        self.caution_low = caution_low
        self.caution_high = caution_high

    def daily_series(self, window: dict[str, Any]) -> list[dict[str, Any]]:
        """일자별 (날짜, 값) 계열을 만든다. 하루에 여러 건이면 daily 규칙으로 합친다."""
        rows = (window.get(self.source) or {}).get("rows") or []
        buckets: dict[str, list[float]] = {}
        for row in rows:
            if self.keep and not self.keep(row):
                continue
            number = _number(self.value(row))
            date = _day(row.get(self.date_key))
            if number is None or not date:
                continue
            buckets.setdefault(date, []).append(number)
        series = []
        for date in sorted(buckets):
            values = buckets[date]
            total = sum(values) if self.daily == "sum" else fmean(values)
            series.append({"date": date, "value": round(total, 2)})
        return series

    @property
    def reference_text(self) -> str:
        """화면과 프롬프트에 함께 쓰는 참고범위 설명."""
        suffix = f" {self.unit}" if self.unit else ""
        if self.direction == "range" and self.low is not None and self.high is not None:
            return f"{self.low}~{self.high}{suffix}"
        if self.direction == "higher" and self.low is not None:
            return f"{self.low}{suffix} 이상"
        if self.direction == "lower" and self.high is not None:
            return f"{self.high}{suffix} 미만"
        return ""

    def status(self, value: float | None) -> str:
        """참고범위와 견줘 양호·주의·관리 필요를 코드가 정한다."""
        if value is None or self.direction == "trend":
            return STATUS_UNKNOWN
        if self.direction == "range":
            if self.low is None or self.high is None:
                return STATUS_UNKNOWN
            if self.low <= value <= self.high:
                return STATUS_GOOD
            below = self.caution_low is not None and self.caution_low <= value < self.low
            above = self.caution_high is not None and self.high < value <= self.caution_high
            return STATUS_CAUTION if below or above else STATUS_MANAGE
        if self.direction == "higher":
            if self.low is None:
                return STATUS_UNKNOWN
            if value >= self.low:
                return STATUS_GOOD
            if self.caution_low is not None and value >= self.caution_low:
                return STATUS_CAUTION
            return STATUS_MANAGE
        if self.direction == "lower":
            if self.high is None:
                return STATUS_UNKNOWN
            if value <= self.high:
                return STATUS_GOOD
            if self.caution_high is not None and value <= self.caution_high:
                return STATUS_CAUTION
            return STATUS_MANAGE
        return STATUS_UNKNOWN


def _bio(type_name: str, value: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    """lifestyle_bio에서 한 종류만 골라 읽는 항목의 공통 설정."""
    return {
        "source": "bio",
        "date_key": "measured_at",
        "daily": "mean",
        "kind": "measurement",
        "keep": lambda row: row.get("bio_type") == type_name,
        "value": value,
    }


def _daily_sum(source: str, date_key: str, value: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    """하루 누적으로 합산하는 항목의 공통 설정."""
    return {
        "source": source,
        "date_key": date_key,
        "daily": "sum",
        "kind": "accumulation",
        "value": value,
    }


# 단위 환산은 화면(app.js)·프롬프트 포맷(supabase_lifestyle_context)과 같게 맞춘다.
# lifestyle_activity.distance_m은 km로, lifestyle_exercise.distance_m은 m로 적재된다.
#
# 참고범위 근거(모두 일반 성인 기준):
#   BMI            대한비만학회 아시아·태평양 기준. 정상 18.5~22.9, 과체중 23~24.9
#   혈압           대한고혈압학회. 정상 120/80 미만, 고혈압 전단계 120~139 / 80~89
#   혈당           대한당뇨병학회. 공복 정상 70~99, 공복혈당장애 100~125 / 식후 2시간 140 미만
#   심박수         안정시 정상 60~100회
#   걸음·운동시간  WHO 신체활동 권고(주 150분 중강도) 및 국내 걷기 권고 8,000걸음
#   영양소         2020 한국인 영양소 섭취기준, WHO 나트륨 2g·당류 50g 권고
#   수면           미국수면재단 성인 권장 7~9시간
_DOMAIN_METRICS: dict[str, list[_Metric]] = {
    "bio": [
        # 체중은 키·체성분에 따라 적정값이 달라 절대 기준을 두지 않는다. BMI로만 판정한다.
        _Metric("체중", "kg", **_bio("weight", lambda row: row.get("value")), direction="trend"),
        _Metric("BMI", "", **_bio("bmi", lambda row: row.get("value")),
                direction="range", low=18.5, high=22.9, caution_low=17.0, caution_high=24.9),
        _Metric("수축기 혈압", "mmHg", **_bio("blood_pressure", lambda row: _detail(row, "systolic")),
                direction="range", low=90, high=119, caution_low=80, caution_high=139),
        _Metric("이완기 혈압", "mmHg", **_bio("blood_pressure", lambda row: _detail(row, "diastolic")),
                direction="range", low=60, high=79, caution_low=50, caution_high=89),
        _Metric(
            "공복 혈당", "mg/dL", source="bio", date_key="measured_at", daily="mean", kind="measurement",
            keep=lambda row: row.get("bio_type") == "blood_glucose" and _detail(row, "fasting") is True,
            value=lambda row: row.get("value"),
            direction="range", low=70, high=99, caution_low=60, caution_high=125,
        ),
        _Metric(
            "식후 혈당", "mg/dL", source="bio", date_key="measured_at", daily="mean", kind="measurement",
            keep=lambda row: row.get("bio_type") == "blood_glucose" and _detail(row, "fasting") is not True,
            value=lambda row: row.get("value"),
            direction="range", low=70, high=139, caution_low=60, caution_high=199,
        ),
        _Metric("심박수", "bpm", **_bio("heart_rate", lambda row: row.get("value")),
                direction="range", low=60, high=100, caution_low=50, caution_high=110),
    ],
    "activity": [
        _Metric("걸음 수", "걸음", **_daily_sum("activity", "record_date", lambda row: row.get("steps")),
                direction="higher", low=8000, caution_low=5000),
        # 계단·활동시간·이동거리는 걸음 수를 따라 움직여 새 이야기가 되지 않아 뺐다.
        # 조회는 그대로 하므로 검증 패널과 챗봇 문맥에는 남아 있다.
        _Metric("활동칼로리", "kcal", **_daily_sum("activity", "record_date", lambda row: row.get("active_calories"))),
        # 참고범위를 두지 않는다. 이 계열에는 운동한 날만 점이 있어서 하루 기준으로
        # 재면 "운동한 날에 얼마나 오래 했나"를 묻게 된다. 주 150분 권고는 빈도까지
        # 함께 봐야 뜻이 서므로 _exercise_habit이 따로 잰다.
        _Metric("운동시간", "분", **_daily_sum("exercise", "record_date", lambda row: _scaled(row.get("duration_sec"), 60))),
        _Metric("운동거리", "km", **_daily_sum("exercise", "record_date", lambda row: _scaled(row.get("distance_m"), 1000))),
        _Metric("운동칼로리", "kcal", **_daily_sum("exercise", "record_date", lambda row: row.get("calories"))),
    ],
    "nutrition": [
        _Metric("섭취칼로리", "kcal", **_daily_sum("food", "consumed_at", lambda row: row.get("calories")),
                direction="range", low=1800, high=2400, caution_low=1400, caution_high=2800),
        # 탄수화물·지방은 총열량 대비 비율로 보는 영양소라 절대량 기준을 두지 않는다.
        _Metric("탄수화물", "g", **_daily_sum("food", "consumed_at", lambda row: row.get("carbohydrate"))),
        _Metric("단백질", "g", **_daily_sum("food", "consumed_at", lambda row: row.get("protein")),
                direction="higher", low=50, caution_low=40),
        _Metric("지방", "g", **_daily_sum("food", "consumed_at", lambda row: row.get("total_fat"))),
        _Metric("나트륨", "mg", **_daily_sum("food", "consumed_at", lambda row: row.get("sodium")),
                direction="lower", high=2000, caution_high=3000),
        _Metric("당", "g", **_daily_sum("food", "consumed_at", lambda row: row.get("sugar")),
                direction="lower", high=50, caution_high=75),
        _Metric("수분 섭취", "mL", **_daily_sum("water", "consumed_at", lambda row: row.get("water_amount")),
                direction="higher", low=1500, caution_low=1000),
    ],
    "sleep": [
        _Metric("수면시간", "시간", **_daily_sum("sleep", "measured_at", lambda row: row.get("value")),
                direction="range", low=7, high=9, caution_low=6, caution_high=10),
        # 수면점수는 기기 제조사 자체 기준이라 의학적 참고범위가 아니다.
        # 하루에 한 번 매겨지는 값이라 합산하지 않고 평균으로 본다.
        _Metric("수면점수", "점", source="sleep", date_key="measured_at", daily="mean", kind="measurement",
                value=lambda row: _detail(row, "sleep_score"),
                direction="higher", low=80, caution_low=60),
        # 수면 단계 셋은 총 수면시간 대비 비율로 보는 값이라 절대 분수 기준을 두지 않는다.
        # 같은 7시간을 자도 어떻게 나뉘었는지가 수면점수의 차이를 설명한다.
        _Metric("깊은수면", "분", **_daily_sum("sleep", "measured_at", lambda row: _detail(row, "deep_sleep_minutes"))),
        _Metric("얕은수면", "분", **_daily_sum("sleep", "measured_at", lambda row: _detail(row, "light_sleep_minutes"))),
        _Metric("REM수면", "분", **_daily_sum("sleep", "measured_at", lambda row: _detail(row, "rem_sleep_minutes"))),
        _Metric("뒤척임", "분", **_daily_sum("sleep", "measured_at", lambda row: _detail(row, "awake_minutes")),
                direction="lower", high=30, caution_high=60),
        # 단계는 비중으로 봐야 판정이 선다. 화면의 표·그래프는 분으로 두고 여기서만 비중을 본다.
        # 참고범위는 일반 성인 기준이며 기기마다 단계 판정 알고리즘이 달라 편차가 있다.
        _Metric("깊은수면 비중", "%", source="sleep", date_key="measured_at", daily="mean",
                kind="measurement",
                value=lambda row: _stage_ratio(_detail(row, "deep_sleep_minutes"), row.get("value")),
                direction="range", low=13, high=23, caution_low=10, caution_high=27),
        _Metric("REM수면 비중", "%", source="sleep", date_key="measured_at", daily="mean",
                kind="measurement",
                value=lambda row: _stage_ratio(_detail(row, "rem_sleep_minutes"), row.get("value")),
                direction="range", low=20, high=25, caution_low=15, caution_high=30),
    ],
}


def _level_text(status: str) -> str:
    """판정을 사용자에게 그대로 읽어 줄 수 있는 말로 바꾼다."""
    return {
        STATUS_GOOD: "기준 범위 안",
        STATUS_CAUTION: "기준을 조금 벗어남",
        STATUS_MANAGE: "기준을 크게 벗어남",
        STATUS_UNKNOWN: "기준 없음",
    }.get(status, "기준 없음")


def _frequency_text(out_of_range: int, days: int) -> str:
    """기준을 벗어난 일이 얼마나 잦았는지. 한 번과 반복은 뜻이 다르다."""
    if not days or not out_of_range:
        return "없음"
    ratio = out_of_range / days
    if ratio >= 0.8:
        return "거의 매번"
    if ratio >= 0.5:
        return "대부분의 날"
    if ratio >= 0.2:
        return "절반 이하의 날"
    return "가끔"


def _direction_text(
    change: float | None,
    change_rate: float | None,
    deviation: float,
    direction: str,
) -> str:
    """변화의 방향과 세기. 정확한 증감량 대신 이 표현을 쓰게 한다.

    의미 있는 변화 폭은 항목마다 다르다. 체중은 한 달에 1%만 움직여도 흐름이지만
    걸음 수의 1%는 잡음이다. 그래서 고정 비율 대신 두 잣대를 함께 본다. 제 수준
    대비 얼마나 움직였는지(change_rate)와, 제 평소 흔들림 대비 얼마나 벗어났는지
    (change/표준편차)가 모두 서야 흐름으로 인정한다.
    """
    if change is None or change_rate is None:
        return "판단하기 이름"
    magnitude = abs(change_rate)
    # 표준편차가 0이면 값이 내내 같았다는 뜻이라 흔들림 잣대를 적용할 것이 없다.
    effect = abs(change) / deviation if deviation > 0 else 0.0
    if magnitude < 1 or effect < 0.6:
        return "큰 변화 없음"
    rising = change > 0
    strong = magnitude >= 8 and effect >= 1.0
    if direction == "trend":
        return f"{'뚜렷하게' if strong else '조금씩'} {'오르는' if rising else '내려가는'} 흐름"
    return f"{'뚜렷하게' if strong else '조금씩'} {'높아지는' if rising else '낮아지는'} 흐름"


def _stability_text(cv: float | None) -> str:
    """날마다 들쭉날쭉했는지. 활동·수면에서는 평균보다 이쪽이 중요하다."""
    if cv is None:
        return ""
    if cv < 15:
        return "안정적"
    if cv < 30:
        return "보통"
    return "날마다 편차가 큼"


def _confidence_text(metric: _Metric, days: int, coverage: float) -> str:
    """추세를 말해도 되는지. 측정형은 횟수로, 누적형은 기록률로 본다."""
    if days < _MIN_DAYS_FOR_COMPARISON:
        return "부족"
    if metric.kind == "accumulation":
        return "부족" if coverage < 0.3 else "보통" if coverage < 0.6 else "충분"
    return "보통" if days < 8 else "충분"


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


def _weekly_pattern_text(series: list[dict[str, Any]]) -> str:
    """주중과 주말이 다른지 한마디로 돌려준다.

    잠은 주말에 몰아 자고 활동은 주말에 줄기 쉽다. 그런 규칙성은 전체 평균만 봐서는
    보이지 않는다. 다만 양쪽에 이틀씩은 있어야 비교할 값이 된다.
    """
    weekday, weekend = [], []
    for point in series:
        try:
            iso = date.fromisoformat(point["date"]).isoweekday()
        except ValueError:
            continue
        (weekend if iso >= 6 else weekday).append(point["value"])
    if len(weekday) < 2 or len(weekend) < 2:
        return "판단하기 이름"

    weekday_mean, weekend_mean = fmean(weekday), fmean(weekend)
    gap = weekend_mean - weekday_mean
    values = weekday + weekend
    deviation = pstdev(values) if len(values) > 1 else 0.0
    # 방향을 잴 때와 같은 잣대다. 제 수준 대비와 평소 흔들림 대비가 모두 서야 차이로 본다.
    magnitude = abs(gap) / abs(weekday_mean) * 100 if weekday_mean else 0.0
    effect = abs(gap) / deviation if deviation > 0 else 0.0
    if magnitude < 5 or effect < 0.5:
        return "주중과 주말이 비슷함"
    return "주말이 더 높음" if gap > 0 else "주말이 더 낮음"


def _longest_out_of_range_run(metric: _Metric, series: list[dict[str, Any]]) -> int:
    """기준을 벗어난 기록이 연달아 몇 번 이어졌는지. 반복성을 말할 근거가 된다."""
    longest = current = 0
    for point in series:
        if metric.status(point["value"]) in {STATUS_CAUTION, STATUS_MANAGE}:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _sleep_timing(window: dict[str, Any], target_hours: float | None = None) -> dict[str, Any] | None:
    """취침·기상 시각의 규칙성과 주중·주말 차이를 정리한다.

    잠의 길이만 봐서는 안 보이는 것이 있다. 같은 7시간을 자도 매일 같은 시각에 자는
    사람과 새벽 1시에 잤다 11시에 잤다 하는 사람은 다르다. 그 차이를 여기서 잰다.
    """
    rows = (window.get("sleep") or {}).get("rows") or []
    marks: list[tuple[int, float | None, float | None]] = []
    for row in rows:
        detail = row.get("detail_data") if isinstance(row.get("detail_data"), dict) else {}
        start = _clock_minutes(detail.get("start_at"))
        end = _clock_minutes(detail.get("end_at"))
        if start is None and end is None:
            continue
        try:
            weekday = date.fromisoformat(_day(row.get("measured_at"))).isoweekday()
        except ValueError:
            continue
        marks.append((weekday, start, end))
    if len(marks) < _MIN_DAYS_FOR_COMPARISON:
        return None

    summary: dict[str, Any] = {"days": len(marks)}
    typical: dict[str, float] = {}
    for key, label, index in (("bedtime", "취침", 1), ("waketime", "기상", 2)):
        minutes = [mark[index] for mark in marks if mark[index] is not None]
        stats = _clock_stats(minutes)
        if not stats:
            continue
        typical[key] = stats["typical_minutes"]
        summary[f"{key}_typical"] = _clock_text(stats["typical_minutes"])
        summary[f"{key}_regularity"] = _clock_regularity_text(stats["spread_minutes"])
        # 주중과 주말은 시각이 갈리기 쉽다. 양쪽에 이틀씩은 있어야 견줄 값이 된다.
        weekday_stats = _clock_stats([mark[index] for mark in marks
                                      if mark[0] <= 5 and mark[index] is not None])
        weekend_stats = _clock_stats([mark[index] for mark in marks
                                      if mark[0] >= 6 and mark[index] is not None])
        if not weekday_stats or not weekend_stats:
            continue
        gap = _clock_gap(weekend_stats["typical_minutes"], weekday_stats["typical_minutes"])
        if abs(gap) < _CLOCK_WEEKEND_SHIFT_MINUTES:
            summary[f"{key}_weekend"] = f"주중과 주말의 {label} 시각이 비슷함"
        else:
            summary[f"{key}_weekend"] = (
                f"주말에 {label}이 {'늦어짐' if gap > 0 else '빨라짐'}"
            )

    # 기상 시각이 일정한 사람에게는 "몇 시에 자면 되는지"가 가장 손에 잡히는 조언이다.
    # 기상은 그대로 두고 취침만 당기면 되므로 목표 시각을 계산해 넘긴다.
    if target_hours and "waketime" in typical:
        target = (typical["waketime"] - target_hours * 60) % 1440
        summary["bedtime_target"] = _clock_text(target)
        summary["bedtime_target_basis"] = (
            f"지금 기상 시각을 그대로 두고 {target_hours:g}시간을 자려면"
        )
        if "bedtime" in typical:
            # 목표보다 얼마나 늦게 잠드는지. 5분 단위로 뭉뚱그려 어림수로 말하게 한다.
            late = _clock_gap(typical["bedtime"], target)
            summary["bedtime_shift"] = (
                f"지금보다 {round(late / 5) * 5}분쯤 일찍" if late >= _BEDTIME_SHIFT_MINUTES
                else "지금 취침 시각으로도 닿는다"
            )
    return summary if len(summary) > 1 else None


def _sleep_target_hours() -> float | None:
    """권장 수면시간. 항목 정의에서 가져와 두 곳에 적히지 않게 한다."""
    for metric in _DOMAIN_METRICS.get("sleep", []):
        if metric.label == "수면시간":
            return metric.low
    return None


def _exercise_rate(days: list[str], minutes_by_day: dict[str, float]) -> dict[str, float]:
    """구간 하나의 주당 횟수와 주말 실행률. 달력 날짜로 나눠야 '얼마나 자주'가 된다."""
    weekend = [day for day in days if date.fromisoformat(day).isoweekday() >= 6]
    done = [day for day in days if day in minutes_by_day]
    return {
        "per_week": len(done) / (len(days) / 7),
        "weekend_ratio": (
            len([day for day in weekend if day in minutes_by_day]) / len(weekend) * 100
            if weekend else 0.0
        ),
        "weekend_days": len(weekend),
    }


def _exercise_habit(window: dict[str, Any], recent_days: int = 30) -> dict[str, Any] | None:
    """운동을 활동과 갈라 '얼마나 자주, 한 번에 얼마나' 하는지 정리한다.

    운동은 매일 하는 것이 아니라서 하루 평균으로는 뜻이 서지 않는다. 한 번에 40분씩
    하더라도 한 달에 두 번이면 권고에 한참 못 미친다. 그 둘을 갈라서 넘긴다.
    """
    days = sorted({_day(row.get("record_date")) for row in (window.get("activity") or {}).get("rows") or []})
    days = [day for day in days if day]
    minutes_by_day: dict[str, float] = {}
    kinds: dict[str, int] = {}
    for row in (window.get("exercise") or {}).get("rows") or []:
        day = _day(row.get("record_date"))
        value = _scaled(row.get("duration_sec"), 60)
        if not day or value is None:
            continue
        minutes_by_day[day] = minutes_by_day.get(day, 0.0) + value
        kind = str(row.get("exercise_type") or "").strip()
        if kind:
            kinds[kind] = kinds.get(kind, 0) + 1
    if len(days) < _MIN_DAYS_FOR_COMPARISON or not minutes_by_day:
        return None

    summary: dict[str, Any] = {"days": len(days), "exercise_days": len(minutes_by_day)}
    # 무엇을 하고 있는지. 종류마다 몸에 남는 것이 달라 횟수만큼이나 알 만한 값이다.
    if kinds:
        ranked = sorted(kinds.items(), key=lambda item: (-item[1], item[0]))
        shown = ", ".join(f"{exercise_kind_name(kind)} {count}회"
                          for kind, count in ranked[:_MAX_EXERCISE_KINDS])
        rest = len(ranked) - _MAX_EXERCISE_KINDS
        summary["kinds"] = f"{shown} 외 {rest}가지" if rest > 0 else shown
        # 한 가지에 쏠렸는지, 골고루 하는지. 종류 수만 세면 쏠림이 안 보인다.
        top = ranked[0][1] / sum(kinds.values())
        summary["variety"] = (
            f"{exercise_kind_name(ranked[0][0])} 한 가지에 쏠려 있다" if top >= _EXERCISE_DOMINANT_RATIO
            else f"{len(ranked)}가지를 섞어서 한다"
        )
    # 한 달에 몇 번인지가 사용자가 가장 쉽게 헤아리는 단위다.
    per_month = len(minutes_by_day) / len(days) * 30
    summary["frequency"] = f"한 달에 {round(per_month)}번쯤"
    typical = median(list(minutes_by_day.values()))
    summary["session"] = f"한 번에 {round(typical / 5) * 5:g}분쯤"

    # 권고는 주 단위다. 기록된 기간을 주로 환산해 주당 총 운동시간을 낸다.
    weekly = sum(minutes_by_day.values()) / (len(days) / 7)
    summary["weekly_total"] = f"주당 {round(weekly / 5) * 5:g}분쯤"
    if weekly >= _EXERCISE_WEEKLY_TARGET_MINUTES:
        summary["guideline"] = f"권고(주 {_EXERCISE_WEEKLY_TARGET_MINUTES}분)를 채우고 있다"
    else:
        summary["guideline"] = f"권고(주 {_EXERCISE_WEEKLY_TARGET_MINUTES}분)에 못 미친다"
        # 길이가 아니라 횟수로 좁혀야 손에 잡히는 조언이 된다. 몇 번 더인지 계산해 준다.
        if typical > 0:
            more = math.ceil((_EXERCISE_WEEKLY_TARGET_MINUTES - weekly) / typical)
            summary["shortfall"] = f"지금 길이 그대로 주 {more}번쯤 더 하면 닿는다"

    whole = _exercise_rate(days, minutes_by_day)
    if whole["weekend_days"] >= _MIN_DAYS_FOR_COMPARISON:
        # 주말은 시간을 내기 쉬운 날이라, 남는 여지가 어디인지 알려 준다.
        weekday_ratio = (
            (len(minutes_by_day) - len([d for d in days
                                        if d in minutes_by_day
                                        and date.fromisoformat(d).isoweekday() >= 6]))
            / max(len(days) - whole["weekend_days"], 1) * 100
        )
        gap = whole["weekend_ratio"] - weekday_ratio
        if gap >= _EXERCISE_WEEKEND_GAP:
            summary["weekend_habit"] = (
                f"주말에 몰려 있다 (주말 {whole['weekend_ratio']:.0f}% · 주중 {weekday_ratio:.0f}%)"
            )
        elif gap <= -_EXERCISE_WEEKEND_GAP:
            summary["weekend_habit"] = (
                f"주중에 몰려 있다 (주중 {weekday_ratio:.0f}% · 주말 {whole['weekend_ratio']:.0f}%)"
            )

    # 과거와 견준다. 지금이 예전보다 나은지 아닌지가 가장 알고 싶은 것이다.
    cut = str(date.fromisoformat(days[-1]) - timedelta(days=recent_days))
    recent = [day for day in days if day > cut]
    earlier = [day for day in days if day <= cut]
    if min(len(recent), len(earlier)) >= _EXERCISE_MIN_COMPARE_DAYS:
        now, before = _exercise_rate(recent, minutes_by_day), _exercise_rate(earlier, minutes_by_day)
        gap = now["per_week"] - before["per_week"]
        moved = (
            abs(gap) >= _EXERCISE_CHANGE_PER_WEEK
            and before["per_week"] > 0
            and abs(gap) / before["per_week"] >= _EXERCISE_CHANGE_RATIO
        )
        if moved:
            summary["change"] = (
                f"예전 주 {before['per_week']:.1f}번에서 요즘 주 {now['per_week']:.1f}번으로 "
                f"{'늘었다' if gap > 0 else '줄었다'}"
            )
        else:
            # 안 변한 것도 알려야 한다. 아니면 모델이 다른 신호에서 변화를 지어낸다.
            summary["change"] = f"주 {now['per_week']:.1f}번쯤으로 예전과 비슷하다"
    return summary


def _co_movements(pairs: list[tuple[_Metric, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    """같은 탭 안에서 함께 움직인 항목 짝을 찾는다.

    탭별 독립 분석이라 다른 탭과는 엮지 않는다. 대신 이 탭 안의 관계는 사용자가
    가장 이해하기 쉬운 이야기라 적극적으로 찾아 넘긴다. 인과가 아니라 동행이다.
    """
    found = []
    for index, (left, left_series) in enumerate(pairs):
        left_values = {point["date"]: point["value"] for point in left_series}
        for right, right_series in pairs[index + 1:]:
            shared = [(left_values[point["date"]], point["value"])
                      for point in right_series if point["date"] in left_values]
            if len(shared) < _MIN_DAYS_FOR_COMPARISON:
                continue
            try:
                coefficient = correlation([pair[0] for pair in shared], [pair[1] for pair in shared])
            except StatisticsError:
                # 한쪽 값이 내내 같으면 상관을 정의할 수 없다.
                continue
            if abs(coefficient) < _CO_MOVEMENT_THRESHOLD:
                continue
            if frozenset({left.label, right.label}) in _TRIVIAL_CO_MOVEMENTS:
                continue
            found.append({
                "metrics": [left.label, right.label],
                "relation": "같은 방향으로 움직임" if coefficient > 0 else "반대 방향으로 움직임",
                "shared_days": len(shared),
                "coefficient": round(coefficient, 2),
            })
    found.sort(key=lambda item: abs(item["coefficient"]), reverse=True)
    return found[:_MAX_CO_MOVEMENTS]


def _downsample(series: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """긴 계열을 처음과 끝을 남기고 균등하게 솎아 프롬프트 길이를 억제한다."""
    if len(series) <= limit:
        return series
    step = (len(series) - 1) / (limit - 1)
    indexes = sorted({round(index * step) for index in range(limit)} | {0, len(series) - 1})
    return [series[index] for index in indexes]


def _find_anomalies(metric: _Metric, series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """참고범위를 벗어났거나 평소와 크게 달랐던 날을 찾는다.

    늘 범위 밖에 있는 항목은 '특정 날의 이상'이 아니라 수준 자체의 문제이므로, 같은
    날을 여러 건 늘어놓지 않고 가장 심한 하루만 예시로 남긴다. 나머지는 항목의
    out_of_range_days가 대신 말해 준다.
    """
    values = [point["value"] for point in series]
    average = fmean(values)
    deviation = pstdev(values) if len(values) > 1 else 0.0
    out_of_range = sum(1 for value in values if metric.status(value) in {STATUS_CAUTION, STATUS_MANAGE})
    is_chronic = out_of_range > len(values) * _CHRONIC_OUT_OF_RANGE_RATIO

    found = []
    for point in series:
        status = metric.status(point["value"])
        reasons = []
        if status in {STATUS_CAUTION, STATUS_MANAGE}:
            reasons.append(f"참고범위({metric.reference_text}) 밖")
        # 표준편차가 0이면 모든 날이 같은 값이라 '평소와 다른 날'이 없다.
        gap = abs(point["value"] - average)
        if len(values) >= _MIN_DAYS_FOR_COMPARISON and deviation > 0 and gap > _ANOMALY_SIGMA * deviation:
            reasons.append("구간 평균과 크게 차이남")
        if not reasons:
            continue
        found.append({
            "date": point["date"],
            "value": point["value"],
            "status": status,
            "reasons": reasons,
            # 얼마나 튀는 날인지. 정렬에만 쓰고 설명에는 쓰지 않는다.
            "deviation_sigma": round(gap / deviation, 2) if deviation > 0 else None,
        })
    found.sort(key=lambda item: (item["status"] == STATUS_MANAGE, item["deviation_sigma"] or 0), reverse=True)
    if is_chronic:
        # 평소와 크게 다른 날은 그대로 두고, 범위 이탈만으로 잡힌 날은 최악의 하루만 남긴다.
        spikes = [item for item in found if "구간 평균과 크게 차이남" in item["reasons"]]
        chronic_example = [item for item in found if item not in spikes][:1]
        found = spikes + chronic_example
    return found[:_MAX_ANOMALIES_PER_METRIC]


def _signals(metric: _Metric, series: list[dict[str, Any]], window_days: int) -> dict[str, Any]:
    """한 구간에서 항목이 어떤 상태였는지 계산한다.

    전체 구간과 최근 구간에 같은 잣대를 대야 두 결과를 견줄 수 있으므로, 구간을 받아
    같은 계산을 두 번 돌린다. 반환하는 값 중 level·frequency·direction·stability·
    confidence는 사용자에게 그대로 옮겨 써도 되는 표현이다.
    """
    values = [point["value"] for point in series]
    average = fmean(values)
    deviation = pstdev(values) if len(values) > 1 else 0.0

    # 구간을 반으로 갈라 과거와 현재를 견준다. 양쪽에 2점씩은 있어야 의미가 있다.
    earlier_average = recent_average = change = change_rate = None
    earlier_range = recent_range = ""
    if len(series) >= _MIN_DAYS_FOR_COMPARISON:
        half = len(series) // 2
        earlier, later = series[:half], series[half:]
        earlier_average = round(fmean(point["value"] for point in earlier), 2)
        recent_average = round(fmean(point["value"] for point in later), 2)
        change = round(recent_average - earlier_average, 2)
        if earlier_average:
            change_rate = round(change / abs(earlier_average) * 100, 1)
        earlier_range = f"{earlier[0]['date']}~{earlier[-1]['date']}"
        recent_range = f"{later[0]['date']}~{later[-1]['date']}"

    statuses = [metric.status(value) for value in values]
    out_of_range_days = sum(1 for status in statuses if status in {STATUS_CAUTION, STATUS_MANAGE})
    coverage_ratio = round(len(values) / window_days, 2)
    cv = round(deviation / abs(average) * 100, 1) if average else None
    current_status = metric.status(recent_average)
    return {
        "window_days": window_days,
        "covered_range": f"{series[0]['date']}~{series[-1]['date']}",
        "days": len(values),
        "average": round(average, 2),
        "minimum": min(values),
        "maximum": max(values),
        "coverage_ratio": coverage_ratio,
        "earlier_average": earlier_average,
        "earlier_range": earlier_range,
        "earlier_status": metric.status(earlier_average),
        "recent_average": recent_average,
        "recent_range": recent_range,
        "current_status": current_status,
        "change": change,
        "change_rate": change_rate,
        "stdev": round(deviation, 2),
        "cv": cv,
        "out_of_range_days": out_of_range_days,
        "longest_out_of_range_run": _longest_out_of_range_run(metric, series),
        # 아래 다섯 값이 사용자에게 그대로 옮겨 써도 되는 표현이다.
        "level": _level_text(current_status if current_status != STATUS_UNKNOWN else metric.status(values[-1])),
        "frequency": _frequency_text(out_of_range_days, len(values)),
        "direction": _direction_text(change, change_rate, deviation, metric.direction),
        "stability": _stability_text(cv),
        "confidence": _confidence_text(metric, len(values), coverage_ratio),
    }


def _summarize_metric(
    metric: _Metric,
    series: list[dict[str, Any]],
    windows: dict[str, int],
    latest_date: str,
) -> dict[str, Any]:
    """항목 하나를 전체 구간과 최근 구간 두 벌로 정리한다."""
    latest = next((point["value"] for point in reversed(series) if point["date"] == latest_date), None)
    # 최근 구간은 마지막 기록일에서 되짚는다. 오늘로 자르면 기기 연동이 끊긴 사용자는
    # 최근 구간이 통째로 비어 버린다. 저장소가 구간을 잡는 방식과 같은 기준이다.
    recent_series = _tail_since(series, latest_date, windows["recent"])
    return {
        "metric": metric.label,
        "unit": metric.unit,
        "kind": metric.kind,
        "direction_type": metric.direction,
        "reference": metric.reference_text,
        "latest": latest,
        "latest_date": series[-1]["date"],
        "latest_status": metric.status(latest),
        # 주중·주말 차이는 구간을 나눠 볼 값이 아니라 전체 기록으로 한 번 본다.
        "weekly_pattern": _weekly_pattern_text(series),
        "full": _signals(metric, series, windows["full"]),
        "recent": _signals(metric, recent_series, windows["recent"]) if recent_series else None,
        "anomalies": _find_anomalies(metric, series),
        "series": _downsample(series, _MAX_SERIES_POINTS),
        "series_downsampled": len(series) > _MAX_SERIES_POINTS,
    }


def _tail_since(series: list[dict[str, Any]], latest_date: str, days: int) -> list[dict[str, Any]]:
    """마지막 기록일에서 days일 되짚은 구간만 남긴다."""
    try:
        since = (date.fromisoformat(latest_date) - timedelta(days=days - 1)).isoformat()
    except ValueError:
        return series
    return [point for point in series if point["date"] >= since]


# 항목마다 프롬프트에 넘길 값. 나머지 통계는 검증용으로만 남기고 모델에게 주지 않는다.
# 여기에 필드를 더할 때는 그 값이 답변에 숫자로 새어 나와도 괜찮은지 먼저 따져야 한다.
_PROMPT_METRIC_FIELDS = ("metric", "unit", "kind", "reference", "weekly_pattern")
# 구간마다 넘길 신호. 전부 사람 말로 옮겨 둔 표현이거나 세기를 나타내는 횟수다.
_PROMPT_SIGNAL_FIELDS = (
    "level", "frequency", "direction", "stability", "confidence",
    "longest_out_of_range_run", "days",
)


def _signal_view(signals: dict[str, Any] | None, with_coverage: bool) -> dict[str, Any] | None:
    """한 구간의 신호에서 모델에게 줄 것만 고른다."""
    if not signals:
        return None
    view = {key: signals[key] for key in _PROMPT_SIGNAL_FIELDS if key in signals}
    # 대표 수치 한 개만 남긴다. 어림수로 한 번 언급할 때 쓰라고 주는 값이다.
    view["typical"] = signals.get("recent_average") or signals.get("average")
    if with_coverage:
        # 하루 누적 항목은 기록이 빠지면 총량이 실제보다 적게 잡힌다.
        view["coverage_ratio"] = signals.get("coverage_ratio")
    return view


def _prompt_view(analysis: dict[str, Any]) -> dict[str, Any]:
    """모델에게 보여 줄 압축본을 만든다.

    일별 계열과 전·후반 평균, 변동계수 같은 원시 통계는 넘기지 않는다. 주면 그대로
    옮겨 적기 때문이다. 대신 같은 뜻을 담은 자연어 표현을 넘긴다. 이상 지점도 예시
    한 건만 남겨 날짜 나열을 부르지 않게 한다.
    """
    metrics = []
    for metric in analysis.get("metrics", []):
        accumulation = metric.get("kind") == "accumulation"
        view = {key: metric[key] for key in _PROMPT_METRIC_FIELDS if key in metric}
        view["full"] = _signal_view(metric.get("full"), accumulation)
        view["recent"] = _signal_view(metric.get("recent"), accumulation)
        example = (metric.get("anomalies") or [])[:_MAX_PROMPT_ANOMALIES]
        if example:
            view["example_day"] = [{"date": item["date"], "value": item["value"]} for item in example]
        metrics.append(view)
    return {
        "domain_label": analysis.get("domain_label", ""),
        "windows": analysis.get("windows", {}),
        "covered_range": analysis.get("covered_range", ""),
        "data_truncated": analysis.get("data_truncated", False),
        "latest_date": analysis.get("latest_date", ""),
        "reference_basis": analysis.get("reference_basis", ""),
        "metrics": metrics,
        "co_movements": [
            {key: item[key] for key in ("metrics", "relation", "shared_days")}
            for item in analysis.get("co_movements", [])
        ],
        "sleep_timing": analysis.get("sleep_timing"),
        "exercise_habit": analysis.get("exercise_habit"),
    }


class LifestyleReportService:
    """탭별 수치와 판정은 직접 계산하고 설명만 Gemini에 맡긴다."""

    def __init__(self) -> None:
        self._llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0).with_structured_output(
            LifestyleReportContent
        )

    async def generate_with_trace(
        self,
        domain: str,
        window: dict[str, Any],
    ) -> tuple[LifestyleReportContent, dict[str, Any]]:
        """탭 하나의 분석 본문과 검증용 계산 근거를 함께 반환한다."""
        started = perf_counter()
        analysis = self.build_analysis(domain, window)
        analysis_elapsed = perf_counter() - started
        ai_started = perf_counter()
        report = await self._llm.ainvoke(self.build_prompt(domain, analysis))
        ai_elapsed = perf_counter() - ai_started
        return report, {
            "analysis_input": analysis,
            "timings": {
                "analysis_seconds": round(analysis_elapsed, 3),
                "ai_seconds": round(ai_elapsed, 3),
                "total_seconds": round(perf_counter() - started, 3),
            },
        }

    @staticmethod
    def build_prompt(domain: str, analysis: dict[str, Any]) -> str:
        """공통 규칙에 탭별 지침을 붙여 프롬프트를 만든다."""
        return ACTIVE_PROMPT.REPORT_PROMPT.format(
            common_rules=ACTIVE_PROMPT.COMMON_RULES,
            domain_guide=ACTIVE_PROMPT.DOMAIN_GUIDES.get(domain, ""),
            domain_label=DOMAIN_LABELS.get(domain, domain),
            latest_date=analysis["latest_date"] or "기록 없음",
            analysis_data=json.dumps(_prompt_view(analysis), ensure_ascii=False, indent=2),
        )

    @staticmethod
    def build_analysis(domain: str, window: dict[str, Any]) -> dict[str, Any]:
        """탭의 세부 항목마다 전체 구간과 최근 구간을 두 벌로 계산한다."""
        windows = analysis_window(domain)
        metrics = _DOMAIN_METRICS.get(domain, [])
        series_by_metric = [(metric, metric.daily_series(window)) for metric in metrics]
        # 마지막 기록일은 항목마다 갈릴 수 있어 탭 안에서 가장 늦은 날을 당일 기준으로 삼는다.
        latest_date = max(
            (series[-1]["date"] for _, series in series_by_metric if series),
            default="",
        )
        recorded = [(metric, series) for metric, series in series_by_metric if series]
        covered = sorted(point["date"] for _, series in recorded for point in (series[0], series[-1]))
        # 조회 상한에 걸려 오래된 기록이 잘렸다면 없는 기간까지 말하지 않도록 알린다.
        truncated = any(
            (window.get(metric.source) or {}).get("truncated") for metric, _ in recorded
        )
        return {
            "domain": domain,
            "domain_label": DOMAIN_LABELS.get(domain, domain),
            "windows": windows,
            "covered_range": f"{covered[0]}~{covered[-1]}" if covered else "",
            "data_truncated": truncated,
            "latest_date": latest_date,
            "reference_basis": "일반 성인 기준이며 성별·나이·활동량을 반영하지 않음",
            "metrics": [
                _summarize_metric(metric, series, windows, latest_date)
                for metric, series in recorded
            ],
            # 탭 안에서 함께 움직인 항목 짝. 다른 탭과는 엮지 않는다.
            "co_movements": _co_movements(recorded),
            # 잠의 길이만으로는 안 보이는 것. 수면 탭에서만 값이 생긴다.
            "sleep_timing": _sleep_timing(window, _sleep_target_hours()) if domain == "sleep" else None,
            # 운동은 활동과 갈라 빈도로 본다. 활동 탭에서만 값이 생긴다.
            "exercise_habit": (
                _exercise_habit(window, windows["recent"]) if domain == "activity" else None
            ),
        }
