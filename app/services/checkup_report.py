"""전체 건강검진 이력 기반 AI 요약분석 서비스.

작성자: 고수연, 최영선
"""

from __future__ import annotations

import json
from collections import defaultdict
from time import perf_counter
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import MODEL
from app.schemas.checkup_report import CheckupReportContent


_REPORT_PROMPT = """너는 사용자가 건강검진 변화를 이해하도록 돕는 친절한 건강관리 AI 코치다.
질병을 진단하거나 원인을 추측하지 말고, 입력 데이터에 있는 수치와 DB 판정만 사용하라.
reference_status는 시스템이 DB의 status를 그대로 전달한 값이다. 절대 재판정하거나 변경하지 마라.
현재값, 이전값, 변화량, 최근 전체 이력의 추세를 함께 설명하라.

[분류 규칙]
- improved: 변화 방향이 개선인 항목. 현재가 경계여도 개선 사실은 설명하라.
- maintained: 변화가 없거나 의미 있는 변화가 작은 항목.
- management_needed: status가 관리 필요이거나 reference_status가 경계 또는 위험인 항목.
- 한 항목을 여러 분류에 중복해서 넣지 마라. 관리 필요 조건이 개선보다 우선한다.
- reference_status가 정상인 항목도 추세가 불리하면 management_needed에 넣을 수 있지만, 현재 정상 범위라는 점을 함께 말하라.

[작성 규칙]
- headline은 가장 중요한 변화 2~3가지를 한 문장으로 요약하라.
- summary와 overall_analysis는 중요한 흐름을 3~5문장으로 설명하라.
- 각 metric description에는 이전값, 현재값, 변화량, 추세, DB 판정을 포함하라.
- recommendations는 입력에 없는 생활습관이나 원인을 단정하지 말고 최대 3개만 작성하라.
- 출력은 반드시 JSON schema에 맞는 한국어 존댓말로 작성하라.

검진 이력 분석 데이터:
{analysis_data}
"""


class CheckupReportService:
    """검진 이력의 수치 변화만 계산하고 Gemini에 설명을 위임한다."""

    def __init__(self) -> None:
        self._llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0).with_structured_output(
            CheckupReportContent
        )

    async def generate(self, history: list[dict[str, Any]]) -> CheckupReportContent:
        report, _ = await self.generate_with_trace(history)
        return report

    async def generate_with_trace(
        self,
        history: list[dict[str, Any]],
    ) -> tuple[CheckupReportContent, dict[str, Any]]:
        started = perf_counter()
        analysis = self._build_analysis(history)
        analysis_elapsed = perf_counter() - started
        ai_started = perf_counter()
        report = await self._llm.ainvoke(
            _REPORT_PROMPT.format(
                analysis_data=json.dumps(analysis, ensure_ascii=False, indent=2)
            )
        )
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
    def _build_analysis(history: list[dict[str, Any]]) -> dict[str, Any]:
        catalog: dict[str, tuple[str, str, str]] = {}
        values: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for checkup in history:
            for result in checkup.get("results", []):
                item_code = str(result.get("item_code") or "")
                raw_value = result.get("value")
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                catalog[item_code] = (
                    str(result.get("item_name") or item_code),
                    str(result.get("unit") or ""),
                    str(result.get("status") or ""),
                )
                values[item_code].append({"date": checkup.get("date", ""), "value": value})

        metrics: list[dict[str, Any]] = []
        for item_code, series in values.items():
            if len(series) < 2:
                continue
            previous = series[-2]["value"]
            current = series[-1]["value"]
            change = round(current - previous, 2)
            metric_name, unit, db_status = catalog[item_code]
            direction = CheckupReportService._direction(item_code, metric_name)
            if change == 0:
                trend = "큰 변화 없이 유지"
                status = "유지"
            else:
                trend = "상승" if current > previous else "하락"
                status = "개선" if (
                    (direction == "lower" and current < previous)
                    or (direction == "higher" and current > previous)
                ) else "관리 필요" if direction in {"lower", "higher"} else "변화 확인"
            metrics.append({
                "metric_id": item_code,
                "metric": metric_name,
                "previous": previous,
                "current": current,
                "change": change,
                "unit": unit,
                "trend": trend,
                "status": status,
                "reference_status": db_status,
                "direction": direction,
                "history": series,
            })
        return {"checkup_count": len(history), "metrics": metrics}

    @staticmethod
    def _direction(item_code: str, metric_name: str) -> str:
        """검사 항목의 일반적인 변화 방향을 분석용으로 반환한다."""
        text = f"{item_code} {metric_name}".casefold()
        if any(keyword in text for keyword in ("hdl", "egfr", "고밀도", "여과율")):
            return "higher"
        if any(keyword in text for keyword in ("bmi", "체질량")):
            return "target"
        if any(keyword in text for keyword in (
            "glucose", "혈당", "ldl", "중성지방", "triglyceride", "콜레스테롤",
            "systolic", "diastolic", "혈압", "ast", "alt", "gamma", "감마",
            "creatinine", "크레아티닌",
        )):
            return "lower"
        return "unknown"
