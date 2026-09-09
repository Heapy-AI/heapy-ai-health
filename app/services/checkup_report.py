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
from app.services.checkup_persona_prompt import (
    get_checkup_persona_prompt,
)


class CheckupReportService:
    """검진 이력의 수치 변화를 계산하고 페르소나에 맞춰 설명을 생성한다."""

    def __init__(self) -> None:
        self._llm = ChatGoogleGenerativeAI(
            model=MODEL,
            temperature=0,
        ).with_structured_output(
            CheckupReportContent
        )

    async def generate(
        self,
        history: list[dict[str, Any]],
        persona: str = "professional",
    ) -> CheckupReportContent:

        report, _ = await self.generate_with_trace(
            history,
            persona=persona,
        )

        return report

    async def generate_with_trace(
        self,
        history: list[dict[str, Any]],
        persona: str = "professional",
    ) -> tuple[CheckupReportContent, dict[str, Any]]:

        started = perf_counter()

        analysis = self._build_analysis(history)

        analysis_elapsed = (
            perf_counter() - started
        )

        prompt_template = (
            get_checkup_persona_prompt(persona)
        )

        prompt = prompt_template.format(
            analysis_data=json.dumps(
                analysis,
                ensure_ascii=False,
                indent=2,
            )
        )

        ai_started = perf_counter()

        report = await self._llm.ainvoke(prompt)

        ai_elapsed = (
            perf_counter() - ai_started
        )

        return report, {
            "persona": persona,
            "analysis_input": analysis,
            "timings": {
                "analysis_seconds": round(
                    analysis_elapsed,
                    3,
                ),
                "ai_seconds": round(
                    ai_elapsed,
                    3,
                ),
                "total_seconds": round(
                    perf_counter() - started,
                    3,
                ),
            },
        }

    @staticmethod
    def _build_analysis(
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:

        catalog: dict[
            str,
            tuple[str, str, str],
        ] = {}

        values: dict[
            str,
            list[dict[str, Any]],
        ] = defaultdict(list)

        for checkup in history:

            for result in checkup.get(
                "results",
                [],
            ):

                item_code = str(
                    result.get("item_code") or ""
                )

                raw_value = result.get("value")

                try:
                    value = float(raw_value)

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                catalog[item_code] = (
                    str(
                        result.get("item_name")
                        or item_code
                    ),
                    str(
                        result.get("unit")
                        or ""
                    ),
                    str(
                        result.get("status")
                        or ""
                    ),
                )

                values[item_code].append(
                    {
                        "date": checkup.get(
                            "date",
                            "",
                        ),
                        "value": value,
                    }
                )

        metrics: list[
            dict[str, Any]
        ] = []

        for (
            item_code,
            series,
        ) in values.items():

            if len(series) < 2:
                continue

            previous = series[-2]["value"]
            current = series[-1]["value"]

            change = round(
                current - previous,
                2,
            )

            (
                metric_name,
                unit,
                db_status,
            ) = catalog[item_code]

            direction = (
                CheckupReportService._direction(
                    item_code,
                    metric_name,
                )
            )

            if change == 0:

                trend = "큰 변화 없이 유지"
                status = "유지"

            else:

                trend = (
                    "상승"
                    if current > previous
                    else "하락"
                )

                status = (
                    "개선"
                    if (
                        (
                            direction == "lower"
                            and current < previous
                        )
                        or (
                            direction == "higher"
                            and current > previous
                        )
                    )
                    else (
                        "관리 필요"
                        if direction
                        in {
                            "lower",
                            "higher",
                        }
                        else "변화 확인"
                    )
                )

            metrics.append(
                {
                    "metric_id": item_code,
                    "metric": metric_name,
                    "previous": previous,
                    "current": current,
                    "change": change,
                    "unit": unit,
                    "trend": trend,
                    "status": status,
                    "reference_status": (
                        db_status
                    ),
                    "direction": direction,
                    "history": series,
                }
            )

        return {
            "checkup_count": len(history),
            "metrics": metrics,
        }

    @staticmethod
    def _direction(
        item_code: str,
        metric_name: str,
    ) -> str:
        """검사 항목의 일반적인 변화 방향을 분석용으로 반환한다."""

        text = (
            f"{item_code} {metric_name}"
            .casefold()
        )

        if any(
            keyword in text
            for keyword in (
                "hdl",
                "egfr",
                "고밀도",
                "여과율",
            )
        ):
            return "higher"

        if any(
            keyword in text
            for keyword in (
                "bmi",
                "체질량",
            )
        ):
            return "target"

        if any(
            keyword in text
            for keyword in (
                "glucose",
                "혈당",
                "ldl",
                "중성지방",
                "triglyceride",
                "콜레스테롤",
                "systolic",
                "diastolic",
                "혈압",
                "ast",
                "alt",
                "gamma",
                "감마",
                "creatinine",
                "크레아티닌",
            )
        ):
            return "lower"

        return "unknown"
