from contextlib import asynccontextmanager
from fastapi import FastAPI
from langchain_huggingface import HuggingFaceEmbeddings

from app.core.config import EMBED_MODEL, COLLECTIONS
from app.core.state import state
from app.services.rag import build_all_vectorstores, build_chain
from app.routers import ask


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 1회: 임베딩 로드 → 컬렉션별 Chroma 열기/구축 → RAG 체인 구성.

    무거운 준비는 여기서 끝내고, 요청은 가볍게 invoke 만 하도록 만듭니다.
    """
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectorstores = build_all_vectorstores(embeddings)   # {"disease_info": Chroma, "health_checkup_info": Chroma, ...}

    retrievers = {
        name: vs.as_retriever(search_kwargs={"k": 3})   # 검색기: 관련 청크 상위 3개
        for name, vs in vectorstores.items()
    }
    chains = {
        name: build_chain(retriever)
        for name, retriever in retrievers.items()
    }

    state["vectorstores"] = vectorstores
    state["retrievers"] = retrievers
    state["chains"] = chains
    state["ready"] = True

    for name, vs in vectorstores.items():
        print(f"[lifespan] '{name}' 인덱스 준비 완료 — 청크 {vs._collection.count()}개")

    yield                                    # 여기서부터 요청을 받습니다
    state.clear()                            # 종료 시 정리

app = FastAPI(title="HEAPY RAG 서빙", version="1.0", lifespan=lifespan)
app.include_router(ask.router)

# 실행 명령어: uvicorn app.main:app --reload
# Gradio UI 실행: python run_ui.py