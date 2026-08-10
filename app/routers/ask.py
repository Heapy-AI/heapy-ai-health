from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.core.config import (
    COLLECTIONS,
    SEARCH_COLLECTIONS,
    SEARCH_FINAL_TOP_K,
    SEARCH_MAX_PER_COLLECTION,
    SEARCH_MIN_SCORE,
    SEARCH_TOP_K,
    SEARCH_TOP_K_PER_COLLECTION,
)
from app.core.state import state
from app.services.rag import cite, format_docs
from app.services.search_result_merger import merge_search_results
from app.services.intent_classifier import Intent
from app.services.query_resolver import QueryResolution
from app.services.safety_guard import check_safety_guard
from app.schemas.health_chatbot import (
    AskRequest,
    AskResponse,
    CombinedAnswerChunk,
    CombinedAskRequest,
    CombinedAskResponse,
    CombinedCitation,
    CombinedSearchHit,
    CombinedSearchResponse,
    SearchHit,
    SearchResponse,
)


router = APIRouter()

NOT_GROUNDED_MARK = "지식베이스에 근거 없음"


def _get_collection_or_404(collection: str):
    """요청받은 컬렉션이 등록돼 있는지 확인하고, 없으면 명확한 400 에러를 낸다."""
    if collection not in COLLECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"알 수 없는 컬렉션입니다: '{collection}' (사용 가능: {list(COLLECTIONS)})",
        )


def _retrieve(collection: str, question: str):
    """질문으로 관련 청크를 검색해 Document 리스트를 돌려준다(검색만, LLM 호출 없음)."""
    return state["vector_search"].search(collection, question, SEARCH_TOP_K)


def _retrieve_combined(question: str):
    """설정된 namespace를 병렬 검색하고 하나의 근거 목록으로 병합한다."""
    vector_search = state["vector_search"]
    resolver = getattr(vector_search, "resolve_query", None)
    resolution = (
        resolver(question)
        if callable(resolver)
        else QueryResolution(question, question)
    )
    embed_resolved = getattr(vector_search, "embed_resolved_query", None)
    query_vector = (
        embed_resolved(resolution.resolved_query)
        if callable(embed_resolved)
        else vector_search.embed_query(resolution.resolved_query)
    )
    search_result = vector_search.search_many_by_vector(
        SEARCH_COLLECTIONS,
        query_vector,
        SEARCH_TOP_K_PER_COLLECTION,
    )
    if (
        search_result.errors
        and len(search_result.errors) == len(search_result.searched_collections)
    ):
        raise HTTPException(
            status_code=503,
            detail="모든 Pinecone namespace 검색에 실패했습니다.",
        )

    documents = merge_search_results(
        search_result.documents,
        final_top_k=SEARCH_FINAL_TOP_K,
        max_per_collection=SEARCH_MAX_PER_COLLECTION,
        min_score=SEARCH_MIN_SCORE,
    )
    return documents, search_result, query_vector, resolution


def _resolution_from_documents(documents, question: str) -> QueryResolution:
    """단일 namespace 검색 결과에 보존된 정규화 메타데이터를 읽는다."""
    if documents:
        metadata = documents[0].metadata
        resolved_query = str(metadata.get("resolved_query", question))
        raw_terms = metadata.get("resolved_terms", [])
        if isinstance(raw_terms, list):
            return QueryResolution(question, resolved_query, tuple())
    return QueryResolution(question, question)


def _select_grounding_verification(
    question: str,
    query_vector: list[float],
    resolution: QueryResolution | None = None,
) -> tuple[bool, str]:
    """질문 위험도와 Intent에 따라 2차 LLM 검증 여부를 결정한다."""
    guard_result = check_safety_guard(question, resolution=resolution)
    if guard_result.triggered:
        return True, f"safety_guard:{guard_result.reason}"

    classifier = state.get("intent_classifier")
    if classifier is None:
        return True, "intent_classifier_unavailable"

    prediction = classifier.predict(query_vector)
    if prediction.uncertain:
        return True, "intent_uncertain"
    if prediction.intent in {Intent.COMPREHENSIVE, Intent.IGNORE}:
        return True, f"intent:{prediction.intent.value}"
    return False, f"intent:{prediction.intent.value}"


def _to_sources(docs) -> list[str]:
    """검색 청크 메타에서 '라벨 · URL' 출처를 만들고 중복 제거·정렬한다."""
    return sorted({cite(d) for d in docs})


def _to_answer_chunks(docs) -> list[CombinedAnswerChunk]:
    """Gemini 문맥에 전달한 최종 Document를 원문 그대로 응답한다."""
    return [
        CombinedAnswerChunk(
            collection=str(document.metadata.get("collection", "unknown")),
            record_id=str(document.metadata.get("record_id", "")),
            score=float(document.metadata.get("score", 0.0) or 0.0),
            source=cite(document),
            text=document.page_content,
        )
        for document in docs
    ]


def _to_citations(docs, citation_ids: list[str]) -> list[CombinedCitation]:
    """검증을 통과한 인용 ID를 실제 최종 청크와 연결한다."""
    citations: list[CombinedCitation] = []
    for citation_id in citation_ids:
        index = int(citation_id[1:]) - 1
        if index < 0 or index >= len(docs):
            continue
        document = docs[index]
        citations.append(
            CombinedCitation(
                citation_id=citation_id,
                collection=str(document.metadata.get("collection", "unknown")),
                record_id=str(document.metadata.get("record_id", "")),
                score=float(document.metadata.get("score", 0.0) or 0.0),
                source=cite(document),
                text=document.page_content,
            )
        )
    return citations


# ── health check — 컬렉션별 인덱스 적재 여부 확인 ──
@router.get("/health")
def health():
    """서버·인덱스 상태 점검. 컬렉션별 청크 수를 모두 보여준다.

    하나라도 비어 있으면 전체 ready=False — 배포 직후 '준비 안 됨'을 빨리 알 수 있습니다.
    """
    counts = state.get("indexed_chunks", {})
    ready = bool(state.get("ready")) and all(c > 0 for c in counts.values()) and len(counts) > 0
    classifier = state.get("intent_classifier")
    return {
        "status": "ok",
        "ready": ready,
        "vector_backend": state.get("backend", "unknown"),
        "llm_backend": state.get("llm_backend", "unknown"),
        "indexed_chunks": counts,
        "embed_model": state.get("embed_model", "unknown"),
        "intent_classifier": {
            "ready": classifier is not None,
            "model_version": (
                classifier.model_version if classifier is not None else None
            ),
        },
    }


# ── /search — LLM 없이 검색 결과만(빠르고 저렴) ──
@router.post("/search", response_model=SearchResponse)
def search(req: AskRequest):
    """질문과 가장 비슷한 청크를 지정한 컬렉션에서 그대로 반환(LLM 호출 없음).

    '어느 자료에 적혀 있나'만 빠르게 확인하거나, 검색 품질을 점검할 때 씁니다.
    """
    _get_collection_or_404(req.collection)
    docs = _retrieve(req.collection, req.question)
    hits = [SearchHit(source=cite(d), text=d.page_content[:120])
            for d in docs]
    resolution = _resolution_from_documents(docs, req.question)
    return SearchResponse(
        query=req.question,
        hits=hits,
        resolved_query=resolution.resolved_query,
        resolved_terms=(docs[0].metadata.get("resolved_terms", []) if docs else []),
    )


# ── /ask — 답 + 출처(근거 없으면 회피) ──
@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """질문 → 지정 컬렉션 기반 RAG 답변 + 출처.

    - 같은 검색 결과로 답·출처를 만들어 일관성을 지킵니다.
    - LLM 이 회피 문구로 답하면 grounded=False, sources 도 비웁니다.
    """
    _get_collection_or_404(req.collection)
    docs = _retrieve(req.collection, req.question)
    resolution = _resolution_from_documents(docs, req.question)
    answer = state["answer_chain"].invoke(
        {
            "context": format_docs(docs),
            "question": resolution.resolved_query,
        }
    )
    grounded = NOT_GROUNDED_MARK not in answer
    sources = _to_sources(docs) if grounded else []
    return AskResponse(
        answer=answer,
        sources=sources,
        grounded=grounded,
        resolved_query=resolution.resolved_query,
        resolved_terms=(docs[0].metadata.get("resolved_terms", []) if docs else []),
    )


@router.post("/search/combined", response_model=CombinedSearchResponse)
def search_combined(req: CombinedAskRequest) -> CombinedSearchResponse:
    """설정된 Pinecone namespace를 병렬 검색한 통합 결과를 반환한다."""
    docs, search_result, _, resolution = _retrieve_combined(req.question)
    hits = [
        CombinedSearchHit(
            collection=str(document.metadata.get("collection", "unknown")),
            score=float(document.metadata.get("score", 0.0) or 0.0),
            source=cite(document),
            text=document.page_content[:120],
        )
        for document in docs
    ]
    return CombinedSearchResponse(
        query=req.question,
        hits=hits,
        searched_collections=search_result.searched_collections,
        failed_collections=sorted(search_result.errors),
        resolved_query=resolution.resolved_query,
        resolved_terms=[term.as_dict() for term in resolution.terms],
    )


@router.post("/ask/combined", response_model=CombinedAskResponse)
def ask_combined(req: CombinedAskRequest) -> CombinedAskResponse:
    """다중 namespace 검색 근거를 사용해 하나의 RAG 답변을 생성한다."""
    docs, search_result, query_vector, resolution = _retrieve_combined(req.question)
    failed_collections = sorted(search_result.errors)
    if not docs:
        return CombinedAskResponse(
            answer=NOT_GROUNDED_MARK,
            sources=[],
            grounded=False,
            chunks=[],
            citations=[],
            verification_method="plan_rejected",
            verification_reason="no_search_results",
            grounding_errors=["검색된 최종 청크가 없습니다."],
            unsupported_claims=[],
            grounding_plan=None,
            audit_status="not_run",
            audit_summary="근거 계획을 생성하지 않았습니다.",
            searched_collections=search_result.searched_collections,
            failed_collections=failed_collections,
            resolved_query=resolution.resolved_query,
            resolved_terms=[term.as_dict() for term in resolution.terms],
        )

    verify_semantics, verification_reason = _select_grounding_verification(
        req.question,
        query_vector,
        resolution,
    )
    result = state["grounded_rag_service"].answer(
        resolution.resolved_query,
        docs,
        verify_semantics=verify_semantics,
    )
    citations = _to_citations(docs, result.cited_chunk_ids)
    return CombinedAskResponse(
        answer=result.answer,
        sources=(
            sorted({citation.source for citation in citations})
            if result.grounded
            else []
        ),
        grounded=result.grounded,
        chunks=_to_answer_chunks(docs),
        citations=citations,
        verification_method=result.verification_method,
        verification_reason=verification_reason,
        grounding_errors=result.grounding_errors,
        unsupported_claims=result.unsupported_claims,
        grounding_plan=(
            result.grounding_plan.model_dump(mode="json")
            if result.grounding_plan is not None
            else None
        ),
        audit_status=result.audit_status,
        audit_summary=result.audit_summary,
        searched_collections=search_result.searched_collections,
        failed_collections=failed_collections,
        resolved_query=resolution.resolved_query,
        resolved_terms=[term.as_dict() for term in resolution.terms],
    )
