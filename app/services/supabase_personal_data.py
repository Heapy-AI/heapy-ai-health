"""로그인 사용자 본인의 검진·생활 데이터 조회 서비스.

챗 응답 경로의 SupabaseHealthContextService·SupabaseLifestyleContextService는
질문 키워드로 조회 범위를 좁혀 LLM 프롬프트 문자열을 만든다. 이 서비스는
'내건강' 화면이 표에 그대로 뿌릴 원본 행을 질문 없이 반환한다.

작성자: 고수연
"""

from __future__ import annotations
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import RLock
from typing import Any
from urllib.parse import quote
import requests

from app.services.supabase_conversation import SupabaseConversationError


# 생활 데이터는 영역별로 조회가 나뉘므로 챗 경로와 같은 방식으로 병렬 조회한다.
_MAX_FETCH_WORKERS = 6

# (응답 키, 테이블, 추가 필터, 날짜 컬럼, select 컬럼)
_LIFESTYLE_PLAN: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "activity",
        "lifestyle_activity",
        "",
        "record_date",
        "record_date,steps,floors_climbed:floors,active_time:active_time_minutes,"
        "active_distance:distance_m,active_calories:active_calories_kcal",
    ),
    (
        "exercise",
        "lifestyle_exercise",
        "",
        "start_at",
        "record_date:start_at,exercise_type,duration_sec:duration_seconds,"
        "distance_m,calories:calories_kcal",
    ),
    (
        "bio",
        "lifestyle_bio",
        "",
        "measured_at",
        "measured_at,bio_type,heart_rate_bpm,blood_glucose_mg_dl,is_fasting,"
        "systolic_mmhg,diastolic_mmhg,pulse_bpm,weight_kg,bmi_value",
    ),
    (
        "food",
        "lifestyle_nutrition",
        "&nutrition_type=eq.food",
        "consumed_at",
        "consumed_at,meal_type,title,calories,carbohydrate,protein,total_fat,sodium,sugar",
    ),
    (
        "water",
        "lifestyle_water_intake",
        "",
        "consumed_at",
        "consumed_at,water_amount:amount_ml",
    ),
    (
        "sleep",
        "lifestyle_sleep",
        "",
        "start_at",
        "measured_at:start_at,total_sleep_minutes,awake_minutes,deep_sleep_minutes,"
        "light_sleep_minutes,rem_sleep_minutes,sleep_score",
    ),
)


class SupabasePersonalDataService:
    """RLS가 적용된 Data API로 본인 검진·생활 기록만 조회한다."""

    def __init__(
        self,
        url: str,
        publishable_key: str,
        *,
        window_days: int = 7,
        max_rows: int = 500,
    ) -> None:
        self.url = url.rstrip("/")
        self.publishable_key = publishable_key
        self.window_days = window_days
        self.max_rows = max_rows
        self._catalog: tuple[dict[str, Any], ...] = ()
        self._catalog_lock = RLock()

    @property
    def configured(self) -> bool:
        return bool(self.url and self.publishable_key)

    def get_latest_checkup(
        self,
        access_token: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """가장 최근 검진 1회의 전체 항목 수치를 반환한다."""
        if not self.configured or not access_token or not user_id:
            return None

        records = self._request(
            "/rest/v1/health_checkup_records"
            f"?user_id=eq.{quote(user_id, safe='')}"
            "&select=record_id,measured_at&order=measured_at.desc&limit=1",
            access_token,
        )
        if not records:
            return None

        record_id = str(records[0].get("record_id") or "")
        results = self._request(
            "/rest/v1/health_checkup_results"
            f"?record_id=eq.{quote(record_id, safe='')}"
            "&select=item_code,value,status"
            f"&order=item_code.asc&limit={self.max_rows}",
            access_token,
        )
        catalog = {
            str(item.get("item_code") or ""): item
            for item in self._get_catalog(access_token)
        }

        items: list[dict[str, str]] = []
        for row in results:
            item_code = str(row.get("item_code") or "")
            if not item_code:
                continue
            master = catalog.get(item_code, {})
            value = row.get("value")
            items.append(
                {
                    "item_code": item_code,
                    "item_name": str(master.get("item_name") or item_code),
                    "value": "" if value is None else str(value),
                    "unit": str(master.get("standard_unit") or ""),
                    "status": str(row.get("status") or ""),
                }
            )
        return {
            "measured_at": self._date(records[0].get("measured_at")),
            "items": items,
        }

    def get_checkup_history(
        self,
        access_token: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """AI 분석 전용으로 사용자의 전체 검진 이력을 반환한다."""
        if not self.configured or not access_token or not user_id:
            return []

        owner = quote(user_id, safe="")
        records = self._request(
            "/rest/v1/health_checkup_records"
            f"?user_id=eq.{owner}&select=record_id,measured_at"
            "&order=measured_at.asc",
            access_token,
        )
        if not records:
            return []
        catalog = {
            str(item.get("item_code") or ""): item
            for item in self._get_catalog(access_token)
        }

        def fetch_record(record: dict[str, Any]) -> dict[str, Any]:
            record_id = quote(str(record.get("record_id") or ""), safe="")
            results = self._request(
                "/rest/v1/health_checkup_results"
                f"?record_id=eq.{record_id}&select=item_code,value,status"
                f"&order=item_code.asc&limit={self.max_rows}",
                access_token,
            )
            for result in results:
                item = catalog.get(str(result.get("item_code") or ""), {})
                result["item_name"] = str(item.get("item_name") or result.get("item_code") or "")
                result["unit"] = str(item.get("standard_unit") or "")
            return {
                "date": self._date(record.get("measured_at")),
                "results": results,
            }

        return [fetch_record(record) for record in records]

    def get_lifestyle_window(
        self,
        access_token: str,
        user_id: str,
        window_days: int | None = None,
    ) -> dict[str, Any]:
        """영역별 최신 기록일 기준 window_days 구간의 생활 데이터를 반환한다."""
        if not self.configured or not access_token or not user_id:
            return self._empty_lifestyle_window()

        selected_window_days = window_days or self.window_days
        if selected_window_days <= 0:
            raise ValueError("window_days는 1 이상이어야 합니다.")
        owner = f"user_id=eq.{quote(user_id, safe='')}"
        fetched = self._fetch_in_parallel(
            [
                (
                    lambda table=table,
                    filters=owner + extra_filter,
                    date_column=date_column,
                    select=select: self._fetch_window(
                        access_token,
                        table,
                        filters,
                        date_column,
                        select,
                        selected_window_days,
                    )
                )
                for _, table, extra_filter, date_column, select in _LIFESTYLE_PLAN
            ]
        )

        window: dict[str, Any] = {"window_days": selected_window_days}
        for plan, domain in zip(_LIFESTYLE_PLAN, fetched):
            window[plan[0]] = self._normalize_domain(plan[0], domain)
        return window

    def _empty_lifestyle_window(self) -> dict[str, Any]:
        """Supabase 미설정 환경에서도 응답 형태를 유지한다."""
        window: dict[str, Any] = {"window_days": self.window_days}
        for plan in _LIFESTYLE_PLAN:
            window[plan[0]] = {"since": "", "until": "", "rows": []}
        return window

    @staticmethod
    def _normalize_domain(domain_name: str, domain: dict[str, Any]) -> dict[str, Any]:
        """실제 Supabase 컬럼을 화면 응답 계약으로 변환한다."""
        if domain_name not in {"bio", "sleep"}:
            return domain

        if domain_name == "sleep":
            return {
                **domain,
                "rows": [
                    {
                        "measured_at": row.get("measured_at", ""),
                        "bio_type": "sleep",
                        "value": (
                            float(row["total_sleep_minutes"]) / 60
                            if row.get("total_sleep_minutes") is not None
                            else None
                        ),
                        "unit": "hour",
                        "detail_data": {
                            key: row.get(key)
                            for key in (
                                "awake_minutes",
                                "deep_sleep_minutes",
                                "light_sleep_minutes",
                                "rem_sleep_minutes",
                                "sleep_score",
                            )
                        },
                    }
                    for row in domain["rows"]
                ],
            }

        normalized_rows: list[dict[str, Any]] = []
        for row in domain["rows"]:
            bio_type = str(row.get("bio_type") or "")
            value: Any = None
            unit = ""
            detail_data: dict[str, Any] = {}
            if bio_type == "heart_rate":
                value, unit = row.get("heart_rate_bpm"), "bpm"
            elif bio_type == "blood_glucose":
                value, unit = row.get("blood_glucose_mg_dl"), "mg/dL"
                detail_data["fasting"] = row.get("is_fasting")
            elif bio_type == "blood_pressure":
                value, unit = row.get("systolic_mmhg"), "mmHg"
                detail_data.update(
                    systolic=row.get("systolic_mmhg"),
                    diastolic=row.get("diastolic_mmhg"),
                    pulse=row.get("pulse_bpm"),
                )
            elif bio_type == "weight":
                value, unit = row.get("weight_kg"), "kg"
            elif bio_type == "bmi":
                value = row.get("bmi_value")
            normalized_rows.append(
                {
                    "measured_at": row.get("measured_at", ""),
                    "bio_type": bio_type,
                    "value": value,
                    "unit": unit,
                    "detail_data": detail_data,
                }
            )
        return {**domain, "rows": normalized_rows}

    def _fetch_window(
        self,
        access_token: str,
        table: str,
        filters: str,
        date_column: str,
        select: str,
        window_days: int,
    ) -> dict[str, Any]:
        """보유한 최신 기록일을 기준점으로 window_days 구간만 조회한다.

        오늘 날짜로 자르지 않는 이유는 config의 생활습관 조회 정책과 같다.
        기기 연동이 끊겨 데이터가 낡아도 마지막으로 남은 기록은 보여야 한다.
        """
        latest_rows = self._request(
            f"/rest/v1/{table}?{filters}&select={date_column}"
            f"&order={date_column}.desc&limit=1",
            access_token,
        )
        if not latest_rows:
            return {"since": "", "until": "", "rows": []}

        until = self._date(latest_rows[0].get(date_column))
        try:
            since = (
                date.fromisoformat(until) - timedelta(days=window_days - 1)
            ).isoformat()
        except ValueError:
            return {"since": "", "until": "", "rows": []}

        rows = self._request(
            f"/rest/v1/{table}?{filters}&select={select}"
            f"&{date_column}=gte.{since}"
            f"&order={date_column}.desc&limit={self.max_rows}",
            access_token,
        )
        return {"since": since, "until": until, "rows": rows}

    def _get_catalog(self, access_token: str) -> tuple[dict[str, Any], ...]:
        """검사 항목명·단위 마스터를 프로세스 수명 동안 한 번만 읽는다."""
        with self._catalog_lock:
            if self._catalog:
                return self._catalog
            rows = self._request(
                "/rest/v1/master_checkup_item"
                "?select=item_code,item_name,standard_unit"
                "&order=item_code.asc",
                access_token,
            )
            self._catalog = tuple(rows)
            return self._catalog

    @staticmethod
    def _date(value: Any) -> str:
        """timestamp와 date 컬럼을 모두 YYYY-MM-DD로 맞춘다."""
        return str(value or "").strip()[:10]

    @staticmethod
    def _fetch_in_parallel(
        fetchers: list[Callable[[], dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """조회 순서를 유지한 채 병렬로 실행한다.

        한 영역이라도 실패하면 화면이 불완전해지므로 예외를 그대로 올린다.
        """
        if len(fetchers) <= 1:
            return [fetch() for fetch in fetchers]
        with ThreadPoolExecutor(
            max_workers=min(len(fetchers), _MAX_FETCH_WORKERS)
        ) as executor:
            return list(executor.map(lambda fetch: fetch(), fetchers))

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
            print(f"[personal-data] Supabase 요청 실패 path={path} error={type(exc).__name__}: {exc}")
            raise SupabaseConversationError(
                "개인 데이터 저장소에 연결할 수 없습니다.",
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
                or "개인 데이터 조회에 실패했습니다."
            )
            print(f"[personal-data] Supabase 응답 오류 path={path} status={response.status_code} message={message}")
            raise SupabaseConversationError(message, response.status_code)
        payload = response.json()
        return payload if isinstance(payload, list) else []
