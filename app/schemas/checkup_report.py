from typing import Any, Literal

from pydantic import BaseModel, Field


class CheckupReportRequest(BaseModel):
    persona: Literal[
        "professional",
        "coach",
    ] = "professional"

class CheckupReportMetric(BaseModel):
    metric: str
    previous: float | None = None
    current: float | None = None
    unit: str = ""
    change: float | None = None
    trend: str
    status: str
    reference_status: str
    description: str


class CheckupReportContent(BaseModel):
    headline: str
    summary: str

    improved: list[CheckupReportMetric] = Field(default_factory=list)
    maintained: list[CheckupReportMetric] = Field(default_factory=list)
    management_needed: list[CheckupReportMetric] = Field(default_factory=list)
    overall_analysis: str
    recommendations: list[str] = Field(default_factory=list, max_length=3)


class CheckupReportResponse(BaseModel):
    success: bool
    report: CheckupReportContent
    checkup_count: int
    verification: dict[str, Any] = Field(default_factory=dict)
