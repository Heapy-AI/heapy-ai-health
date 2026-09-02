"""인증된 사용자의 질문 관련 생활습관 컨텍스트 조회 서비스.

작성자: 고수연
- supabase_health_context.py 골격에 따라 동작
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests

from app.services.supabase_conversation import SupabaseConversationError


_TREND_KEYWORDS = (
    "추이",
    "변화",
    "변했",
    "높아졌",
    "낮아졌",
    "늘었",
    "줄었",
    "평균",
    "과거",
    "예전",
    "이전",
)
_GENERIC_KEYWORDS = ("생활습관", "생활 습관", "라이프스타일", "생활패턴", "건강습관")
_ACTIVITY_KEYWORDS = (
    "걸음",
    "걸었",
    "걷기",
    "활동량",
    "활동시간",
    "활동 시간",
    "계단",
    "만보",
    "활동칼로리",
)
_EXERCISE_KEYWORDS = (
    "운동",
    "러닝",
    "달리기",
    "조깅",
    "자전거",
    "사이클",
    "라이딩",
    "헬스",
    "유산소",
    "근력",
    "수영",
)
_NUTRITION_KEYWORDS = (
    "식단",
    "식사",
    "먹은",
    "먹었",
    "음식",
    "영양",
    "섭취",
    "칼로리",
    "나트륨",
    "단백질",
    "탄수화물",
    "지방",
    "당분",
    "식이섬유",
    "콜레스테롤",
    "수분",
    "물마",
    "물 마",
    "아침",
    "점심",
    "저녁",
    "간식",
)
_BIO_TYPE_KEYWORDS = {
    "weight": ("체중", "몸무게"),
    "bmi": ("bmi", "체질량"),
    "blood_pressure": ("혈압",),
    "blood_glucose": ("혈당",),
    "heart_rate": ("심박", "맥박", "심장박동", "심장 박동"),
    "sleep": ("수면", "잤", "잠자", "잠들", "잠은", "잠이", "잠을"),
}

# 질병명이 지표 키워드를 포함해 일반 질병 질문이 개인 기록 조회를 유발하는 것을 막는다.
# ("고혈압"의 혈압, "당뇨병"의 당뇨, "수면무호흡"의 수면 등)
_DISEASE_PHRASES = (
    "이상지질혈증",
    "수면무호흡",
    "수면장애",
    "고지혈증",
    "당뇨병",
    "고혈압",
    "저혈압",
    "고혈당",
    "저혈당",
    "지방간",
    "당뇨",
)

_BIO_TYPE_LABELS = {
    "weight": "체중",
    "bmi": "BMI",
    "blood_pressure": "혈압",
    "blood_glucose": "혈당",
    "heart_rate": "심박수",
    "sleep": "수면시간",
}
_EXERCISE_TYPE_LABELS = {
    "walking": "걷기",
    "running": "달리기",
    "indoor_cycling": "실내 자전거",
}
_MEAL_TYPE_LABELS = {
    "breakfast": "아침",
    "lunch": "점심",
    "dinner": "저녁",
    "snack": "간식",
}
_UNIT_LABELS = {"hour": "시간"}

_WATER_ROW_LIMIT = 7
# "생활습관 전반" 질문은 영역·지표별로 조회가 나뉘어 요청 수가 늘어난다.
# 챗 응답 경로이므로 vector_search와 같은 방식으로 병렬 조회한다.
_MAX_FETCH_WORKERS = 8


@dataclass(frozen=True)
class PersonalLifestyleContext:
    """LLM에 전달할 최소 범위의 개인 생활습관 컨텍스트."""

    prompt_text: str
    domains: tuple[str, ...]
    bio_types: tuple[str, ...]
    record_count: int
    includes_history: bool


class SupabaseLifestyleContextService:
    """RLS가 적용된 Data API로 본인 생활습관 기록만 조회한다."""

    def __init__(
        self,
        url: str,
        publishable_key: str,
        *,
        max_rows: int = 10,
        trend_max_rows: int = 30,
    ) -> None:
        self.url = url.rstrip("/")
        self.publishable_key = publishable_key
        self.max_rows = max_rows
        self.trend_max_rows = trend_max_rows

    @property
    def configured(self) -> bool:
        return bool(self.url and self.publishable_key)

    def get_relevant_context(
        self,
        access_token: str,
        user_id: str,
        question: str,
        resolved_terms: tuple[dict[str, Any], ...] = (),
    ) -> PersonalLifestyleContext | None:
        """질문에 해당하는 생활습관 영역만 조회해 프롬프트 컨텍스트로 반환한다."""
        if not self.configured or not access_token or not user_id:
            return None

        domains, bio_types = self._select_domains(question, resolved_terms)
        if not domains:
            return None

        includes_history = any(keyword in question for keyword in _TREND_KEYWORDS)
        limit = self.trend_max_rows if includes_history else self.max_rows

        # (섹션 제목, 조회 함수, 포맷 함수) 순서가 프롬프트 순서를 그대로 정한다.
        plan: list[tuple[str, Callable[[], list[dict[str, Any]]], Callable]] = []
        if "activity" in domains:
            plan.append(
                (
                    "[일별 활동량]",
                    lambda: self._get_activity(access_token, user_id, limit),
                    self._format_activity,
                )
            )
        if "exercise" in domains:
            plan.append(
                (
                    "[운동 기록]",
                    lambda: self._get_exercise(access_token, user_id, limit),
                    self._format_exercise,
                )
            )
        if "bio" in domains:
            plan.append(
                (
                    "[신체·수면 지표]",
                    lambda: self._get_bio(access_token, user_id, bio_types, limit),
                    self._format_bio,
                )
            )
        if "nutrition" in domains:
            plan.append(
                (
                    "[식사 기록]",
                    lambda: self._get_nutrition_food(access_token, user_id, limit),
                    self._format_food,
                )
            )
            plan.append(
                (
                    "[수분 섭취]",
                    lambda: self._get_nutrition_water(access_token, user_id, limit),
                    self._format_water,
                )
            )

        fetched = self._fetch_in_parallel([fetch for _, fetch, _ in plan])
        record_count = sum(len(rows) for rows in fetched)
        sections = [
            (title, formatter(rows))
            for (title, _, formatter), rows in zip(plan, fetched)
        ]
        sections = [(title, lines) for title, lines in sections if lines]
        if not sections or not record_count:
            return None

        prompt_lines = ["[인증된 사용자 생활습관 정보]"]
        for title, lines in sections:
            prompt_lines.append(title)
            prompt_lines.extend(lines)

        return PersonalLifestyleContext(
            prompt_text="\n".join(prompt_lines),
            domains=tuple(sorted(domains)),
            bio_types=tuple(sorted(bio_types)),
            record_count=record_count,
            includes_history=includes_history,
        )

    @staticmethod
    def _fetch_in_parallel(
        fetchers: list[Callable[[], list[dict[str, Any]]]],
    ) -> list[list[dict[str, Any]]]:
        """조회 순서를 유지한 채 병렬로 실행한다.

        한 영역이라도 실패하면 개인 컨텍스트가 불완전해지므로 예외를 그대로 올린다.
        """
        if len(fetchers) <= 1:
            return [fetch() for fetch in fetchers]
        with ThreadPoolExecutor(
            max_workers=min(len(fetchers), _MAX_FETCH_WORKERS)
        ) as executor:
            return list(executor.map(lambda fetch: fetch(), fetchers))

    @staticmethod
    def _select_domains(
        question: str,
        resolved_terms: tuple[dict[str, Any], ...] = (),
    ) -> tuple[set[str], set[str]]:
        """질문과 정규화된 용어에서 조회할 생활습관 영역을 고른다."""
        haystack = question.casefold()
        for term in resolved_terms:
            for key in ("canonical_name", "matched_alias"):
                value = term.get(key)
                if value:
                    haystack += " " + str(value).casefold()

        # 긴 질병명부터 제거해 "당뇨병"이 "당뇨"로 남지 않게 한다.
        for phrase in _DISEASE_PHRASES:
            haystack = haystack.replace(phrase, " ")

        generic = any(keyword in haystack for keyword in _GENERIC_KEYWORDS)
        domains: set[str] = set()
        bio_types: set[str] = set()

        if any(keyword in haystack for keyword in _ACTIVITY_KEYWORDS):
            domains.add("activity")
        if any(keyword in haystack for keyword in _EXERCISE_KEYWORDS):
            domains.add("exercise")
        if any(keyword in haystack for keyword in _NUTRITION_KEYWORDS):
            domains.add("nutrition")
        for bio_type, keywords in _BIO_TYPE_KEYWORDS.items():
            if any(keyword in haystack for keyword in keywords):
                domains.add("bio")
                bio_types.add(bio_type)

        if generic:
            domains.update({"activity", "exercise", "nutrition", "bio"})
        return domains, bio_types

    def _get_activity(
        self,
        access_token: str,
        user_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        return self._request(
            "/rest/v1/lifestyle_activity"
            f"?user_id=eq.{quote(user_id, safe='')}"
            "&select=record_date,steps,floors_climbed,active_time,"
            "active_distance,active_calories"
            f"&order=record_date.desc&limit={limit}",
            access_token,
        )

    def _get_exercise(
        self,
        access_token: str,
        user_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        return self._request(
            "/rest/v1/lifestyle_exercise"
            f"?user_id=eq.{quote(user_id, safe='')}"
            "&select=record_date,exercise_type,duration_sec,distance_m,calories"
            f"&order=record_date.desc&limit={limit}",
            access_token,
        )

    def _get_bio(
        self,
        access_token: str,
        user_id: str,
        bio_types: set[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        """지표별로 나눠 조회해 한 지표가 결과를 독점하지 않게 한다."""
        selected = sorted(bio_types) if bio_types else sorted(_BIO_TYPE_KEYWORDS)
        per_type = limit if bio_types else max(2, limit // 3)

        def fetch(bio_type: str) -> list[dict[str, Any]]:
            return self._request(
                "/rest/v1/lifestyle_bio"
                f"?user_id=eq.{quote(user_id, safe='')}"
                f"&bio_type=eq.{quote(bio_type, safe='')}"
                "&select=measured_at,bio_type,value,unit,detail_data"
                f"&order=measured_at.desc&limit={per_type}",
                access_token,
            )

        results = self._fetch_in_parallel(
            [lambda bio_type=bio_type: fetch(bio_type) for bio_type in selected]
        )
        return [row for rows in results for row in rows]

    def _get_nutrition_food(
        self,
        access_token: str,
        user_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        return self._request(
            "/rest/v1/lifestyle_nutrition"
            f"?user_id=eq.{quote(user_id, safe='')}"
            "&nutrition_type=eq.food"
            "&select=consumed_at,meal_type,title,calories,carbohydrate,"
            "protein,total_fat,sodium,sugar"
            f"&order=consumed_at.desc&limit={limit}",
            access_token,
        )

    def _get_nutrition_water(
        self,
        access_token: str,
        user_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        return self._request(
            "/rest/v1/lifestyle_nutrition"
            f"?user_id=eq.{quote(user_id, safe='')}"
            "&nutrition_type=eq.water"
            "&select=consumed_at,water_amount"
            f"&order=consumed_at.desc&limit={min(limit, _WATER_ROW_LIMIT)}",
            access_token,
        )

    @staticmethod
    def _date(value: Any) -> str:
        text = str(value or "").strip()
        return text[:10] if text else "날짜 미상"

    @staticmethod
    def _number(value: Any, unit: str = "", digits: int = 0) -> str:
        """None과 문자열 숫자를 모두 사람이 읽는 형태로 만든다."""
        if value is None or value == "":
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return f"{value}{unit}"
        return f"{number:,.{digits}f}{unit}"

    @classmethod
    def _join(cls, date: str, parts: list[str]) -> str:
        return " | ".join([date, *[part for part in parts if part]])

    @classmethod
    def _format_activity(cls, rows: list[dict[str, Any]]) -> list[str]:
        lines = []
        for row in rows:
            steps = cls._number(row.get("steps"), "보")
            floors = cls._number(row.get("floors_climbed"), "층")
            active = cls._number(row.get("active_time"), "분")
            # lifestyle_activity.active_distance는 km 단위로 적재된다.
            # (lifestyle_exercise.distance_m과 달리 컬럼명에 단위가 없다.)
            distance = cls._number(row.get("active_distance"), "km", digits=1)
            calories = cls._number(row.get("active_calories"), "kcal")
            parts = [
                f"걸음 {steps}" if steps else "",
                f"계단 {floors}" if floors else "",
                f"활동 {active}" if active else "",
                f"이동 {distance}" if distance else "",
                f"활동칼로리 {calories}" if calories else "",
            ]
            lines.append(cls._join(cls._date(row.get("record_date")), parts))
        return lines

    @classmethod
    def _format_exercise(cls, rows: list[dict[str, Any]]) -> list[str]:
        lines = []
        for row in rows:
            raw_type = str(row.get("exercise_type") or "")
            label = _EXERCISE_TYPE_LABELS.get(raw_type, raw_type or "종목 미상")
            duration = row.get("duration_sec")
            minutes = ""
            if duration not in (None, ""):
                try:
                    minutes = f"{float(duration) / 60:,.0f}분"
                except (TypeError, ValueError):
                    minutes = ""
            # lifestyle_exercise.distance_m은 미터 단위이므로 km로 환산해 표기한다.
            distance = row.get("distance_m")
            distance_text = ""
            if distance not in (None, ""):
                try:
                    distance_text = f"{float(distance) / 1000:,.1f}km"
                except (TypeError, ValueError):
                    distance_text = ""
            calories = cls._number(row.get("calories"), "kcal")
            parts = [label, minutes, distance_text, calories]
            lines.append(cls._join(cls._date(row.get("record_date")), parts))
        return lines

    @staticmethod
    def _bio_detail_parts(bio_type: str, detail: dict[str, Any]) -> list[str]:
        """지표별 detail_data에서 해석에 필요한 값만 뽑는다.

        혈당의 공복 여부처럼 값만으로는 판단할 수 없는 정보가 여기에 담긴다.
        """
        if bio_type == "blood_pressure":
            pulse = detail.get("pulse")
            return [f"맥박 {pulse}bpm"] if pulse is not None else []
        if bio_type == "blood_glucose":
            if "fasting" in detail:
                return ["공복" if detail.get("fasting") else "식후"]
            return []
        if bio_type == "sleep":
            parts = []
            if detail.get("sleep_score") is not None:
                parts.append(f"수면점수 {detail['sleep_score']}")
            if detail.get("deep_sleep_min") is not None:
                parts.append(f"깊은수면 {detail['deep_sleep_min']}분")
            if detail.get("awake_min") is not None:
                parts.append(f"깬시간 {detail['awake_min']}분")
            return parts
        return []

    @classmethod
    def _format_bio(cls, rows: list[dict[str, Any]]) -> list[str]:
        lines = []
        for row in rows:
            raw_type = str(row.get("bio_type") or "")
            label = _BIO_TYPE_LABELS.get(raw_type, raw_type or "지표 미상")
            raw_unit = str(row.get("unit") or "")
            unit = _UNIT_LABELS.get(raw_unit, raw_unit)
            detail = row.get("detail_data")
            detail = detail if isinstance(detail, dict) else {}

            systolic = detail.get("systolic")
            diastolic = detail.get("diastolic")
            if (
                raw_type == "blood_pressure"
                and systolic is not None
                and diastolic is not None
            ):
                # 혈압은 value에 수축기만 담기므로 이완기까지 함께 표기한다.
                value = f"{systolic}/{diastolic} {unit}".strip()
            else:
                value = cls._number(
                    row.get("value"),
                    f" {unit}" if unit else "",
                    digits=1,
                )

            parts = [label, value, *cls._bio_detail_parts(raw_type, detail)]
            lines.append(cls._join(cls._date(row.get("measured_at")), parts))
        return lines

    @classmethod
    def _format_food(cls, rows: list[dict[str, Any]]) -> list[str]:
        lines = []
        for row in rows:
            raw_meal = str(row.get("meal_type") or "")
            meal = _MEAL_TYPE_LABELS.get(raw_meal, raw_meal)
            title = str(row.get("title") or "").strip()
            calories = cls._number(row.get("calories"), "kcal")
            nutrient_specs = (
                ("탄수", "carbohydrate", "g", 1),
                ("단백", "protein", "g", 1),
                ("지방", "total_fat", "g", 1),
                ("나트륨", "sodium", "mg", 0),
                ("당", "sugar", "g", 1),
            )
            nutrients = " ".join(
                f"{label} {cls._number(row.get(column), unit, digits)}"
                for label, column, unit, digits in nutrient_specs
                if row.get(column) is not None
            )
            parts = [meal, title, calories, nutrients]
            lines.append(cls._join(cls._date(row.get("consumed_at")), parts))
        return lines

    @classmethod
    def _format_water(cls, rows: list[dict[str, Any]]) -> list[str]:
        lines = []
        for row in rows:
            amount = cls._number(row.get("water_amount"), "mL")
            lines.append(cls._join(cls._date(row.get("consumed_at")), [amount]))
        return lines

    def _request(
        self,
        path: str,
        access_token: str,
    ) -> list[dict[str, Any]]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "apikey": self.publishable_key,
        }
        try:
            response = requests.get(
                f"{self.url}{path}",
                headers=headers,
                timeout=(5, 15),
            )
        except requests.RequestException as exc:
            raise SupabaseConversationError(
                "생활습관 데이터 저장소에 연결할 수 없습니다.",
                503,
            ) from exc
        if not response.ok:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            message = str(
                payload.get("message")
                or payload.get("details")
                or "생활습관 데이터 조회에 실패했습니다."
            )
            raise SupabaseConversationError(message, response.status_code)
        payload = response.json()
        return payload if isinstance(payload, list) else []
