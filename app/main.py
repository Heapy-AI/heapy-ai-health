from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import (
    CONVERSATION_SUMMARY_ENABLED,
    INTENT_MIN_CONFIDENCE,
    INTENT_MODEL_PATH,
    QUERY_RESOLUTION_AMBIGUITY_MARGIN,
    QUERY_RESOLUTION_MIN_SCORE,
    QUERY_REWRITE_ENABLED,
    RDB_DSN,
    SEARCH_COLLECTIONS,
    SEARCH_FINAL_TOP_K,
    SEARCH_MAX_PER_COLLECTION,
    SEARCH_MIN_SCORE,
    SEARCH_TOP_K_PER_COLLECTION,
    SUPABASE_PUBLISHABLE_KEY,
    SUPABASE_URL,
)
from app.core.state import state
from app.routers import ask, auth, chat, checkup_report, conversations, intent, personal_data
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.conversation_summary import build_conversation_summarizer
from app.services.general_chat import build_general_chat_chain
from app.services.grounded_rag import build_grounded_rag_service
from app.services.intent_classifier import LinearIntentClassifier
from app.services.query_confirmation import QueryConfirmationStore
from app.services.query_resolver import build_query_resolver
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
    query_resolver = build_query_resolver(
        RDB_DSN,
        supabase_url=SUPABASE_URL,
        supabase_publishable_key=SUPABASE_PUBLISHABLE_KEY,
        min_score=QUERY_RESOLUTION_MIN_SCORE,
        ambiguity_margin=QUERY_RESOLUTION_AMBIGUITY_MARGIN,
    )
    state["query_resolver"] = query_resolver
    conversation_summarizer = (
        build_conversation_summarizer() if CONVERSATION_SUMMARY_ENABLED else None
    )
    state["conversation_summarizer"] = conversation_summarizer
    confirmation_store = QueryConfirmationStore()
    state["query_confirmation_store"] = confirmation_store
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
        query_resolver=query_resolver,
        conversation_summarizer=conversation_summarizer,
        confirmation_store=confirmation_store,
    )

    medical_term_backend = (
        "RDB"
        if RDB_DSN
        else "Supabase RPC"
        if SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY
        else "미연결"
    )
    print(
        "[lifespan] 멀티턴 질문 재작성 "
        + ("활성" if query_rewriter is not None else "비활성")
        + " · 대화 요약 "
        + ("활성" if conversation_summarizer is not None else "비활성")
        + " · 의료용어 저장소 "
        + medical_term_backend
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
app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(personal_data.router)
app.include_router(checkup_report.router)
app.include_router(chat.router)
app.include_router(ask.router)
app.include_router(intent.router)

FRONTEND_ROOT = Path(__file__).resolve().parent / "frontends"
USER_FRONTEND_ROOT = FRONTEND_ROOT / "user"
SHARED_FRONTEND_ROOT = FRONTEND_ROOT / "shared"
app.mount(
    "/assets",
    StaticFiles(directory=USER_FRONTEND_ROOT / "assets"),
    name="user-assets",
)
app.mount(
    "/images",
    StaticFiles(directory=SHARED_FRONTEND_ROOT / "images"),
    name="shared-images",
)


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    """HEAPY 사용자 웹 앱을 반환한다.

    작성자: 김진우
    """
    return FileResponse(USER_FRONTEND_ROOT / "index.html")

# 실행 명령어: uvicorn app.main:app --reload
