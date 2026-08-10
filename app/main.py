from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import (
    INTENT_MIN_CONFIDENCE,
    CONVERSATION_SUMMARY_ENABLED,
    QUERY_REWRITE_ENABLED,
    INTENT_MODEL_PATH,
    SEARCH_COLLECTIONS,
    SEARCH_FINAL_TOP_K,
    SEARCH_MAX_PER_COLLECTION,
    SEARCH_MIN_SCORE,
    SEARCH_TOP_K_PER_COLLECTION,
)
from app.core.state import state
from app.routers import ask, chat, intent
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.general_chat import build_general_chat_chain
from app.services.grounded_rag import build_grounded_rag_service
from app.services.intent_classifier import LinearIntentClassifier
from app.services.conversation_summary import build_conversation_summarizer
from app.services.query_rewriter import build_query_rewriter
from app.services.rag import build_answer_chain
from app.services.vector_search import build_pinecone_search_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 로컬 임베딩 모델과 Pinecone 검색을 준비한다."""
    vector_search = build_pinecone_search_service()
    counts = vector_search.counts()

    state["vector_search"] = vector_search
    state["answer_chain"] = build_answer_chain()
    grounded_rag_service = build_grounded_rag_service()
    state["grounded_rag_service"] = grounded_rag_service
    general_chat_chain = build_general_chat_chain()
    state["general_chat_chain"] = general_chat_chain
    query_rewriter = build_query_rewriter() if QUERY_REWRITE_ENABLED else None
    state["query_rewriter"] = query_rewriter
    conversation_summarizer = (
        build_conversation_summarizer() if CONVERSATION_SUMMARY_ENABLED else None
    )
    state["conversation_summarizer"] = conversation_summarizer
    state["backend"] = vector_search.backend_name
    state["embed_model"] = vector_search.embed_model
    state["indexed_chunks"] = counts
    state["ready"] = True

    if INTENT_MODEL_PATH.is_file():
        state["intent_classifier"] = LinearIntentClassifier.from_file(
            INTENT_MODEL_PATH,
            INTENT_MIN_CONFIDENCE,
        )
        print(
            f"[lifespan] intent 분류기 준비 완료 - "
            f"version={state['intent_classifier'].model_version}"
        )
    else:
        state["intent_classifier"] = None
        print(
            f"[lifespan] intent 모델 없음 - 학습 후 배치 필요: "
            f"{INTENT_MODEL_PATH}"
        )

    state["chat_orchestrator"] = ChatOrchestrator(
        vector_search=vector_search,
        intent_classifier=state["intent_classifier"],
        grounded_rag_service=grounded_rag_service,
        general_chat_chain=general_chat_chain,
        search_collections=SEARCH_COLLECTIONS,
        top_k_per_collection=SEARCH_TOP_K_PER_COLLECTION,
        final_top_k=SEARCH_FINAL_TOP_K,
        max_per_collection=SEARCH_MAX_PER_COLLECTION,
        min_score=SEARCH_MIN_SCORE,
        query_rewriter=query_rewriter,
        conversation_summarizer=conversation_summarizer,
    )

    print(
        "[lifespan] 멀티턴 질문 재작성 "
        + ("활성" if query_rewriter is not None else "비활성")
        + " · 대화 요약 "
        + ("활성" if conversation_summarizer is not None else "비활성")
    )

    print(
        f"[lifespan] 벡터 백엔드 준비 완료 - "
        f"backend={vector_search.backend_name}, model={vector_search.embed_model}"
    )
    for name, count in counts.items():
        print(f"[lifespan] '{name}' 청크 {count}개")

    yield                                    # 여기서부터 요청을 받습니다
    state.clear()                            # 종료 시 정리

app = FastAPI(title="HEAPY RAG 서빙", version="1.0", lifespan=lifespan)
app.include_router(chat.router)
app.include_router(ask.router)
app.include_router(intent.router)

WEB_ROOT = Path(__file__).resolve().parent / "web"
app.mount("/assets", StaticFiles(directory=WEB_ROOT / "assets"), name="web-assets")


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    """HEAPY 챗봇 시연용 웹 앱을 반환한다.

    작성자: 김진우
    """
    return FileResponse(WEB_ROOT / "index.html")

# 실행 명령어: uvicorn app.main:app --reload
# Gradio UI 실행: python run_ui.py
