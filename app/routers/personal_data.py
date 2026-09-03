"""로그인 사용자 본인의 검진·생활 데이터 조회 API.

user_id는 클라이언트 입력을 받지 않고 검증된 세션에서만 꺼낸다. 조회는 사용자
access token으로 수행되므로 본인 행 격리는 Supabase RLS(004·006)가 보장한다.

작성자: 고수연
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import (
    PERSONAL_DATA_MAX_ROWS,
    PERSONAL_DATA_WINDOW_DAYS,
    SUPABASE_PUBLISHABLE_KEY,
    SUPABASE_URL,
)
from app.routers.auth import AuthenticatedSession, require_current_session
from app.schemas.personal_data import (
    LatestCheckupResponse,
    LifestyleWindowResponse,
)
from app.services.supabase_conversation import SupabaseConversationError
from app.services.supabase_personal_data import SupabasePersonalDataService


router = APIRouter(prefix="/me", tags=["personal-data"])
personal_data_service = SupabasePersonalDataService(
    SUPABASE_URL,
    SUPABASE_PUBLISHABLE_KEY,
    window_days=PERSONAL_DATA_WINDOW_DAYS,
    max_rows=PERSONAL_DATA_MAX_ROWS,
)


def _raise_personal_data_error(error: SupabaseConversationError) -> None:
    """개인 데이터 저장소 오류를 HTTP 오류로 변환한다."""
    status_code = error.status_code if error.status_code in {400, 404, 409, 503} else 502
    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.get("/checkup", response_model=LatestCheckupResponse)
def get_latest_checkup(
    session: AuthenticatedSession = Depends(require_current_session),
) -> LatestCheckupResponse:
    """현재 사용자의 가장 최근 검진 1회 수치를 반환한다."""
    try:
        snapshot = personal_data_service.get_latest_checkup(
            session.access_token,
            str(session.user.get("id", "")),
        )
    except SupabaseConversationError as error:
        _raise_personal_data_error(error)
        raise

    # 검진 기록이 없는 계정도 정상 응답으로 다뤄 화면이 빈 상태를 그리게 한다.
    return LatestCheckupResponse(**(snapshot or {}))


@router.get("/lifestyle", response_model=LifestyleWindowResponse)
def get_lifestyle_window(
    window_days: int = Query(7, ge=7, le=365),
    session: AuthenticatedSession = Depends(require_current_session),
) -> LifestyleWindowResponse:
    """현재 사용자의 최신 1주일치 생활 데이터를 반환한다."""
    try:
        window = personal_data_service.get_lifestyle_window(
            session.access_token,
            str(session.user.get("id", "")),
            window_days,
        )
    except SupabaseConversationError as error:
        _raise_personal_data_error(error)
        raise

    return LifestyleWindowResponse(**window)
