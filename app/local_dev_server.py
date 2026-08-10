"""HEAPY 로컬 검색·RAG 테스트 서버.

실행:
    python -m uvicorn app.local_dev_server:app --host 127.0.0.1 --port 8000

실제 Gemini 답변까지 확인하려면 ``LOCAL_LLM_ENABLED=1``과
``GOOGLE_API_KEY``를 설정한다. 기본값은 외부 호출이 없는 로컬 데모 모드다.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
LOCAL_LLM_ENABLED = os.environ.get("LOCAL_LLM_ENABLED", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

if LOCAL_LLM_ENABLED:
    if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        raise RuntimeError(
            "LOCAL_LLM_ENABLED=1인 경우 GOOGLE_API_KEY 또는 "
            "GEMINI_API_KEY가 필요합니다. .env 또는 실행 환경에 설정하세요."
        )
else:
    # app.core.config는 Google 연동 키를 확인하므로 로컬 데모에서만 placeholder를 넣는다.
    os.environ.setdefault("GOOGLE_API_KEY", "local-demo-key")

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import SEARCH_COLLECTIONS
from app.core.state import state
from app.routers import ask, chat, intent
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.local_dev import (
    LocalAnswerChain,
    LocalSearchService,
    build_local_chat_orchestrator,
    build_local_query_resolver,
)
from app.services.query_confirmation import QueryConfirmationStore
from app.services.general_chat import build_general_chat_chain
from app.services.grounded_rag import build_grounded_rag_service
from app.services.rag import build_answer_chain


@asynccontextmanager
async def lifespan(app: FastAPI):
    resolver = build_local_query_resolver()
    vector_search = LocalSearchService(resolver)
    orchestrator = build_local_chat_orchestrator(vector_search, resolver)
    if LOCAL_LLM_ENABLED:
        grounded_rag_service = build_grounded_rag_service()
        general_chat_chain = build_general_chat_chain()
        answer_chain = build_answer_chain()
        llm_backend = "gemini"
    else:
        grounded_rag_service = orchestrator._grounded_rag_service
        general_chat_chain = orchestrator._general_chat_chain
        answer_chain = LocalAnswerChain()
        llm_backend = "local_demo"

    if LOCAL_LLM_ENABLED:
        orchestrator = ChatOrchestrator(
            vector_search=vector_search,
            intent_classifier=orchestrator._intent_classifier,
            grounded_rag_service=grounded_rag_service,
            general_chat_chain=general_chat_chain,
            search_collections=SEARCH_COLLECTIONS,
            top_k_per_collection=3,
            final_top_k=6,
            max_per_collection=2,
            min_score=0.0,
        )
    state.update(
        {
            "vector_search": vector_search,
            "query_resolver": resolver,
            "answer_chain": answer_chain,
            "grounded_rag_service": grounded_rag_service,
            "general_chat_chain": general_chat_chain,
            "intent_classifier": orchestrator._intent_classifier,
            "backend": vector_search.backend_name,
            "embed_model": vector_search.embed_model,
            "indexed_chunks": vector_search.counts(),
            "llm_backend": llm_backend,
            "ready": True,
            "chat_orchestrator": orchestrator,
            "query_confirmation_store": QueryConfirmationStore(),
        }
    )
    yield
    state.clear()


app = FastAPI(
    title="HEAPY RAG 로컬 테스트 서버",
    version="local-demo",
    lifespan=lifespan,
)
app.include_router(chat.router)
app.include_router(ask.router)
app.include_router(intent.router)

WEB_ROOT = Path(__file__).resolve().parent / "web"
app.mount("/assets", StaticFiles(directory=WEB_ROOT / "assets"), name="web-assets")


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(
        WEB_ROOT / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )
