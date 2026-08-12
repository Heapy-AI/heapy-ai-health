"""검색·생성 품질 지표 계산 (LLM 호출 없는 결정적 지표)."""
from __future__ import annotations

import math
import re
from collections import Counter

_WHITESPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^0-9A-Za-z가-힣]+")

# 골든셋의 건강검진 문서 ID(screening:chest_xray:001)와 인덱스 벡터 ID(CHEST_XRAY)는
# 표기만 다른 동일 청크다. vdb/chunk/health_checkup_info/screening_core_v1.jsonl의
# canonical_key 30개와 골든셋 screening ID 30개가 1:1로 대응함을 확인했다.
_SCREENING_ID = re.compile(r"^screening:([a-z0-9_]+):\d+$")


def normalize_document_id(document_id: str) -> str:
    """서로 다른 표기의 동일 문서 ID를 하나의 정규형으로 맞춘다."""
    match = _SCREENING_ID.fullmatch(document_id.strip())
    if match:
        return match.group(1).upper()
    return document_id.strip()


def normalize_ids(document_ids) -> list[str]:
    """문서 ID 목록을 정규화한다(순서 유지)."""
    return [normalize_document_id(str(document_id)) for document_id in document_ids]


# 같은 질병(kdca-6582-*)·같은 의약품(eyak:200901703:*)의 다른 섹션 청크를 하나로 묶는다.
_KDCA_GROUP = re.compile(r"^(kdca-\d+)-\d+$")
_EYAK_GROUP = re.compile(r"^(eyak:[^:]+):")


def document_group(document_id: str) -> str:
    """문서 ID가 속한 원천 문서(질병·의약품·검진항목) 식별자를 반환한다."""
    normalized = normalize_document_id(document_id)
    match = _KDCA_GROUP.fullmatch(normalized)
    if match:
        return match.group(1)
    match = _EYAK_GROUP.match(normalized)
    if match:
        return match.group(1)
    return normalized


def document_groups(document_ids) -> list[str]:
    """문서 ID 목록을 원천 문서 단위로 변환한다(순서 유지)."""
    return [document_group(str(document_id)) for document_id in document_ids]


# --------------------------------------------------------------------------
# 검색 지표
# --------------------------------------------------------------------------
def hit_at_k(retrieved_ids: list[str], relevant: set[str], k: int) -> float:
    """상위 k개 안에 정답 문서가 하나라도 있으면 1."""
    if not relevant:
        return float("nan")
    return 1.0 if any(doc_id in relevant for doc_id in retrieved_ids[:k]) else 0.0


def reciprocal_rank(retrieved_ids: list[str], relevant: set[str], k: int = 10) -> float:
    """첫 정답 문서 순위의 역수(MRR@k)."""
    if not relevant:
        return float("nan")
    for rank, doc_id in enumerate(retrieved_ids[:k], start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def context_recall_ids(retrieved_ids: list[str], gold: set[str]) -> float:
    """근거재현율: 정답 문서 중 실제로 회수된 비율."""
    if not gold:
        return float("nan")
    return len(set(retrieved_ids) & gold) / len(gold)


def context_precision_ids(retrieved_ids: list[str], relevant: set[str]) -> float:
    """근거정밀도: 회수 문서 중 정답으로 인정되는 비율."""
    if not retrieved_ids:
        return float("nan")
    if not relevant:
        return float("nan")
    return len([d for d in retrieved_ids if d in relevant]) / len(retrieved_ids)


def average_precision(retrieved_ids: list[str], relevant: set[str]) -> float:
    """순위를 반영한 평균 정밀도(MAP 구성요소)."""
    if not relevant or not retrieved_ids:
        return float("nan")
    hits = 0
    total = 0.0
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant:
            hits += 1
            total += hits / rank
    if hits == 0:
        return 0.0
    return total / min(len(relevant), len(retrieved_ids))


def ndcg_at_k(retrieved_ids: list[str], relevant: set[str], k: int = 10) -> float:
    """이진 관련도 기준 nDCG@k."""
    if not relevant:
        return float("nan")
    gain = sum(
        1.0 / math.log2(rank + 1)
        for rank, doc_id in enumerate(retrieved_ids[:k], start=1)
        if doc_id in relevant
    )
    ideal = sum(
        1.0 / math.log2(rank + 1)
        for rank in range(1, min(len(relevant), k) + 1)
    )
    return gain / ideal if ideal else float("nan")


# --------------------------------------------------------------------------
# 인용(출처) 지표
# --------------------------------------------------------------------------
def citation_ids_to_record_ids(
    cited_chunk_ids: list[str],
    retrieved_ids: list[str],
) -> list[str]:
    """C1/C2 형식 인용 라벨을 실제 문서 record_id로 되돌린다."""
    resolved: list[str] = []
    for label in cited_chunk_ids:
        match = re.fullmatch(r"C(\d+)", label.strip())
        if not match:
            continue
        index = int(match.group(1)) - 1
        if 0 <= index < len(retrieved_ids):
            resolved.append(retrieved_ids[index])
    return resolved


def citation_accuracy(cited_record_ids: list[str], relevant: set[str]) -> float:
    """출처ID일치율: 인용한 문서 중 정답 문서 비율."""
    if not cited_record_ids or not relevant:
        return float("nan")
    return len([d for d in cited_record_ids if d in relevant]) / len(cited_record_ids)


# --------------------------------------------------------------------------
# 생성 지표 (어휘 기반)
# --------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    """비교용으로 공백·기호를 정리한다."""
    return _WHITESPACE.sub(" ", _NON_WORD.sub(" ", text)).strip().lower()


def _char_ngrams(text: str, n: int = 2) -> Counter:
    compact = normalize_text(text).replace(" ", "")
    if len(compact) < n:
        return Counter([compact] if compact else [])
    return Counter(compact[i : i + n] for i in range(len(compact) - n + 1))


def char_ngram_f1(prediction: str, reference: str, n: int = 2) -> float:
    """한국어에 견고한 문자 n-gram F1."""
    if not prediction.strip() or not reference.strip():
        return 0.0
    pred = _char_ngrams(prediction, n)
    ref = _char_ngrams(reference, n)
    overlap = sum((pred & ref).values())
    if overlap == 0:
        return 0.0
    precision = overlap / max(sum(pred.values()), 1)
    recall = overlap / max(sum(ref.values()), 1)
    return 2 * precision * recall / (precision + recall)


def token_f1(prediction: str, reference: str) -> float:
    """어절 단위 F1."""
    pred = Counter(normalize_text(prediction).split())
    ref = Counter(normalize_text(reference).split())
    if not pred or not ref:
        return 0.0
    overlap = sum((pred & ref).values())
    if overlap == 0:
        return 0.0
    precision = overlap / sum(pred.values())
    recall = overlap / sum(ref.values())
    return 2 * precision * recall / (precision + recall)


def reference_coverage(prediction: str, reference: str) -> float:
    """짧은 정답(질환명 등)이 답변에 그대로 포함되었는지."""
    normalized_reference = normalize_text(reference).replace(" ", "")
    normalized_prediction = normalize_text(prediction).replace(" ", "")
    if not normalized_reference:
        return float("nan")
    return 1.0 if normalized_reference in normalized_prediction else 0.0


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """두 임베딩의 코사인 유사도."""
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


# --------------------------------------------------------------------------
# 집계 유틸
# --------------------------------------------------------------------------
def mean(values) -> float:
    """NaN을 제외한 평균."""
    clean = [v for v in values if v is not None and not _is_nan(v)]
    if not clean:
        return float("nan")
    return sum(clean) / len(clean)


def percentile(values, q: float) -> float:
    """선형 보간 백분위수."""
    clean = sorted(v for v in values if v is not None and not _is_nan(v))
    if not clean:
        return float("nan")
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[int(position)]
    return clean[lower] + (clean[upper] - clean[lower]) * (position - lower)


def _is_nan(value) -> bool:
    return isinstance(value, float) and math.isnan(value)


# --------------------------------------------------------------------------
# 레코드 단위 결정적 지표
# --------------------------------------------------------------------------
ABSTENTION_ANSWERS = {
    (
        "질문과 정확히 일치하는 정보를 찾지 못했습니다. 이름이나 수치를 다시 확인해 "
        "알려주시면 확인 가능한 정보부터 이어서 설명드릴게요."
    ),
    "죄송합니다. 건강 관련 문의만 도와드릴 수 있어요.",
}


def is_abstention(answer: str, grounded) -> bool:
    """시스템이 답변을 회피(근거 없음/거절)했는지 판정한다."""
    if (answer or "").strip() in ABSTENTION_ANSWERS:
        return True
    return grounded is False


def deterministic_metrics(record: dict) -> dict:
    """LLM 호출 없이 계산 가능한 검색·인용·어휘 지표를 한 레코드에서 계산한다."""
    gold_meta = record["gold"]
    relevant = set(
        normalize_ids(
            gold_meta.get("acceptable_document_ids") or gold_meta.get("gold_document_ids") or []
        )
    )
    gold = set(normalize_ids(gold_meta.get("gold_document_ids") or []))

    final_ids = normalize_ids(
        doc["record_id"] for doc in record.get("retrieved_documents", [])
    )
    candidate_ids = normalize_ids(
        doc["record_id"] for doc in record.get("candidate_documents", [])
    )
    cited_ids = citation_ids_to_record_ids(record.get("cited_chunk_ids", []), final_ids)

    answer = record.get("answer") or ""
    reference = gold_meta.get("reference_answer") or ""
    source_uri = gold_meta.get("source_uri") or ""

    cited_set = set(cited_ids)
    cited_sources = {
        doc["source"]
        for doc, doc_id in zip(record.get("retrieved_documents", []), final_ids)
        if doc_id in cited_set
    }

    abstained = is_abstention(answer, record.get("grounded"))
    answerable = bool(gold_meta.get("answerable", True))

    return {
        # 검색 — LLM에 실제 전달된 최종 문맥 기준
        "hit@1": hit_at_k(final_ids, relevant, 1),
        "hit@3": hit_at_k(final_ids, relevant, 3),
        "hit@5": hit_at_k(final_ids, relevant, 5),
        "mrr@10": reciprocal_rank(final_ids, relevant, 10),
        "ndcg@10": ndcg_at_k(final_ids, relevant, 10),
        "map": average_precision(final_ids, relevant),
        "context_recall_id": context_recall_ids(final_ids, gold),
        "context_precision_id": context_precision_ids(final_ids, relevant),
        # 검색 — 병합·컬렉션 상한 적용 전 후보 기준
        "candidate_hit@1": hit_at_k(candidate_ids, relevant, 1),
        "candidate_hit@3": hit_at_k(candidate_ids, relevant, 3),
        "candidate_hit@5": hit_at_k(candidate_ids, relevant, 5),
        "candidate_mrr@10": reciprocal_rank(candidate_ids, relevant, 10),
        "candidate_context_recall_id": context_recall_ids(candidate_ids, gold),
        # 검색 — 원천 문서(같은 질병·의약품의 다른 섹션) 단위 완화 기준
        "group_hit@1": hit_at_k(
            document_groups(final_ids), set(document_groups(relevant)), 1
        ),
        "group_hit@3": hit_at_k(
            document_groups(final_ids), set(document_groups(relevant)), 3
        ),
        "group_hit@5": hit_at_k(
            document_groups(final_ids), set(document_groups(relevant)), 5
        ),
        "candidate_group_hit@3": hit_at_k(
            document_groups(candidate_ids), set(document_groups(relevant)), 3
        ),
        # 인용
        "citation_accuracy": citation_accuracy(cited_ids, relevant),
        "citation_hit": (
            float(any(d in relevant for d in cited_ids)) if cited_ids else float("nan")
        ),
        "citation_count": len(cited_ids),
        "source_uri_match": (
            float(source_uri in cited_sources)
            if cited_sources and source_uri
            else float("nan")
        ),
        # 생성 — 어휘 기반
        "answer_char_f1": char_ngram_f1(answer, reference) if reference else float("nan"),
        "answer_token_f1": token_f1(answer, reference) if reference else float("nan"),
        "reference_coverage": (
            reference_coverage(answer, reference)
            if reference and len(reference) <= 40
            else float("nan")
        ),
        # 거절 처리
        "is_abstention": float(abstained),
        "abstention_correct": float(abstained == (not answerable)),
        "resolved_cited_record_ids": cited_ids,
    }
