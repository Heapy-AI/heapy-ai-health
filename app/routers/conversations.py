"""로그인 사용자의 챗봇 대화 세션 API.

작성자: 김진우
"""

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Response

from app.routers.auth import (
    AuthenticatedSession,
    conversation_service,
    require_current_session,
)
from app.schemas.conversation import (
    ConversationDetailResponse,
    ConversationMessageResponse,
    ConversationSessionResponse,
)
from app.services.supabase_conversation import SupabaseConversationError


router = APIRouter(prefix="/conversations", tags=["conversations"])


def _raise_conversation_error(error: SupabaseConversationError) -> None:
    """대화 저장소 오류를 HTTP 오류로 변환한다."""
    status_code = error.status_code if error.status_code in {400, 404, 409, 503} else 502
    raise HTTPException(status_code=status_code, detail=str(error)) from error


def _to_session(row: dict) -> ConversationSessionResponse:
    """Data API 행을 세션 응답으로 변환한다."""
    return ConversationSessionResponse(
        session_id=str(row.get("session_id", "")),
        title=str(row.get("title") or "새 대화"),
        summary=str(row.get("summary") or ""),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("", response_model=list[ConversationSessionResponse])
def list_conversations(
    session: AuthenticatedSession = Depends(require_current_session),
) -> list[ConversationSessionResponse]:
    """현재 사용자의 대화 세션 목록을 반환한다."""
    try:
        return [
            _to_session(row)
            for row in conversation_service.list_sessions(session.access_token)
        ]
    except SupabaseConversationError as error:
        _raise_conversation_error(error)
    return []


@router.post("", response_model=ConversationSessionResponse)
def create_conversation(
    session: AuthenticatedSession = Depends(require_current_session),
) -> ConversationSessionResponse:
    """새 대화 세션을 생성한다."""
    try:
        row = conversation_service.create_session(
            session.access_token,
            str(session.user.get("id", "")),
        )
        return _to_session(row)
    except SupabaseConversationError as error:
        _raise_conversation_error(error)
    raise HTTPException(status_code=500, detail="대화 세션 생성에 실패했습니다.")


@router.get("/{session_id}", response_model=ConversationDetailResponse)
def get_conversation(
    session_id: str,
    session: AuthenticatedSession = Depends(require_current_session),
) -> ConversationDetailResponse:
    """선택한 세션과 저장된 전체 메시지를 반환한다."""
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            session_future = executor.submit(
                conversation_service.get_session,
                session.access_token,
                session_id,
            )
            messages_future = executor.submit(
                conversation_service.get_messages,
                session.access_token,
                session_id,
            )
            session_row = session_future.result()
            message_rows = messages_future.result()
        return ConversationDetailResponse(
            session=_to_session(session_row),
            messages=[ConversationMessageResponse(**row) for row in message_rows],
        )
    except SupabaseConversationError as error:
        _raise_conversation_error(error)
    raise HTTPException(status_code=500, detail="대화를 불러오지 못했습니다.")


@router.delete("/{session_id}", status_code=204)
def delete_conversation(
    session_id: str,
    session: AuthenticatedSession = Depends(require_current_session),
) -> Response:
    """현재 사용자가 소유한 대화 세션을 삭제한다."""
    try:
        conversation_service.delete_session(session.access_token, session_id)
    except SupabaseConversationError as error:
        _raise_conversation_error(error)
    return Response(status_code=204)
