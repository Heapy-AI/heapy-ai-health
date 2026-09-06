"""생활건강 탭별 AI 분석 API 모델.

내건강 > 생활건강의 생체·활동·영양·수면 탭은 항목 특성이 서로 달라 분석 관점도 다르다.
어느 탭이든 당일 값·과거와 현재 비교·패턴·이상 지점을 함께 내려주도록 계약을 고정한다.

status 계열 값은 서비스가 참고범위와 비교해 계산한 결과이며 AI가 바꾸지 못한다.

작성자: 고수연
"""

from typing import Any

from pydantic import BaseModel, Field


class LifestyleReportMetric(BaseModel):
    """분석 대상 항목 한 건의 당일 값과 구간 비교."""

    metric: str
    unit: str = ""
    # 참고범위 설명. 기준을 정할 수 없는 항목은 빈 문자열로 둔다.
    reference: str = ""
    latest: float | None = None
    average: float | None = None
    # 구간 전반과 후반의 평균. 과거와 현재를 견주는 근거다.
    previous: float | None = None
    current: float | None = None
    change: float | None = None
    trend: str = ""
    # 코드가 계산한 판정: 양호 · 주의 · 관리 필요 · 판단 보류
    previous_status: str = ""
    status: str = ""
    description: str


class LifestyleReportAnomaly(BaseModel):
    """참고범위를 벗어났거나 평소와 크게 달랐던 날 한 건."""

    metric: str
    date: str
    value: float | None = None
    unit: str = ""
    status: str = ""
    description: str


class LifestyleReportContent(BaseModel):
    """탭 하나에 대한 AI 분석 본문."""

    headline: str
    summary: str
    metrics: list[LifestyleReportMetric] = Field(default_factory=list)
    # 수치 하나만 봐서는 안 보이는 흐름. 항목 사이의 관계나 규칙성을 담는다.
    patterns: list[str] = Field(default_factory=list, max_length=4)
    anomalies: list[LifestyleReportAnomaly] = Field(default_factory=list)
    overall_analysis: str
    recommendations: list[str] = Field(default_factory=list, max_length=3)


class LifestyleReportResponse(BaseModel):
    """생활건강 탭 AI 분석 응답."""

    success: bool
    domain: str
    window_days: int
    latest_date: str = ""
    report: LifestyleReportContent
    verification: dict[str, Any] = Field(default_factory=dict)
