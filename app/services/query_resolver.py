"""RDB 표준 의료용어를 이용한 질문 정규화.

검색 임베딩에 오타가 섞인 원문만 넣으면 짧은 의약품명·질환명은 쉽게
엉뚱한 청크로 밀릴 수 있다. 이 모듈은 질문에서 의료용어 후보를 추출하고,
RDB가 반환한 정확명/별칭/유사도 결과를 이용해 검색용 질문을 재작성한다.

직접 RDB가 연결되지 않아도 Supabase Data API 설정이 있으면 의료용어 일괄 검색 RPC를
사용한다. 두 저장소가 모두 없을 때만 ``NullMedicalTermRepository``로 기존 검색을 유지한다.
"""
from __future__ import annotations

import re
import logging
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Protocol

import requests


LOGGER = logging.getLogger(__name__)


TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]+")
HANGUL_INITIALS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
HANGUL_JAMO_INITIALS = "ᄀᄁᄂᄃᄄᄅᄆᄇᄈᄉᄊᄋᄌᄍᄎᄏᄐᄑᄒ"
HANGUL_JAMO_TO_COMPAT = str.maketrans(HANGUL_JAMO_INITIALS, HANGUL_INITIALS)
HANGUL_TENSE_INITIALS_TO_BASE = str.maketrans("ㄲㄸㅃㅆㅉ", "ㄱㄷㅂㅅㅈ")
HANGUL_MEDIALS = (
    "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
)
HANGUL_FINALS = (
    "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ",
    "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ",
    "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)
KOREAN_PARTICLES = (
    "으로부터",
    "에서부터",
    "으로",
    "에게",
    "까지",
    "부터",
    "처럼",
    "보다",
    "에서",
    "에게",
    "하고",
    "이나",
    "이랑",
    "랑",
    "이",
    "가",
    "은",
    "는",
    "을",
    "를",
    "에",
    "의",
    "로",
    "와",
    "과",
    "도",
    "만",
)
MEDICATION_QUERY_LEXEMES = frozenset(
    {"약", "약물", "약품", "복약", "복용", "처방"}
)
MEDICAL_QUERY_CONTEXT_LEXEMES = frozenset(
    {"건강", "검사", "검진", "결과", "상태", "수치", "정도", "항목", "이상"}
)
# 의료용어 목록이 아니라 한국어 문장 성분을 판별하기 위한 일반적인
# 활용 어미 규칙이다. 완성형 동사·형용사 어절이 초성 부분열만으로
# 의료용어 후보가 되는 것을 막고, 해당 어절은 검색 문맥으로 보존한다.
PREDICATE_ENDING_RE = re.compile(
    r"(?:았|었|였|겠|했|해|돼|되|워|와|아|어|요|죠|네|까|나|게|고|줘|지)$"
)


def normalize_search_text(value: str) -> str:
    """공백·구두점 차이를 제거한 비교용 의료용어 키를 만든다.

    호환 자모(예: ``ㅂㄹㅍ``)도 남겨 초성 검색 후보로 사용할 수 있게 한다.
    """
    normalized = _normalize_korean_input(value)
    return re.sub(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ]+", "", normalized)


def is_medical_query_context(value: str) -> bool:
    """일반 문맥어만 이어진 표현인지 판별한다.

    ``검진 결과``나 ``이상 수치``처럼 여러 문맥어가 붙은 표현도 의료용어
    부분 일치 후보로 승격하지 않는다. 검사항목명 목록은 Supabase 용어집이
    계속 담당하므로 애플리케이션에 항목별 예외를 추가하지 않는다.

    작성자: 김진우
    """
    normalized = normalize_search_text(value)
    if not normalized:
        return False

    reachable = {0}
    for start in range(len(normalized)):
        if start not in reachable:
            continue
        for lexeme in MEDICAL_QUERY_CONTEXT_LEXEMES:
            if normalized.startswith(lexeme, start):
                reachable.add(start + len(lexeme))
    return len(normalized) in reachable


def _normalize_korean_input(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return normalized.translate(HANGUL_JAMO_TO_COMPAT)


def korean_initials(value: str) -> str:
    """한글 음절을 초성열로 변환한다.

    ``브르폔``과 ``부루펜``처럼 모음·종성이 흔들린 입력, 그리고
    ``ㅂㄹㅍ``처럼 초성만 입력한 경우를 같은 검색 후보로 만들기 위한
    보조 키다. 한글 음절의 유니코드 조합 규칙만 사용하므로 외부 패키지가
    필요하지 않다.
    """
    normalized = _normalize_korean_input(value)
    initials: list[str] = []
    for character in normalized:
        if character in HANGUL_INITIALS:
            initials.append(character)
            continue
        codepoint = ord(character)
        if 0xAC00 <= codepoint <= 0xD7A3:
            initials.append(HANGUL_INITIALS[(codepoint - 0xAC00) // 588])
    return "".join(initials).translate(HANGUL_TENSE_INITIALS_TO_BASE)


def is_korean_initial_input(value: str) -> bool:
    """입력이 실제 한글 음절이 아닌 초성 자모열인지 판별한다."""
    normalized = _normalize_korean_input(value)
    return bool(normalized) and all(character in HANGUL_INITIALS for character in normalized)


def is_likely_predicate(value: str) -> bool:
    """완성형 어절이 동사·형용사 활용형일 가능성을 판별한다.

    특정 의료용어를 열거하지 않고 문법적 활용 어미만 사용한다. ``나왔어``,
    ``낮게``, ``알려줘`` 같은 어절은 의료용어 후보가 아니라 질문 문맥으로
    전달되어야 한다. DB alias와 정확히 일치하는 경우에는 resolver가 이
    판별보다 우선하므로 증상 표현 alias도 검색할 수 있다.
    """
    normalized = _normalize_korean_input(value).replace(" ", "")
    if is_korean_initial_input(normalized):
        return False
    syllables = korean_syllable_components(normalized)
    return len(syllables) >= 3 and bool(PREDICATE_ENDING_RE.search(normalized))


def korean_syllable_components(value: str) -> tuple[tuple[str, str, str], ...]:
    """한글 음절을 초성·중성·종성 구성요소로 분해한다."""
    normalized = _normalize_korean_input(value)
    components: list[tuple[str, str, str]] = []
    for character in normalized:
        codepoint = ord(character)
        if not 0xAC00 <= codepoint <= 0xD7A3:
            continue
        offset = codepoint - 0xAC00
        initial = HANGUL_INITIALS[offset // 588]
        medial = HANGUL_MEDIALS[(offset % 588) // 28]
        final = HANGUL_FINALS[offset % 28]
        components.append((initial, medial, final))
    return tuple(components)


def korean_syllable_shape_similarity(left: str, right: str) -> float:
    """같은 초성열을 가진 음절 오타의 구성 유사도를 계산한다."""
    left_components = korean_syllable_components(left)
    right_components = korean_syllable_components(right)
    if not left_components or len(left_components) != len(right_components):
        return 0.0

    score = 0.0
    for left_component, right_component in zip(left_components, right_components):
        if left_component[0] == right_component[0]:
            score += 0.4
        if left_component[1] == right_component[1]:
            score += 0.4
        if left_component[2] == right_component[2]:
            score += 0.2
    return score / len(left_components)


def is_syllable_initial_typo(value: str, alias: str) -> bool:
    """초성열은 같지만 음절이 일부 흔들린 다음절 입력인지 판별한다."""
    query_initials = korean_initials(value)
    alias_initials = korean_initials(alias)
    components = korean_syllable_components(value)
    return (
        len(components) >= 3
        and query_initials == alias_initials
        and korean_syllable_shape_similarity(value, alias) >= 0.55
    )


def korean_initial_substrings(value: str) -> tuple[tuple[str, str], ...]:
    """한글 연속 구간에서 길이 2 이상의 초성 부분열을 만든다.

    용어 목록에 ``혈압`` alias를 별도로 넣지 않아도 ``고혈압``에서
    ``혈압 → ㅎㅇ`` 같은 검색 후보를 일반 규칙으로 파생할 수 있다.
    반환된 표면형은 확인 질문에 표시할 후보이며, 표준용어 자체는
    ``canonical_name``을 그대로 사용한다.
    """
    normalized = _normalize_korean_input(value)
    runs: list[list[tuple[str, str]]] = []
    current_run: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal current_run
        if len(current_run) >= 2:
            runs.append(current_run)
        current_run = []

    for character in normalized:
        if character in HANGUL_INITIALS:
            current_run.append(
                (character.translate(HANGUL_TENSE_INITIALS_TO_BASE), character)
            )
            continue
        codepoint = ord(character)
        if 0xAC00 <= codepoint <= 0xD7A3:
            initial = HANGUL_INITIALS[(codepoint - 0xAC00) // 588]
            current_run.append(
                (initial.translate(HANGUL_TENSE_INITIALS_TO_BASE), character)
            )
            continue
        flush()
    flush()

    forms: list[tuple[str, str]] = []
    for run in runs:
        for start in range(len(run)):
            for end in range(start + 2, len(run) + 1):
                initial_key = "".join(item[0] for item in run[start:end])
                surface = "".join(item[1] for item in run[start:end])
                forms.append((initial_key, surface))
    return tuple(forms)


@dataclass(frozen=True)
class MedicalTermMatch:
    """RDB가 반환한 표준용어 후보 한 건."""

    canonical_key: str
    canonical_name: str
    term_type: str
    matched_alias: str
    score: float
    match_kind: str
    priority: int = 0
    canonical_keys: tuple[str, ...] = ()


class MedicalTermRepository(Protocol):
    """의료용어 후보를 검색하는 저장소 인터페이스."""

    def search(self, query: str, *, limit: int = 8) -> Sequence[MedicalTermMatch]:
        """질문 또는 질문 일부와 가까운 표준용어를 반환한다."""


class NullMedicalTermRepository:
    """RDB 미설정 환경에서 사용하는 no-op 저장소."""

    def search(self, query: str, *, limit: int = 8) -> Sequence[MedicalTermMatch]:
        return ()

    def search_many(
        self,
        queries: Sequence[str],
        *,
        limit: int = 8,
    ) -> dict[str, Sequence[MedicalTermMatch]]:
        return {query: () for query in queries}


class InMemoryMedicalTermRepository:
    """테스트와 로컬 품질 점검용 작은 용어 저장소.

    운영 데이터의 기준은 이 클래스가 아니라 RDB다. 다만 검색 정규화 규칙을
    외부 서비스 없이 재현할 수 있어 회귀 테스트에서 사용한다.
    """

    def __init__(self, terms: Iterable[dict[str, Any] | MedicalTermMatch]) -> None:
        self._terms: list[MedicalTermMatch] = []
        for term in terms:
            if isinstance(term, MedicalTermMatch):
                self._terms.append(term)
                continue
            aliases = term.get("aliases", [term.get("canonical_name", "")])
            canonical_name = str(term.get("canonical_name", ""))
            for alias_record in aliases:
                if isinstance(alias_record, dict):
                    alias = alias_record.get("display") or alias_record.get("alias_display")
                    priority = int(alias_record.get("priority", 0) or 0)
                else:
                    alias = alias_record
                    priority = int(
                        term.get("alias_priority", 100)
                        if normalize_search_text(str(alias))
                        == normalize_search_text(canonical_name)
                        else term.get("alias_priority", 0)
                    )
                if not alias:
                    continue
                self._terms.append(
                    MedicalTermMatch(
                        canonical_key=str(term["canonical_key"]),
                        canonical_name=canonical_name,
                        term_type=str(term.get("term_type", "OTHER")),
                        matched_alias=str(alias),
                        score=0.0,
                        match_kind="fuzzy",
                        priority=priority,
                    )
                )

    @lru_cache(maxsize=2048)
    def search(self, query: str, *, limit: int = 8) -> Sequence[MedicalTermMatch]:
        query_key = normalize_search_text(query)
        query_initials = korean_initials(query)
        query_is_initial_input = is_korean_initial_input(query)
        if len(query_key) < 2 and len(query_initials) < 2:
            return ()

        ranked: list[MedicalTermMatch] = []
        query_fragments = (query, *TOKEN_RE.findall(query))
        # 각 alias마다 전체 alias를 다시 훑던 O(N²) 오타 방지 계산을
        # query 단위의 O(N) 후보 계산으로 줄인다.
        syllable_typo_alias_keys: set[str] = set()
        for fragment in query_fragments:
            if len(normalize_search_text(fragment)) < 3:
                continue
            for other in self._terms:
                if is_syllable_initial_typo(fragment, other.matched_alias):
                    syllable_typo_alias_keys.add(
                        normalize_search_text(other.matched_alias)
                    )
        longer_typo_length = max(
            (len(alias_key) for alias_key in syllable_typo_alias_keys),
            default=0,
        )
        for term in self._terms:
            alias_key = normalize_search_text(term.matched_alias)
            if len(alias_key) < 2:
                continue
            alias_initials = korean_initials(term.matched_alias)
            # 짧은 alias(예: "당뇨")가 더 긴 표준 alias의 음절 오타(예:
            # "당뇨뼝" → "당뇨병")를 substring 점수로 가로채지 않게 한다.
            # 용어명은 코드에 등록하지 않고 현재 repository의 alias 전체를
            # 비교하므로, 어떤 의료용어 조합에도 같은 규칙이 적용된다.
            longer_syllable_typo_exists = longer_typo_length > len(alias_key)
            initial_substring_match = next(
                (
                    (initial_key, surface)
                    for initial_key, surface in korean_initial_substrings(term.matched_alias)
                    if initial_key == query_initials
                ),
                None,
            )
            matched_alias = term.matched_alias
            if alias_key == query_key:
                score, kind = 1.0, "exact"
            elif (
                (alias_key in query_key or query_key in alias_key)
                and not longer_syllable_typo_exists
            ):
                score, kind = 0.96, "substring"
            elif (
                len(query_initials) >= 2
                and alias_initials == query_initials
                and (
                    query_is_initial_input
                    or is_syllable_initial_typo(query, term.matched_alias)
                )
            ):
                score = 0.97 if query_is_initial_input else 0.90
                kind = "initials"
            elif (
                len(query_initials) >= 2
                and initial_substring_match is not None
                and (
                    query_is_initial_input
                    or is_syllable_initial_typo(query, initial_substring_match[1])
                )
            ):
                score = 0.88 if query_is_initial_input else 0.86
                kind = "initials_substring"
                matched_alias = initial_substring_match[1]
            else:
                score = SequenceMatcher(None, alias_key, query_key).ratio()
                kind = "fuzzy"
            ranked.append(
                MedicalTermMatch(
                    canonical_key=term.canonical_key,
                    canonical_name=term.canonical_name,
                    term_type=term.term_type,
                    matched_alias=matched_alias,
                    score=score,
                    match_kind=kind,
                    priority=term.priority,
                )
            )
        ranked.sort(
            key=lambda item: (
                -item.score,
                -item.priority,
                -len(normalize_search_text(item.matched_alias)),
                item.canonical_key,
            )
        )
        return tuple(ranked[: max(1, min(limit, 20))])

    def search_many(
        self,
        queries: Sequence[str],
        *,
        limit: int = 8,
    ) -> dict[str, Sequence[MedicalTermMatch]]:
        return {query: self.search(query, limit=limit) for query in dict.fromkeys(queries)}


class RdbMedicalTermRepository:
    """PostgreSQL 저장소 어댑터.

    SQL은 ``database/migrations/001_medical_term_search.sql``의
    ``search_medical_terms`` 함수를 호출한다. psycopg는 메서드 호출 시
    지연 import하므로 RDB를 사용하지 않는 테스트 환경도 계속 실행된다.
    """

    def __init__(self, dsn: str, *, connect_factory=None) -> None:
        if not dsn.strip():
            raise ValueError("RDB DSN은 비어 있을 수 없습니다.")
        self._dsn = dsn
        self._connect_factory = connect_factory

    def search(self, query: str, *, limit: int = 8) -> Sequence[MedicalTermMatch]:
        if len(normalize_search_text(query)) < 2:
            return ()

        connect = self._connect_factory
        if connect is None:
            try:
                import psycopg
            except ImportError as exc:  # pragma: no cover - 운영 설치 누락 안내
                raise RuntimeError(
                    "RDB_DSN을 사용하려면 psycopg[binary]를 설치해야 합니다."
                ) from exc
            connect = psycopg.connect

        return self.search_many([query], limit=limit).get(query, ())

    def search_many(
        self,
        queries: Sequence[str],
        *,
        limit: int = 8,
    ) -> dict[str, Sequence[MedicalTermMatch]]:
        """질문의 토큰 후보를 한 번의 DB 연결로 조회한다."""
        unique_queries = [
            query
            for query in dict.fromkeys(queries)
            if len(normalize_search_text(query)) >= 2
        ]
        if not unique_queries:
            return {query: () for query in queries}

        connect = self._connect_factory
        if connect is None:
            try:
                import psycopg
            except ImportError as exc:  # pragma: no cover - 운영 설치 누락 안내
                raise RuntimeError(
                    "RDB_DSN을 사용하려면 psycopg[binary]를 설치해야 합니다."
                ) from exc
            connect = psycopg.connect

        with connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                "SELECT q.input_query, r.canonical_key, r.canonical_name, "
                    "r.term_type, r.matched_alias, r.match_score, r.match_kind, "
                    "r.match_priority "
                    "FROM unnest(%s::text[]) AS q(input_query) "
                    "CROSS JOIN LATERAL search_medical_terms(q.input_query, %s) AS r",
                    (unique_queries, max(1, min(limit, 20))),
                )
                rows = cursor.fetchall()

        grouped: dict[str, list[MedicalTermMatch]] = {
            query: [] for query in unique_queries
        }
        for row in rows:
            grouped[str(row[0])].append(
                MedicalTermMatch(
                    canonical_key=str(row[1]),
                    canonical_name=str(row[2]),
                    term_type=str(row[3]),
                    matched_alias=str(row[4]),
                    score=float(row[5]),
                    match_kind=str(row[6]),
                    priority=int(row[7] or 0),
                )
            )
        return {query: tuple(grouped.get(query, ())) for query in queries}


class SupabaseMedicalTermRepository:
    """Supabase Data API의 의료용어 일괄 검색 RPC 어댑터."""

    def __init__(self, url: str, publishable_key: str, *, request_factory=None) -> None:
        if not url.strip() or not publishable_key.strip():
            raise ValueError("Supabase 의료용어 검색 설정이 필요합니다.")
        self._url = url.rstrip("/")
        self._publishable_key = publishable_key
        self._request_factory = request_factory or requests.post

    def search(self, query: str, *, limit: int = 8) -> Sequence[MedicalTermMatch]:
        return self.search_many([query], limit=limit).get(query, ())

    def search_many(
        self,
        queries: Sequence[str],
        *,
        limit: int = 8,
    ) -> dict[str, Sequence[MedicalTermMatch]]:
        """여러 의료용어 후보를 한 번의 Supabase RPC로 조회한다."""
        unique_queries = [
            query
            for query in dict.fromkeys(queries)
            if len(normalize_search_text(query)) >= 2
        ]
        grouped: dict[str, list[MedicalTermMatch]] = {
            query: [] for query in unique_queries
        }
        if not unique_queries:
            return {query: () for query in queries}

        try:
            response = self._request_factory(
                f"{self._url}/rest/v1/rpc/search_medical_terms_batch",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "apikey": self._publishable_key,
                },
                json={
                    "p_queries": unique_queries,
                    "p_limit": max(1, min(limit, 20)),
                },
                timeout=(5, 15),
            )
            response.raise_for_status()
            rows = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError("Supabase 의료용어 검색에 실패했습니다.") from exc

        for row in rows if isinstance(rows, list) else []:
            input_query = str(row.get("input_query", ""))
            if input_query not in grouped:
                continue
            grouped[input_query].append(
                MedicalTermMatch(
                    canonical_key=str(row.get("canonical_key", "")),
                    canonical_name=str(row.get("canonical_name", "")),
                    term_type=str(row.get("term_type", "")),
                    matched_alias=str(row.get("matched_alias", "")),
                    score=float(row.get("match_score", 0.0) or 0.0),
                    match_kind=str(row.get("match_kind", "")),
                    priority=int(row.get("match_priority", 0) or 0),
                )
            )
        return {query: tuple(grouped.get(query, ())) for query in queries}


@dataclass(frozen=True)
class ResolvedQueryTerm:
    """질문 안의 입력 표현과 RDB 표준용어의 연결 결과."""

    source_text: str
    canonical_key: str
    canonical_name: str
    term_type: str
    score: float
    match_kind: str
    matched_alias: str = ""
    canonical_keys: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        canonical_keys = self.canonical_keys or (self.canonical_key,)
        return {
            "input": self.source_text,
            "canonical_key": self.canonical_key,
            "canonical_name": self.canonical_name,
            "term_type": self.term_type,
            "score": round(self.score, 4),
            "match_kind": self.match_kind,
            "matched_alias": self.matched_alias,
            "canonical_keys": list(canonical_keys),
        }


@dataclass(frozen=True)
class QueryResolution:
    """검색용 질문과 사용자 입력 용어의 정규화 결과."""

    original_query: str
    resolved_query: str
    terms: tuple[ResolvedQueryTerm, ...] = ()
    needs_confirmation: bool = False
    confirmation_question: str = ""
    domain_hint: str = ""
    resolution_status: str = "NO_MATCH"

    @property
    def changed(self) -> bool:
        return self.original_query != self.resolved_query or bool(self.terms)

    def as_dict(self) -> dict[str, Any]:
        return {
            "original_query": self.original_query,
            "resolved_query": self.resolved_query,
            "terms": [term.as_dict() for term in self.terms],
            "needs_confirmation": self.needs_confirmation,
            "confirmation_question": self.confirmation_question,
            "domain_hint": self.domain_hint,
            "resolution_status": self.resolution_status,
        }


def build_confirmed_query_resolution(
    original_question: str,
    confirmed_term: dict[str, Any],
) -> QueryResolution:
    """사용자가 확인한 후보를 재검색 없이 확정한다.

    확인 이후 원문을 resolver에 다시 넣지 않는다. 그래야 원문 안의 일반
    서술어가 새로운 의료용어 후보로 승격되어 연쇄 확인을 만들지 않는다.
    """
    original = str(original_question or "").strip()
    source = str(confirmed_term.get("input", "")).strip()
    canonical = str(
        confirmed_term.get("canonical_name")
        or confirmed_term.get("matched_alias")
        or ""
    ).strip()
    if not canonical:
        return QueryResolution(original, original)

    if source and source in original:
        resolved = original.replace(source, canonical, 1)
    elif normalize_search_text(canonical) in normalize_search_text(original):
        resolved = original
    else:
        resolved = f"{original} {canonical}".strip()

    term_type = str(confirmed_term.get("term_type", "OTHER"))
    term = ResolvedQueryTerm(
        source_text=source or canonical,
        canonical_key=str(confirmed_term.get("canonical_key", "")),
        canonical_name=canonical,
        term_type=term_type,
        score=1.0,
        match_kind="confirmed",
        matched_alias=str(confirmed_term.get("matched_alias", canonical)),
        canonical_keys=tuple(
            str(key)
            for key in confirmed_term.get("canonical_keys", ())
            if str(key).strip()
        ),
    )
    return QueryResolution(
        original_query=original,
        resolved_query=resolved,
        terms=(term,),
        domain_hint="MEDICATION" if term_type.strip().upper() == "MEDICATION" else "",
        resolution_status="RESOLVED",
    )


@dataclass(frozen=True)
class _QuerySpan:
    start: int
    end: int
    text: str


class MedicalQueryResolver:
    """질문을 RDB 표준용어 중심의 검색 질의로 변환한다."""

    def __init__(
        self,
        repository: MedicalTermRepository | None = None,
        *,
        min_score: float = 0.66,
        fuzzy_min_score: float = 0.70,
        ambiguity_margin: float = 0.05,
        max_terms: int = 3,
    ) -> None:
        if not 0.0 <= min_score <= 1.0:
            raise ValueError("min_score는 0 이상 1 이하이어야 합니다.")
        if ambiguity_margin < 0.0:
            raise ValueError("ambiguity_margin은 0 이상이어야 합니다.")
        if fuzzy_min_score < min_score or fuzzy_min_score > 1.0:
            raise ValueError("fuzzy_min_score는 min_score 이상 1 이하이어야 합니다.")
        if max_terms <= 0:
            raise ValueError("max_terms는 1 이상이어야 합니다.")
        self.repository = repository or NullMedicalTermRepository()
        self.min_score = min_score
        self.fuzzy_min_score = fuzzy_min_score
        self.ambiguity_margin = ambiguity_margin
        self.max_terms = max_terms

    def resolve(self, question: str) -> QueryResolution:
        """질의를 캐시된 표준화 결과로 변환한다."""
        return self._resolve_uncached(str(question or "").strip())

    def _resolve_uncached(self, original: str) -> QueryResolution:
        """최신 RDB 용어 사전을 사용해 질문을 정규화한다.

        외부 의료용어 DB 결과는 프로세스 수명 동안 캐시하지 않는다. 운영 중 별칭이
        보완된 뒤에도 과거의 잘못된 확인 후보가 남는 것을 방지하기 위함이다.

        작성자: 김진우
        """
        domain_hint = self._infer_domain_hint(original)
        if not original:
            return QueryResolution(original, original, domain_hint=domain_hint)

        spans = self._candidate_spans(original)
        # 짧은 별칭(예: '당뇨')이 전체 질문의 부분 문자열이라는 이유로
        # 오타가 섞인 더 긴 용어를 가로채지 않도록, 우선 단어/구문 후보를
        # 조회한다. 전체 문장은 단어 경계로 잡히지 않을 때만 fallback으로 쓴다.
        candidates: list[tuple[_QuerySpan, MedicalTermMatch]] = []
        has_ambiguity = False
        lookup_spans = [*spans, _QuerySpan(0, len(original), original)]
        try:
            matches_by_query = self._search_many(
                [span.text for span in lookup_spans],
                limit=5,
            )
        except Exception:  # RDB 장애 시 기존 원문 벡터 검색으로 안전하게 fallback
            LOGGER.warning("의료용어 RDB 조회를 건너뛰고 원문 검색을 사용합니다.", exc_info=True)
            return QueryResolution(original, original, domain_hint=domain_hint)
        for span in spans:
            if len(normalize_search_text(span.text)) < 2:
                continue
            matches = [
                match
                for match in matches_by_query.get(span.text, ())
                if self._is_candidate_match(span, match)
            ]
            best = self._select_best(matches, query=span.text)
            has_ambiguity = has_ambiguity or self._is_ambiguous(
                matches,
                query=span.text,
            )
            if best is not None:
                candidates.append((span, best))
        full_span = _QuerySpan(0, len(original), original)
        full_matches = [
            match
            for match in matches_by_query.get(original, ())
            if self._is_candidate_match(full_span, match)
        ]
        full_best = self._select_best(full_matches, query=original)
        has_ambiguity = has_ambiguity or self._is_ambiguous(
            full_matches,
            query=original,
        )
        if full_best is not None:
            is_exact_full = (
                full_best.match_kind == "exact"
                and normalize_search_text(full_best.matched_alias)
                == normalize_search_text(original)
            )
            if is_exact_full or not candidates:
                candidates.insert(0, (full_span, full_best))

        selected: list[tuple[_QuerySpan, MedicalTermMatch]] = []
        for span, match in sorted(
            candidates,
            key=lambda item: (
                -item[1].score,
                item[0].end - item[0].start,
                item[1].canonical_key,
            ),
        ):
            if any(self._overlaps(span, previous) for previous, _ in selected):
                continue
            selected.append((span, match))
            if len(selected) >= self.max_terms:
                break

        selected.sort(key=lambda item: (item[0].start, item[0].end))
        selected_valid = [
            (span, match)
            for span, match in selected
            if match.score >= self.min_score
        ]
        strong_match_kinds = {
            "exact",
            "substring",
            "alias_group_exact",
            "alias_group_substring",
        }
        strong_selected = [
            (span, match)
            for span, match in selected_valid
            if match.match_kind in strong_match_kinds
        ]
        if strong_selected:
            # HDL·AST처럼 명시적으로 일치한 검사항목이 있는데 문장 속 일반어인
            # ``수치``가 ``간수치``의 약한 초성·오타 후보로 다시 잡히면 잘못된
            # 확인 질문이 생긴다. 정확한 DB 근거가 있으면 약한 후보는 폐기한다.
            selected_valid = strong_selected
        if any(
            match.term_type.strip().upper() == "MEDICATION"
            for _, match in selected_valid
        ):
            domain_hint = "MEDICATION"
        terms = tuple(
            ResolvedQueryTerm(
                source_text=span.text,
                canonical_key=match.canonical_key,
                canonical_name=match.canonical_name,
                term_type=match.term_type,
                score=match.score,
                match_kind=match.match_kind,
                matched_alias=match.matched_alias,
                canonical_keys=match.canonical_keys,
            )
            for span, match in selected_valid
        )
        if not terms:
            return QueryResolution(
                original,
                original,
                domain_hint=domain_hint,
                resolution_status="AMBIGUOUS" if has_ambiguity else "NO_MATCH",
            )

        confirmation_match = next(
            (
                (span, match)
                for span, match in selected_valid
                if match.match_kind in {
                    "initials",
                    "initials_substring",
                    "fuzzy",
                    "alias_group_initials",
                    "alias_group_fuzzy",
                }
            ),
            None,
        )
        if confirmation_match is not None:
            span, match = confirmation_match
            alias = match.matched_alias.strip()
            canonical = match.canonical_name.strip()
            label = alias or canonical
            if alias and normalize_search_text(alias) != normalize_search_text(canonical):
                label = f"{alias}({canonical})"
            # 확인 한 번에 가장 신뢰도 높은 후보 하나만 보낸다. 같은 문장의
            # 일반 동사·형용사에서 나온 약한 후보가 다음 확인 질문으로
            # 이어지는 것을 막는다.
            confirmation_term = ResolvedQueryTerm(
                source_text=span.text,
                canonical_key=match.canonical_key,
                canonical_name=match.canonical_name,
                term_type=match.term_type,
                score=match.score,
                match_kind=match.match_kind,
                matched_alias=match.matched_alias,
                canonical_keys=match.canonical_keys,
            )
            return QueryResolution(
                original_query=original,
                resolved_query=original,
                terms=(confirmation_term,),
                needs_confirmation=True,
                confirmation_question=f"혹시 '{label}'를 물어보신 걸까요?",
                domain_hint=domain_hint,
                resolution_status="CONFIRM",
            )

        resolved = original
        replacements: list[tuple[int, int, str]] = []
        for (span, match), term in zip(selected_valid, terms):
            if self._preserve_medication_compound(span, match, domain_hint):
                continue
            if not (span.start == 0 and span.end == len(original)):
                replacements.append((span.start, span.end, term.canonical_name))
        for start, end, replacement in sorted(replacements, reverse=True):
            resolved = resolved[:start] + replacement + resolved[end:]

        # word_similarity가 문장 내부 위치를 반환하지 않는 경우에도 표준명은
        # 임베딩 입력에 포함시켜 오타 질문이 정확명 검색으로 연결되게 한다.
        if not replacements:
            hints = " ".join(term.canonical_name for term in terms)
            if (
                hints
                and domain_hint != "MEDICATION"
                and normalize_search_text(hints) != normalize_search_text(resolved)
            ):
                resolved = f"{resolved} {hints}".strip()

        return QueryResolution(
            original_query=original,
            resolved_query=resolved,
            terms=terms,
            domain_hint=domain_hint,
            resolution_status="RESOLVED",
        )

    @staticmethod
    def _infer_domain_hint(question: str) -> str:
        """질문의 일반적인 약물 어휘와 RDB 용어 타입으로 검색 영역을 힌트한다."""
        for token in TOKEN_RE.findall(question):
            normalized = normalize_search_text(token)
            normalized = MedicalQueryResolver._strip_query_particle(normalized)
            if normalized in MEDICATION_QUERY_LEXEMES:
                return "MEDICATION"
            # ``감기약``·``혈압약``처럼 질환명에 약물 범주가 붙은 복합어도
            # 질환명 하나로 축약하지 않고 의약품 검색 영역을 유지한다.
            if len(normalized) > 1 and normalized.endswith("약"):
                return "MEDICATION"
        return ""

    @staticmethod
    def _strip_query_particle(value: str) -> str:
        for particle in sorted(KOREAN_PARTICLES, key=len, reverse=True):
            if value.endswith(particle) and len(value) > len(particle) + 1:
                return value[: -len(particle)]
        return value

    @staticmethod
    def _preserve_medication_compound(
        span: _QuerySpan,
        match: MedicalTermMatch,
        domain_hint: str,
    ) -> bool:
        """복합어의 약물 범주가 질환 alias로 덮어써지지 않게 한다."""
        if domain_hint != "MEDICATION":
            return False
        if match.term_type.strip().upper() == "MEDICATION":
            return False
        span_key = normalize_search_text(span.text)
        alias_key = normalize_search_text(match.matched_alias)
        return bool(alias_key and alias_key != span_key and alias_key in span_key)

    @staticmethod
    def _is_candidate_match(span: _QuerySpan, match: MedicalTermMatch) -> bool:
        """검색 후보가 의료용어로 볼 만한 독립 근거를 갖췄는지 판정한다.

        정확·부분 일치는 DB가 직접 제공한 강한 근거이므로 허용한다. 반면
        완성형 일반 어절은 초성 부분열이나 낮은 fuzzy 점수 하나만으로
        의료용어가 되지 않는다. 초성 자모 입력 또는 음절 구성 오타처럼
        독립적인 증거가 있을 때만 약한 후보를 통과시킨다.
        """
        kind = match.match_kind.strip().lower()
        if (
            is_medical_query_context(span.text)
            and kind not in {"exact", "alias_group_exact"}
        ):
            return False
        strong_kinds = {
            "exact",
            "substring",
            "alias_group_exact",
            "alias_group_substring",
        }
        if kind in strong_kinds:
            return True

        query = span.text
        if is_korean_initial_input(query):
            return kind in {
                "initials",
                "initials_substring",
                "alias_group_initials",
            }
        if is_likely_predicate(query):
            return False
        if kind in {
            "initials",
            "initials_substring",
            "alias_group_initials",
            "fuzzy",
            "alias_group_fuzzy",
        }:
            return is_syllable_initial_typo(query, match.matched_alias)
        return True

    def _search_many(
        self,
        queries: Sequence[str],
        *,
        limit: int,
    ) -> dict[str, Sequence[MedicalTermMatch]]:
        search_many = getattr(self.repository, "search_many", None)
        if callable(search_many):
            return dict(search_many(queries, limit=limit))
        return {
            query: self.repository.search(query, limit=limit)
            for query in dict.fromkeys(queries)
        }

    def _candidate_spans(self, question: str) -> list[_QuerySpan]:
        token_spans = [
            _QuerySpan(match.start(), match.end(), match.group(0))
            for match in TOKEN_RE.finditer(question)
        ]
        candidates: list[_QuerySpan] = []
        for index, token in enumerate(token_spans):
            candidates.append(token)
            stripped = self._strip_particle(token)
            if stripped.end < token.end and len(normalize_search_text(stripped.text)) >= 2:
                candidates.append(stripped)
            for width in (2, 3):
                end_index = index + width - 1
                if end_index >= len(token_spans):
                    break
                candidates.append(
                    _QuerySpan(
                        token.start,
                        token_spans[end_index].end,
                        question[token.start : token_spans[end_index].end],
                    )
                )
        # 같은 후보의 반복 조회를 없애고 짧은 후보를 먼저 둔다.
        unique: dict[tuple[int, int], _QuerySpan] = {}
        for candidate in candidates:
            unique[(candidate.start, candidate.end)] = candidate
        return sorted(unique.values(), key=lambda item: (item.start, item.end - item.start))

    @staticmethod
    def _strip_particle(span: _QuerySpan) -> _QuerySpan:
        for particle in sorted(KOREAN_PARTICLES, key=len, reverse=True):
            if span.text.endswith(particle) and len(span.text) > len(particle) + 1:
                return _QuerySpan(span.start, span.end - len(particle), span.text[: -len(particle)])
        return span

    def _select_best(
        self,
        matches: Sequence[MedicalTermMatch],
        *,
        query: str = "",
    ) -> MedicalTermMatch | None:
        ranked = sorted(
            matches,
            key=lambda item: (-item.score, -item.priority, item.canonical_key),
        )
        if not ranked or ranked[0].score < self.min_score:
            return None
        if (
            ranked[0].match_kind == "fuzzy"
            and ranked[0].score < self.fuzzy_min_score
        ):
            return None
        shared_alias = self._shared_alias_group(ranked, query=query)
        if shared_alias is not None:
            return self._build_alias_group_match(shared_alias, query=query)
        if len(ranked) > 1 and ranked[0].canonical_key != ranked[1].canonical_key:
            if (
                ranked[0].match_kind == "exact"
                and ranked[0].score >= 1.0
                and ranked[1].match_kind != "exact"
            ):
                return ranked[0]
            if ranked[0].score - ranked[1].score < self.ambiguity_margin:
                return None
        return ranked[0]

    def _is_ambiguous(
        self,
        matches: Sequence[MedicalTermMatch],
        *,
        query: str = "",
    ) -> bool:
        ranked = sorted(
            (
                match
                for match in matches
                if match.score >= self.min_score
                and not (
                    match.match_kind == "fuzzy"
                    and match.score < self.fuzzy_min_score
                )
            ),
            key=lambda item: (-item.score, -item.priority, item.canonical_key),
        )
        if len(ranked) < 2 or ranked[0].canonical_key == ranked[1].canonical_key:
            return False
        if self._shared_alias_group(ranked, query=query) is not None:
            return False
        if (
            ranked[0].match_kind == "exact"
            and ranked[0].score >= 1.0
            and ranked[1].match_kind != "exact"
        ):
            return False
        return ranked[0].score - ranked[1].score < self.ambiguity_margin

    def _shared_alias_group(
        self,
        ranked: Sequence[MedicalTermMatch],
        *,
        query: str = "",
    ) -> tuple[MedicalTermMatch, ...] | None:
        """같은 사용자 표현이 여러 표준항목의 alias인 경우를 묶는다.

        예를 들어 여러 검사항목이 모두 ``간수치``를 관련어로 사용할 수
        있다. 이때 특정 항목 하나를 선택하면 잘못된 표준화가 되지만,
        공통 alias를 검색 그룹으로 사용하면 관련 근거를 함께 검색할 수
        있다. 서로 다른 alias가 경쟁하는 경우에는 기존 모호성 차단을
        유지한다.
        """
        if len(ranked) < 2:
            return None
        top = ranked[0]
        alias_key = normalize_search_text(top.matched_alias)
        if not alias_key:
            return None
        group = tuple(
            match
            for match in ranked
            if normalize_search_text(match.matched_alias) == alias_key
            and top.score - match.score < self.ambiguity_margin
        )
        query_key = normalize_search_text(query)
        if len({match.canonical_key for match in group}) < 2 and query_key:
            group = tuple(
                match
                for match in ranked
                if match.term_type.strip().upper() == "SCREENING"
                and query_key in normalize_search_text(match.matched_alias)
                and top.score - match.score < self.ambiguity_margin
            )
        canonical_keys = {match.canonical_key for match in group}
        term_types = {match.term_type.strip().upper() for match in group}
        if len(canonical_keys) < 2 or len(term_types) != 1:
            return None
        return group

    @staticmethod
    def _build_alias_group_match(
        group: Sequence[MedicalTermMatch],
        *,
        query: str = "",
    ) -> MedicalTermMatch:
        top = group[0]
        if all(match.match_kind == "exact" for match in group):
            match_kind = "alias_group_exact"
        elif all(
            match.match_kind in {"exact", "substring"}
            for match in group
        ):
            match_kind = "alias_group_substring"
        elif any(match.match_kind in {"initials", "initials_substring"} for match in group):
            match_kind = "alias_group_initials"
        else:
            match_kind = "alias_group_fuzzy"
        alias = query.strip() or top.matched_alias
        alias_key = normalize_search_text(alias)
        return MedicalTermMatch(
            canonical_key=f"ALIAS_GROUP:{alias_key}",
            canonical_name=alias,
            term_type="ALIAS_GROUP",
            matched_alias=alias,
            score=top.score,
            match_kind=match_kind,
            priority=max(match.priority for match in group),
            canonical_keys=tuple(
                sorted({match.canonical_key for match in group})
            ),
        )

    @staticmethod
    def _overlaps(left: _QuerySpan, right: _QuerySpan) -> bool:
        return left.start < right.end and right.start < left.end


def build_query_resolver(
    dsn: str = "",
    *,
    supabase_url: str = "",
    supabase_publishable_key: str = "",
    min_score: float = 0.66,
    ambiguity_margin: float = 0.05,
) -> MedicalQueryResolver:
    """환경설정에 맞는 질의 정규화기를 생성한다."""
    repository: MedicalTermRepository
    if dsn.strip():
        repository = RdbMedicalTermRepository(dsn)
    elif supabase_url.strip() and supabase_publishable_key.strip():
        repository = SupabaseMedicalTermRepository(
            supabase_url,
            supabase_publishable_key,
        )
    else:
        repository = NullMedicalTermRepository()
    return MedicalQueryResolver(
        repository,
        min_score=min_score,
        ambiguity_margin=ambiguity_margin,
    )
