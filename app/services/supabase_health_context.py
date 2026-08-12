"""인증된 사용자의 질문 관련 건강검진 컨텍스트 조회 서비스.

작성자: 김진우
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import RLock
from typing import Any
from urllib.parse import quote

import requests

from app.services.supabase_conversation import SupabaseConversationError


_TREND_KEYWORDS = ("추이", "변화", "변했", "높아졌", "낮아졌", "과거", "예전", "이전")
_CHECKUP_KEYWORDS = ("건강검진", "검진 결과", "검사 결과", "건강 상태")
_NON_NORMAL_KEYWORDS = ("이상 항목", "경계 항목", "주의 항목", "문제 있는", "안 좋은")
_NON_NORMAL_PATTERN = re.compile(
    r"(?:이상|경계|주의|문제).{0,4}(?:수치|결과|항목)|(?:비정상|안\s*좋)"
)


@dataclass(frozen=True)
class PersonalHealthContext:
    """LLM에 전달할 최소 범위의 개인 건강검진 컨텍스트.

    작성자: 김진우
    """

    prompt_text: str
    item_codes: tuple[str, ...]
    result_count: int
    includes_history: bool


class SupabaseHealthContextService:
    """RLS가 적용된 Data API로 본인 검진 결과만 조회한다.

    작성자: 김진우
    """

    def __init__(self, url: str, publishable_key: str) -> None:
        self.url = url.rstrip("/")
        self.publishable_key = publishable_key
        self._catalog: tuple[dict[str, Any], ...] = ()
        self._catalog_lock = RLock()

    @property
    def configured(self) -> bool:
        return bool(self.url and self.publishable_key)

    def get_relevant_context(
        self,
        access_token: str,
        user_id: str,
        question: str,
        resolved_terms: tuple[dict[str, Any], ...] = (),
    ) -> PersonalHealthContext | None:
        """질문에 해당하는 검사항목만 조회해 프롬프트 컨텍스트로 반환한다."""
        if not self.configured or not access_token or not user_id:
            return None

        catalog = self._get_catalog(access_token)
        item_codes, generic_checkup, non_normal_only = self._select_item_codes(
            question,
            catalog,
            resolved_terms,
        )
        if not item_codes and not generic_checkup:
            return None

        profile = self._get_profile(access_token, user_id)
        records = self._get_records(access_token, user_id)
        if not records:
            return None

        includes_history = any(keyword in question for keyword in _TREND_KEYWORDS)
        selected_records = records if includes_history else records[:1]
        results = self._get_results(
            access_token,
            selected_records,
            item_codes,
        )
        if non_normal_only:
            results = [row for row in results if str(row.get("status")) != "정상"]
        if not results:
            return None
        catalog_by_code = {
            str(item.get("item_code", "")): item
            for item in catalog
        }
        results = [
            {**catalog_by_code.get(str(row.get("item_code", "")), {}), **row}
            for row in results
        ]

        return PersonalHealthContext(
            prompt_text=self._format_prompt_context(profile, selected_records, results),
            item_codes=tuple(sorted({str(row["item_code"]) for row in results})),
            result_count=len(results),
            includes_history=includes_history,
        )

    def _get_catalog(self, access_token: str) -> tuple[dict[str, Any], ...]:
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

    def _get_profile(self, access_token: str, user_id: str) -> dict[str, Any]:
        encoded_user_id = quote(user_id, safe="")
        rows = self._request(
            "/rest/v1/users"
            f"?user_id=eq.{encoded_user_id}"
            "&select=name,birth_date,sex,chronic_conditions&limit=1",
            access_token,
        )
        return rows[0] if rows else {}

    def _get_records(self, access_token: str, user_id: str) -> list[dict[str, Any]]:
        encoded_user_id = quote(user_id, safe="")
        return self._request(
            "/rest/v1/health_checkup_records"
            f"?user_id=eq.{encoded_user_id}"
            "&select=record_id,measured_at&order=measured_at.desc",
            access_token,
        )

    def _get_results(
        self,
        access_token: str,
        records: list[dict[str, Any]],
        item_codes: set[str],
    ) -> list[dict[str, Any]]:
        record_ids = [str(row.get("record_id", "")) for row in records]
        record_filter = quote(",".join(record_ids), safe=",")
        path = (
            "/rest/v1/health_checkup_results"
            f"?record_id=in.({record_filter})"
            "&select=result_id,record_id,item_code,value,status"
        )
        if item_codes:
            item_filter = quote(",".join(sorted(item_codes)), safe=",")
            path += f"&item_code=in.({item_filter})"
        return self._request(path, access_token)

    @staticmethod
    def _select_item_codes(
        question: str,
        catalog: tuple[dict[str, Any], ...],
        resolved_terms: tuple[dict[str, Any], ...] = (),
    ) -> tuple[set[str], bool, bool]:
        normalized = re.sub(r"[^0-9a-z가-힣]", "", question.casefold())
        upper_question = question.upper()
        catalog_codes = {
            str(item.get("item_code", "")).upper()
            for item in catalog
            if str(item.get("item_code", "")).strip()
        }
        selected = SupabaseHealthContextService._codes_from_resolved_terms(
            resolved_terms,
            catalog,
            catalog_codes,
        )

        for item in catalog:
            code = str(item.get("item_code", "")).upper()
            item_name = re.sub(
                r"[^0-9a-z가-힣]",
                "",
                str(item.get("item_name", "")).casefold(),
            )
            if code and re.search(
                rf"(?<![A-Z0-9_]){re.escape(code)}(?![A-Z0-9_])",
                upper_question,
            ):
                selected.add(code)
            elif len(item_name) >= 2 and item_name in normalized:
                selected.add(code)

        generic_checkup = any(keyword in question for keyword in _CHECKUP_KEYWORDS)
        non_normal_only = any(
            keyword in question for keyword in _NON_NORMAL_KEYWORDS
        ) or bool(_NON_NORMAL_PATTERN.search(question))
        return selected, generic_checkup, non_normal_only

    @staticmethod
    def _codes_from_resolved_terms(
        resolved_terms: tuple[dict[str, Any], ...],
        catalog: tuple[dict[str, Any], ...],
        catalog_codes: set[str],
    ) -> set[str]:
        """용어집의 표준키를 검진 항목 코드로 변환한다.

        표준키가 검진 코드와 같으면 그대로 사용한다. 혈압처럼 하나의 표준명이
        여러 마스터 항목을 설명하는 경우에는 용어집 표준명과 마스터 항목명을
        비교하여 동적으로 확장한다.

        작성자: 김진우
        """
        selected: set[str] = set()
        for term in resolved_terms:
            term_type = str(term.get("term_type", "")).strip().upper()
            if term_type not in {"SCREENING", "ALIAS_GROUP"}:
                continue
            keys = {
                str(key).strip().upper()
                for key in term.get("canonical_keys", ())
                if str(key).strip()
            }
            canonical_key = str(term.get("canonical_key", "")).strip().upper()
            if canonical_key and not canonical_key.startswith("ALIAS_GROUP:"):
                keys.add(canonical_key)
            selected.update(keys & catalog_codes)

            phrases = (
                str(term.get("canonical_name", "")),
                str(term.get("matched_alias", "")),
            )
            for phrase in phrases:
                selected.update(
                    SupabaseHealthContextService._codes_described_by_phrase(
                        phrase,
                        catalog,
                    )
                )
        return selected

    @staticmethod
    def _codes_described_by_phrase(
        phrase: str,
        catalog: tuple[dict[str, Any], ...],
    ) -> set[str]:
        """표준명에 포함된 마스터 항목명을 코드로 연결한다.

        작성자: 김진우
        """
        phrase_normalized = re.sub(r"[^0-9a-z가-힣]", "", phrase.casefold())
        if len(phrase_normalized) < 2:
            return set()
        phrase_tokens = {
            token
            for token in re.findall(r"[0-9a-z]+|[가-힣]+", phrase.casefold())
            if len(token) >= 2
        }
        selected: set[str] = set()
        for item in catalog:
            code = str(item.get("item_code", "")).upper()
            item_name = str(item.get("item_name", ""))
            item_normalized = re.sub(
                r"[^0-9a-z가-힣]",
                "",
                item_name.casefold(),
            )
            item_tokens = {
                token
                for token in re.findall(r"[0-9a-z]+|[가-힣]+", item_name.casefold())
                if len(token) >= 2
            }
            if code and (
                item_normalized in phrase_normalized
                or phrase_normalized in item_normalized
                or (item_tokens and item_tokens.issubset(phrase_tokens))
            ):
                selected.add(code)
        return selected

    @staticmethod
    def _format_prompt_context(
        profile: dict[str, Any],
        records: list[dict[str, Any]],
        results: list[dict[str, Any]],
    ) -> str:
        record_dates = {
            str(record.get("record_id")): str(record.get("measured_at", ""))
            for record in records
        }
        chronic_conditions = profile.get("chronic_conditions") or []
        profile_lines = [
            f"- 사용자 이름: {profile.get('name', '확인되지 않음')}",
            f"- 성별: {profile.get('sex', '확인되지 않음')}",
            f"- 생년월일: {profile.get('birth_date', '확인되지 않음')}",
            "- 등록된 만성질환: "
            + (", ".join(map(str, chronic_conditions)) if chronic_conditions else "없음"),
        ]
        result_lines = []
        for row in sorted(
            results,
            key=lambda item: (
                record_dates.get(str(item.get("record_id")), ""),
                str(item.get("item_code", "")),
            ),
            reverse=True,
        ):
            result_lines.append(
                "- {date} | {name}({code}) | 값: {value}{unit} | DB 상태: {status}".format(
                    date=record_dates.get(str(row.get("record_id")), "날짜 미상"),
                    name=row.get("item_name") or row.get("item_code", ""),
                    code=row.get("item_code", ""),
                    value=row.get("value", ""),
                    unit=(
                        f" {row.get('standard_unit')}"
                        if row.get("standard_unit")
                        else ""
                    ),
                    status=row.get("status", "미분류"),
                )
            )
        return "\n".join(
            [
                "[인증된 사용자 건강검진 정보]",
                *profile_lines,
                "[질문 관련 건강검진 결과]",
                *result_lines,
            ]
        )

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
                "건강검진 데이터 저장소에 연결할 수 없습니다.",
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
                or "건강검진 데이터 조회에 실패했습니다."
            )
            raise SupabaseConversationError(message, response.status_code)
        payload = response.json()
        return payload if isinstance(payload, list) else []
