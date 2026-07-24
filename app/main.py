from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.core.state import state
from app.services.rag import build_answer_chain
from app.services.vector_search import build_pinecone_search_service
from app.routers import ask


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 로컬 임베딩 모델과 Pinecone 검색을 준비한다."""
    vector_search = build_pinecone_search_service()
    counts = vector_search.counts()

    state["vector_search"] = vector_search
    state["answer_chain"] = build_answer_chain()
    state["backend"] = vector_search.backend_name
    state["embed_model"] = vector_search.embed_model
    state["indexed_chunks"] = counts
    state["ready"] = True

    print(
        f"[lifespan] 벡터 백엔드 준비 완료 - "
        f"backend={vector_search.backend_name}, model={vector_search.embed_model}"
    )
    for name, count in counts.items():
        print(f"[lifespan] '{name}' 청크 {count}개")

    yield                                    # 여기서부터 요청을 받습니다
    state.clear()                            # 종료 시 정리

app = FastAPI(title="HEAPY RAG 서빙", version="1.0", lifespan=lifespan)
app.include_router(ask.router)

# 실행 명령어: uvicorn app.main:app --reload
# Gradio UI 실행: python run_ui.py
