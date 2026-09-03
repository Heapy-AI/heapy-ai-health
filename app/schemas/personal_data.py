"""'내건강' 화면의 개인 검진·생활 데이터 API 모델.

테이블 컬럼을 그대로 노출하지 않고 화면에 필요한 값만 계약으로 고정한다.

작성자: 고수연
"""

from typing import Any

from pydantic import BaseModel


class CheckupItemResponse(BaseModel):
    """검진 항목 한 건의 수치와 판정."""

    item_code: str
    item_name: str
    value: str = ""
    unit: str = ""
    status: str = ""


class LatestCheckupResponse(BaseModel):
    """가장 최근 검진 1회의 전체 항목."""

    measured_at: str = ""
    items: list[CheckupItemResponse] = []


class ActivityRowResponse(BaseModel):
    """일별 활동량 한 건."""

    record_date: str = ""
    steps: float | None = None
    floors_climbed: float | None = None
    active_time: float | None = None
    # lifestyle_activity.active_distance는 km 단위로 적재된다.
    active_distance: float | None = None
    active_calories: float | None = None


class ExerciseRowResponse(BaseModel):
    """운동 기록 한 건."""

    record_date: str = ""
    exercise_type: str = ""
    duration_sec: float | None = None
    # lifestyle_exercise.distance_m은 미터 단위이므로 화면에서 km로 환산한다.
    distance_m: float | None = None
    calories: float | None = None


class BioRowResponse(BaseModel):
    """신체·수면 지표 한 건."""

    measured_at: str = ""
    bio_type: str = ""
    value: float | None = None
    unit: str = ""
    # 혈압의 이완기, 혈당의 공복 여부처럼 값만으로 해석할 수 없는 정보가 담긴다.
    detail_data: dict[str, Any] = {}


class FoodRowResponse(BaseModel):
    """식사 기록 한 건."""

    consumed_at: str = ""
    meal_type: str = ""
    title: str = ""
    calories: float | None = None
    carbohydrate: float | None = None
    protein: float | None = None
    total_fat: float | None = None
    sodium: float | None = None
    sugar: float | None = None


class WaterRowResponse(BaseModel):
    """수분 섭취 기록 한 건."""

    consumed_at: str = ""
    water_amount: float | None = None


class ActivityWindowResponse(BaseModel):
    """조회 구간과 일별 활동량 목록."""

    since: str = ""
    until: str = ""
    rows: list[ActivityRowResponse] = []


class ExerciseWindowResponse(BaseModel):
    """조회 구간과 운동 기록 목록."""

    since: str = ""
    until: str = ""
    rows: list[ExerciseRowResponse] = []


class BioWindowResponse(BaseModel):
    """조회 구간과 신체·수면 지표 목록."""

    since: str = ""
    until: str = ""
    rows: list[BioRowResponse] = []


class FoodWindowResponse(BaseModel):
    """조회 구간과 식사 기록 목록."""

    since: str = ""
    until: str = ""
    rows: list[FoodRowResponse] = []


class WaterWindowResponse(BaseModel):
    """조회 구간과 수분 섭취 목록."""

    since: str = ""
    until: str = ""
    rows: list[WaterRowResponse] = []


class LifestyleWindowResponse(BaseModel):
    """생활 데이터 영역별 최신 구간 응답.

    구간 기준일은 영역마다 다를 수 있다. 기기 연동 상태에 따라 마지막 기록일이
    영역별로 갈리기 때문에 since·until을 영역 안에 함께 담는다.
    """

    window_days: int
    activity: ActivityWindowResponse
    exercise: ExerciseWindowResponse
    bio: BioWindowResponse
    food: FoodWindowResponse
    water: WaterWindowResponse
    sleep: BioWindowResponse
