from fastapi import APIRouter, HTTPException
from app.core.config import EMBED_MODEL, COLLECTIONS
from app.core.state import state
from app.services.rag import cite
from app.schemas.health_chatbot import (AskRequest, SearchHit, SearchResponse, AskResponse)


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
    return state["retrievers"][collection].invoke(question)


def _to_sources(docs) -> list[str]:
    """검색 청크 메타에서 '라벨 · URL' 출처를 만들고 중복 제거·정렬한다."""
    return sorted({cite(d) for d in docs})


# ── health check — 컬렉션별 인덱스 적재 여부 확인 ──
@router.get("/health")
def health():
    """서버·인덱스 상태 점검. 컬렉션별 청크 수를 모두 보여준다.

    하나라도 비어 있으면 전체 ready=False — 배포 직후 '준비 안 됨'을 빨리 알 수 있습니다.
    """
    vectorstores = state.get("vectorstores", {})
    counts = {name: vs._collection.count() for name, vs in vectorstores.items()}
    ready = bool(state.get("ready")) and all(c > 0 for c in counts.values()) and len(counts) > 0
    return {"status": "ok", "ready": ready, "indexed_chunks": counts, "embed_model": EMBED_MODEL}


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
    return SearchResponse(query=req.question, hits=hits)


# ── /ask — 답 + 출처(근거 없으면 회피) ──
@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """질문 → 지정 컬렉션 기반 RAG 답변 + 출처.

    - 같은 검색 결과로 답·출처를 만들어 일관성을 지킵니다.
    - LLM 이 회피 문구로 답하면 grounded=False, sources 도 비웁니다.
    """
    _get_collection_or_404(req.collection)
    docs = _retrieve(req.collection, req.question)
    answer = state["chains"][req.collection].invoke(req.question)
    grounded = NOT_GROUNDED_MARK not in answer
    sources = _to_sources(docs) if grounded else []
    return AskResponse(answer=answer, sources=sources, grounded=grounded)