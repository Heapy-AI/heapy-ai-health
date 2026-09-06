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
from collections.abc import Callable
from statistics import StatisticsError, correlation, fmean, pstdev
from time import perf_counter
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import MODEL
from app.schemas.lifestyle_report import LifestyleReportContent
from app.services.prompts import lifestyle_report_v2 as prompt_v2


# 쓰고 있는 프롬프트 판. v1.0으로 되돌리려면 이 모듈만 바꾸면 된다.
# (v1.0은 출력 계약이 달라 LifestyleReportContentV1을 함께 써야 한다.)
ACTIVE_PROMPT = prompt_v2
PROMPT_VERSION = prompt_v2.VERSION


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
# 같은 탭 안에서 함께 움직인 항목으로 볼 상관계수 문턱과 보고 상한.
_CO_MOVEMENT_THRESHOLD = 0.6
_MAX_CO_MOVEMENTS = 4
# 프롬프트에 예시로 넘기는 이상 지점 수. 날짜 나열을 부르지 않도록 최소로 준다.
_MAX_PROMPT_ANOMALIES = 1


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


def _scaled(value: Any, divisor: float) -> float | None:
    """초를 분으로, 미터를 km로 바꾸는 것처럼 단위만 환산한다."""
    number = _number(value)
    return None if number is None else number / divisor


class _Metric:
    """탭 화면의 세부 항목 하나.

    값 추출·일별 합산 방식과 함께, 좋고 나쁨을 가리는 기준을 들고 있다.

    direction
        higher  채울수록 좋은 항목 (걸음 수, 단백질)
        lower   적을수록 좋은 항목 (나트륨, 깬 시간)
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
#   걸음·활동시간  WHO 신체활동 권고(주 150분 중강도) 및 국내 걷기 권고 8,000걸음
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
        _Metric("계단", "층", **_daily_sum("activity", "record_date", lambda row: row.get("floors_climbed"))),
        _Metric("활동시간", "분", **_daily_sum("activity", "record_date", lambda row: row.get("active_time")),
                direction="higher", low=30, caution_low=15),
        # lifestyle_activity.distance_m은 컬럼명과 달리 km로 적재돼 환산하지 않는다.
        _Metric("이동거리", "km", **_daily_sum("activity", "record_date", lambda row: row.get("active_distance_km"))),
        _Metric("활동칼로리", "kcal", **_daily_sum("activity", "record_date", lambda row: row.get("active_calories"))),
        # 주 150분 권고를 하루 평균으로 환산하면 약 21분이다.
        _Metric("운동시간", "분", **_daily_sum("exercise", "record_date", lambda row: _scaled(row.get("duration_sec"), 60)),
                direction="higher", low=21, caution_low=10),
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
        # 깊은수면은 총 수면시간 대비 비율로 보는 값이라 절대 분수 기준을 두지 않는다.
        _Metric("깊은수면", "분", **_daily_sum("sleep", "measured_at", lambda row: _detail(row, "deep_sleep_min"))),
        _Metric("깬 시간", "분", **_daily_sum("sleep", "measured_at", lambda row: _detail(row, "awake_min")),
                direction="lower", high=30, caution_high=60),
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


def _summarize_metric(metric: _Metric, series: list[dict[str, Any]], window_days: int, latest_date: str) -> dict[str, Any]:
    """항목 하나의 당일 값·구간 통계·전후반 비교·이상 지점을 한데 모은다."""
    values = [point["value"] for point in series]
    average = fmean(values)
    latest = next((point["value"] for point in reversed(series) if point["date"] == latest_date), None)

    # 구간을 반으로 갈라 과거와 현재를 견준다. 양쪽에 2점씩은 있어야 의미가 있다.
    earlier_average = recent_average = change = change_rate = None
    earlier_range = recent_range = ""
    if len(series) >= _MIN_DAYS_FOR_COMPARISON:
        half = len(series) // 2
        earlier, recent = series[:half], series[half:]
        earlier_average = round(fmean(point["value"] for point in earlier), 2)
        recent_average = round(fmean(point["value"] for point in recent), 2)
        change = round(recent_average - earlier_average, 2)
        if earlier_average:
            change_rate = round(change / abs(earlier_average) * 100, 1)
        earlier_range = f"{earlier[0]['date']}~{earlier[-1]['date']}"
        recent_range = f"{recent[0]['date']}~{recent[-1]['date']}"

    if change is None:
        trend = "데이터 부족"
    elif change == 0:
        trend = "유지"
    else:
        trend = "상승" if change > 0 else "하락"

    deviation = pstdev(values) if len(values) > 1 else 0.0
    statuses = [metric.status(value) for value in values]
    out_of_range_days = sum(1 for status in statuses if status in {STATUS_CAUTION, STATUS_MANAGE})
    coverage_ratio = round(len(values) / window_days, 2)
    cv = round(deviation / abs(average) * 100, 1) if average else None
    # 통계값을 사람 말로 미리 옮겨 둔다. 모델은 숫자보다 이 표현을 쓰게 된다.
    current_status = metric.status(recent_average)
    return {
        "metric": metric.label,
        "unit": metric.unit,
        "kind": metric.kind,
        "direction": metric.direction,
        "reference": metric.reference_text,
        "latest": latest,
        "latest_date": series[-1]["date"],
        "latest_status": metric.status(latest),
        "average": round(average, 2),
        "minimum": min(values),
        "maximum": max(values),
        "days": len(values),
        # 구간의 며칠에 기록이 있었는지. 낮으면 총량·평균을 단정할 수 없다.
        "coverage_ratio": coverage_ratio,
        # 아래 네 값이 사용자에게 그대로 옮겨 써도 되는 표현이다.
        "level": _level_text(current_status if current_status != STATUS_UNKNOWN else metric.status(latest)),
        "frequency": _frequency_text(out_of_range_days, len(values)),
        "direction": _direction_text(change, change_rate, deviation, metric.direction),
        "stability": _stability_text(cv),
        "confidence": _confidence_text(metric, len(values), coverage_ratio),
        # 기준을 벗어난 기록이 연달아 몇 번 이어졌는지. 반복성을 말할 근거다.
        "longest_out_of_range_run": _longest_out_of_range_run(metric, series),
        "earlier_average": earlier_average,
        "earlier_range": earlier_range,
        "earlier_status": metric.status(earlier_average),
        "recent_average": recent_average,
        "recent_range": recent_range,
        "current_status": current_status,
        "change": change,
        "change_rate": change_rate,
        "trend": trend,
        "stdev": round(deviation, 2),
        # 변동계수. 평균 대비 얼마나 들쭉날쭉했는지를 단위 없이 견줄 수 있다.
        "cv": cv,
        "out_of_range_days": out_of_range_days,
        "anomalies": _find_anomalies(metric, series),
        "series": _downsample(series, _MAX_SERIES_POINTS),
        "series_downsampled": len(series) > _MAX_SERIES_POINTS,
    }


# 프롬프트에 넘길 항목 필드. 나머지 통계는 검증용으로만 남기고 모델에게 주지 않는다.
# 여기에 필드를 더할 때는 그 값이 답변에 숫자로 새어 나와도 괜찮은지 먼저 따져야 한다.
_PROMPT_METRIC_FIELDS = (
    "metric", "unit", "kind", "reference",
    "level", "frequency", "direction", "stability", "confidence",
    "longest_out_of_range_run", "days",
)


def _prompt_view(analysis: dict[str, Any]) -> dict[str, Any]:
    """모델에게 보여 줄 압축본을 만든다.

    일별 계열과 전·후반 평균, 변동계수 같은 원시 통계는 넘기지 않는다. 주면 그대로
    옮겨 적기 때문이다. 대신 같은 뜻을 담은 자연어 표현을 넘긴다. 이상 지점도 예시
    한 건만 남겨 날짜 나열을 부르지 않게 한다.
    """
    metrics = []
    for metric in analysis.get("metrics", []):
        view = {key: metric[key] for key in _PROMPT_METRIC_FIELDS if key in metric}
        # 대표 수치 한 개만 남긴다. 어림수로 한 번 언급할 때 쓰라고 주는 값이다.
        view["recent_typical"] = metric.get("recent_average")
        if metric.get("kind") == "accumulation":
            view["coverage_ratio"] = metric.get("coverage_ratio")
        example = (metric.get("anomalies") or [])[:_MAX_PROMPT_ANOMALIES]
        if example:
            view["example_day"] = [{"date": item["date"], "value": item["value"]} for item in example]
        metrics.append(view)
    return {
        "domain_label": analysis.get("domain_label", ""),
        "window_days": analysis.get("window_days"),
        "latest_date": analysis.get("latest_date", ""),
        "reference_basis": analysis.get("reference_basis", ""),
        "metrics": metrics,
        "co_movements": [
            {key: item[key] for key in ("metrics", "relation", "shared_days")}
            for item in analysis.get("co_movements", [])
        ],
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
        window_days: int,
    ) -> tuple[LifestyleReportContent, dict[str, Any]]:
        """탭 하나의 분석 본문과 검증용 계산 근거를 함께 반환한다."""
        started = perf_counter()
        analysis = self.build_analysis(domain, window, window_days)
        analysis_elapsed = perf_counter() - started
        ai_started = perf_counter()
        report = await self._llm.ainvoke(self.build_prompt(domain, analysis, window_days))
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
    def build_prompt(domain: str, analysis: dict[str, Any], window_days: int) -> str:
        """공통 규칙에 탭별 지침을 붙여 프롬프트를 만든다."""
        return ACTIVE_PROMPT.REPORT_PROMPT.format(
            common_rules=ACTIVE_PROMPT.COMMON_RULES,
            domain_guide=ACTIVE_PROMPT.DOMAIN_GUIDES.get(domain, ""),
            domain_label=DOMAIN_LABELS.get(domain, domain),
            window_days=window_days,
            latest_date=analysis["latest_date"] or "기록 없음",
            analysis_data=json.dumps(_prompt_view(analysis), ensure_ascii=False, indent=2),
        )

    @staticmethod
    def build_analysis(domain: str, window: dict[str, Any], window_days: int) -> dict[str, Any]:
        """탭의 세부 항목마다 당일 값·구간 통계·판정·이상 지점을 계산한다."""
        metrics = _DOMAIN_METRICS.get(domain, [])
        series_by_metric = [(metric, metric.daily_series(window)) for metric in metrics]
        # 마지막 기록일은 항목마다 갈릴 수 있어 탭 안에서 가장 늦은 날을 당일 기준으로 삼는다.
        latest_date = max(
            (series[-1]["date"] for _, series in series_by_metric if series),
            default="",
        )
        recorded = [(metric, series) for metric, series in series_by_metric if series]
        return {
            "domain": domain,
            "domain_label": DOMAIN_LABELS.get(domain, domain),
            "window_days": window_days,
            "latest_date": latest_date,
            "reference_basis": "일반 성인 기준이며 성별·나이·활동량을 반영하지 않음",
            "metrics": [
                _summarize_metric(metric, series, window_days, latest_date)
                for metric, series in recorded
            ],
            # 탭 안에서 함께 움직인 항목 짝. 다른 탭과는 엮지 않는다.
            "co_movements": _co_movements(recorded),
        }
