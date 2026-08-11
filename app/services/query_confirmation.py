"""표준용어 확인 질문의 상태 저장소.

확인 버튼을 일반 검색어로 다시 보내지 않고, 서버가 발급한 확인 ID로
사용자가 승인한 canonical term을 확정하기 위한 짧은 수명 저장소다.
운영 환경에서는 Redis 등 공유 저장소로 교체할 수 있도록 작은 인터페이스로
분리한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from uuid import uuid4


@dataclass(frozen=True)
class QueryConfirmationRecord:
    confirmation_id: str
    original_question: str
    term: dict
    expires_at: float


class QueryConfirmationStore:
    """짧은 TTL을 가진 프로세스 내 확인 상태 저장소."""

    def __init__(self, *, ttl_seconds: int = 600) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds는 0보다 커야 합니다.")
        self._ttl_seconds = ttl_seconds
        self._records: dict[str, QueryConfirmationRecord] = {}
        self._lock = Lock()

    def create(self, original_question: str, terms: list[dict]) -> str:
        if not terms:
            raise ValueError("확인할 표준용어가 필요합니다.")
        confirmation_id = uuid4().hex
        now = monotonic()
        record = QueryConfirmationRecord(
            confirmation_id=confirmation_id,
            original_question=str(original_question).strip(),
            term=dict(terms[0]),
            expires_at=now + self._ttl_seconds,
        )
        with self._lock:
            self._purge_expired(now)
            self._records[confirmation_id] = record
        return confirmation_id

    def consume(self, confirmation_id: str) -> QueryConfirmationRecord | None:
        key = str(confirmation_id or "").strip()
        if not key:
            return None
        now = monotonic()
        with self._lock:
            self._purge_expired(now)
            record = self._records.pop(key, None)
        return record

    def discard(self, confirmation_id: str) -> None:
        with self._lock:
            self._records.pop(str(confirmation_id or "").strip(), None)

    def _purge_expired(self, now: float) -> None:
        expired = [
            key for key, record in self._records.items() if record.expires_at <= now
        ]
        for key in expired:
            self._records.pop(key, None)
