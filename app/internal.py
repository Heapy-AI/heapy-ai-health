"""Spring Boot 전용 챗봇 진입점. 작성자: 김진우."""

import hmac
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.state import state


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class InternalChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contractVersion: Literal["1.0"]
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    summary: str = Field(default="", max_length=4000)
    persona: Literal["coach", "professional"] = "coach"
    personalContext: str = Field(default="", max_length=20000)

    @field_validator("message")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("질문을 입력해 주세요.")
        return value.strip()


def authorize(authorization: str = Header(default="")) -> None:
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(503, "내부 인증 설정이 준비되지 않았습니다.")
    if not hmac.compare_digest(authorization.encode(), ("Bearer " + expected).encode()):
        raise HTTPException(401, "내부 인증이 필요합니다.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(os.environ.get("INTERNAL_SERVICE_TOKEN", "")) < 32:
        raise RuntimeError("내부 서비스 인증 설정이 필요합니다.")
    from app.core.runtime import lifespan as initialize
    async with initialize(app):
        yield


app = FastAPI(title="HEAPY 내부 챗봇", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def limit_body(request, call_next):
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 262144:
            return JSONResponse(status_code=413, content={"code": "PAYLOAD_TOO_LARGE"})
        chunks.append(chunk)
    request._body = b"".join(chunks)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    # 작성자: 김진우 — 검증 오류에 입력된 건강 문맥과 질문을 복제하지 않는다.
    return JSONResponse(status_code=422, content={"code": "INVALID_INPUT"})


@app.get("/health/ready")
def ready():
    if not state.get("ready") or not state.get("chat_orchestrator"):
        raise HTTPException(503, "모델을 준비 중입니다.")
    return {"status": "ready", "contractVersion": "1.0"}


@app.post("/internal/chat/answer", dependencies=[Depends(authorize)])
def answer(request: InternalChatRequest):
    orchestrator = state.get("chat_orchestrator")
    if not orchestrator:
        raise HTTPException(503, "챗봇이 준비되지 않았습니다.")
    try:
        result = orchestrator.answer(
            request.message, history=[turn.model_dump() for turn in request.history],
            summary=request.summary, persona=request.persona,
            personal_context_loader=lambda question, terms: request.personalContext or None,
        )
        citations = []
        if result.grounded:
            for key in result.cited_chunk_ids:
                if not key.startswith("C") or not key[1:].isdigit():
                    continue
                index = int(key[1:]) - 1
                if 0 <= index < len(result.documents):
                    metadata = result.documents[index].metadata
                    document_id = str(metadata.get("record_id", ""))[:200]
                    url = str(metadata.get("source_url", metadata.get("url", "")))[:2000]
                    if not url.startswith("https://"):
                        url = ""
                    if document_id or url:
                        citations.append({"title": str(metadata.get("title", metadata.get("source", "건강정보 근거")))[:300],
                                          "documentId": document_id or None, "sourceUrl": url or None})
        if not result.answer.strip() or len(result.answer) > 16000:
            raise ValueError("응답 형식 오류")
        return {"answer": result.answer, "citations": citations[:12],
                "summary": result.conversation_summary[:4000],
                "metadata": {"intent": result.intent.value, "emergency": result.emergency,
                             "personalContextUsed": result.personal_context_used}}
    except Exception:
        # 작성자: 김진우 — 공급자 예외의 요청 본문·키를 응답이나 로그에 남기지 않는다.
        raise HTTPException(503, "챗봇 응답을 완료하지 못했습니다.") from None
