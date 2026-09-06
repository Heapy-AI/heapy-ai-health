"""생활건강 탭별 AI 분석 API 모델.

내건강 > 생활건강의 생체·활동·영양·수면 탭은 항목 특성이 서로 달라 분석 관점도 다르다.
탭 하나를 독립으로 분석하되, 사용자에게는 항목별 수치가 아니라 '지금 어떤 상태인지'를
설명한 결과를 내려준다.

v1.0 계약(LifestyleReportContentV1)은 항목마다 수치를 적게 해서 결과가 통계 리포트처럼
읽혔다. v2.0은 나열할 자리를 없애 같은 문제가 되풀이되지 않게 한다. 상세 통계는 API 응답의
verification.analysis_input에 그대로 남으므로 개발자 검증 화면에서는 여전히 전부 볼 수 있다.

작성자: 고수연
"""

from typing import Any

from pydantic import BaseModel, Field


class LifestyleReportContent(BaseModel):
    """탭 하나에 대한 AI 분석 본문 (프롬프트 v2.0 계약).

    화면은 '현재 상태'와 '지금 신경 쓰면 좋은 것' 두 덩어리로 읽힌다. 항목별 수치 목록과
    이상 지점 목록을 두지 않는 것이 핵심이다. 자리를 만들어 두면 모델이 채우려 든다.
    """

    # 이 탭에서 가장 중요한 것 한 문장.
    headline: str
    # 지금 상태 → 변화 방향 → 반복 여부를 이어 쓴 2~4문장.
    current_state: str
    # 핵심 패턴을 짧게 덧붙일 자리. current_state와 겹치면 비워 둔다.
    key_points: list[str] = Field(default_factory=list, max_length=3)
    # 이 탭 데이터에서 우선순위가 높은 행동만. 문제가 없으면 비울 수 있다.
    actions: list[str] = Field(default_factory=list, max_length=3)


class LifestyleReportMetricV1(BaseModel):
    """v1.0 계약의 항목별 수치 한 건. 프롬프트 v1.0을 되돌려 쓸 때만 사용한다."""

    metric: str
    unit: str = ""
    reference: str = ""
    latest: float | None = None
    average: float | None = None
    previous: float | None = None
    current: float | None = None
    change: float | None = None
    trend: str = ""
    previous_status: str = ""
    status: str = ""
    description: str


class LifestyleReportAnomalyV1(BaseModel):
    """v1.0 계약의 이상 지점 한 건. 프롬프트 v1.0을 되돌려 쓸 때만 사용한다."""

    metric: str
    date: str
    value: float | None = None
    unit: str = ""
    status: str = ""
    description: str


class LifestyleReportContentV1(BaseModel):
    """프롬프트 v1.0의 출력 계약. 두 판을 견주려고 남겨 둔다."""

    headline: str
    summary: str
    metrics: list[LifestyleReportMetricV1] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list, max_length=4)
    anomalies: list[LifestyleReportAnomalyV1] = Field(default_factory=list)
    overall_analysis: str
    recommendations: list[str] = Field(default_factory=list, max_length=3)


class LifestyleReportResponse(BaseModel):
    """생활건강 탭 AI 분석 응답."""

    success: bool
    domain: str
    window_days: int
    latest_date: str = ""
    # 어느 판 프롬프트로 만든 결과인지. 화면과 검증 로그가 함께 참조한다.
    prompt_version: str = ""
    report: LifestyleReportContent
    verification: dict[str, Any] = Field(default_factory=dict)
