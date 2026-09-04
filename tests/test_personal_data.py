"""'내건강' 개인 검진·생활 데이터 API 계약 테스트.

작성자: 고수연
"""

import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import personal_data
from app.routers.auth import AuthenticatedSession, require_current_session
from app.services.supabase_conversation import SupabaseConversationError
from app.services.supabase_personal_data import SupabasePersonalDataService


CHECKUP_SNAPSHOT = {
    "measured_at": "2026-03-14",
    "items": [
        {
            "item_code": "FBS",
            "item_name": "공복혈당",
            "value": "104",
            "unit": "mg/dL",
            "status": "경계",
        }
    ],
}


def _rows_response(rows: list[dict]) -> Mock:
    """Data API 성공 응답을 흉내낸다."""
    response = Mock()
    response.ok = True
    response.json.return_value = rows
    return response


class PersonalDataApiTest(unittest.TestCase):
    """세션 사용자 기준 조회 계약과 오류 변환을 검증한다."""

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(personal_data.router)
        app.dependency_overrides[require_current_session] = lambda: AuthenticatedSession(
            user={"id": "user-id"},
            access_token="access-token",
        )
        self.app = app
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    @patch.object(personal_data.personal_data_service, "get_latest_checkup")
    def test_checkup_uses_session_user_and_token(self, get_latest_checkup) -> None:
        """클라이언트 입력이 아니라 검증된 세션 값으로만 조회한다."""
        get_latest_checkup.return_value = CHECKUP_SNAPSHOT

        response = self.client.get("/me/checkup")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["measured_at"], "2026-03-14")
        self.assertEqual(payload["items"][0]["item_name"], "공복혈당")
        get_latest_checkup.assert_called_once_with("access-token", "user-id", None)

    @patch.object(personal_data.personal_data_service, "get_latest_checkup")
    def test_checkup_passes_selected_record_id(self, get_latest_checkup) -> None:
        """드롭다운에서 고른 회차는 세션 토큰과 함께 그대로 전달한다."""
        get_latest_checkup.return_value = CHECKUP_SNAPSHOT

        response = self.client.get("/me/checkup", params={"record_id": "record-9"})

        self.assertEqual(response.status_code, 200)
        get_latest_checkup.assert_called_once_with(
            "access-token",
            "user-id",
            "record-9",
        )

    @patch.object(personal_data.personal_data_service, "get_checkup_records")
    def test_checkup_records_uses_session_user(self, get_checkup_records) -> None:
        """회차 목록도 세션 사용자 기준으로만 조회한다."""
        get_checkup_records.return_value = [
            {"record_id": "record-2", "measured_at": "2026-03-14"},
            {"record_id": "record-1", "measured_at": "2024-02-02"},
        ]

        response = self.client.get("/me/checkup/records")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["measured_at"], "2026-03-14")
        get_checkup_records.assert_called_once_with("access-token", "user-id")

    @patch.object(personal_data.personal_data_service, "get_latest_checkup")
    def test_checkup_without_record_returns_empty_payload(
        self,
        get_latest_checkup,
    ) -> None:
        """검진 기록이 없는 계정도 200으로 빈 상태를 그린다."""
        get_latest_checkup.return_value = None

        response = self.client.get("/me/checkup")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"measured_at": "", "items": []})

    @patch.object(personal_data.personal_data_service, "get_lifestyle_window")
    def test_lifestyle_returns_all_domains(self, get_lifestyle_window) -> None:
        """영역이 비어도 응답 형태는 유지한다."""
        get_lifestyle_window.return_value = {
            "window_days": 7,
            "activity": {
                "since": "2026-08-20",
                "until": "2026-08-26",
                "rows": [{"record_date": "2026-08-26", "steps": 8421}],
            },
            "exercise": {"since": "", "until": "", "rows": []},
            "bio": {"since": "", "until": "", "rows": []},
            "food": {"since": "", "until": "", "rows": []},
            "water": {"since": "", "until": "", "rows": []},
            "sleep": {"since": "", "until": "", "rows": []},
        }

        response = self.client.get("/me/lifestyle")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["window_days"], 7)
        self.assertEqual(payload["activity"]["since"], "2026-08-20")
        self.assertEqual(payload["activity"]["rows"][0]["steps"], 8421)
        self.assertEqual(payload["water"]["rows"], [])
        get_lifestyle_window.assert_called_once_with("access-token", "user-id", 7)

    @patch.object(personal_data.personal_data_service, "get_lifestyle_window")
    def test_storage_failure_maps_to_http_error(self, get_lifestyle_window) -> None:
        """저장소 연결 실패는 503으로 그대로 전달한다."""
        get_lifestyle_window.side_effect = SupabaseConversationError(
            "개인 데이터 저장소에 연결할 수 없습니다.",
            503,
        )

        response = self.client.get("/me/lifestyle")

        self.assertEqual(response.status_code, 503)
        self.assertIn("연결할 수 없습니다", response.json()["detail"])


class PersonalDataServiceTest(unittest.TestCase):
    """조회 범위와 항목명 병합 규칙을 검증한다."""

    def setUp(self) -> None:
        self.service = SupabasePersonalDataService(
            "https://project.supabase.co",
            "publishable-key",
            window_days=7,
            max_rows=500,
        )

    def test_latest_checkup_reads_one_record_and_merges_item_names(self) -> None:
        """최신 1회만 읽고 마스터의 항목명·단위를 붙인다."""

        def fake_get(url: str, **_: object) -> Mock:
            if "health_checkup_records" in url:
                return _rows_response(
                    [{"record_id": "record-1", "measured_at": "2026-03-14T00:00:00+00:00"}]
                )
            if "health_checkup_results" in url:
                return _rows_response(
                    [{"item_code": "FBS", "value": "104", "status": "경계"}]
                )
            return _rows_response(
                [
                    {
                        "item_code": "FBS",
                        "item_name": "공복혈당",
                        "standard_unit": "mg/dL",
                    }
                ]
            )

        with patch(
            "app.services.supabase_personal_data.requests.get",
            side_effect=fake_get,
        ) as requests_get:
            snapshot = self.service.get_latest_checkup("access-token", "user-id")

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["measured_at"], "2026-03-14")
        self.assertEqual(
            snapshot["items"],
            [
                {
                    "item_code": "FBS",
                    "item_name": "공복혈당",
                    "value": "104",
                    "unit": "mg/dL",
                    "status": "경계",
                }
            ],
        )
        record_url = requests_get.call_args_list[0].args[0]
        self.assertIn("order=measured_at.desc", record_url)
        self.assertIn("limit=1", record_url)
        self.assertIn("user_id=eq.user-id", record_url)

    def test_selected_record_query_keeps_session_user_filter(self) -> None:
        """선택 회차 조회도 본인 user_id 조건을 함께 걸어 남의 회차를 막는다."""

        def fake_get(url: str, **_: object) -> Mock:
            if "health_checkup_records" in url:
                return _rows_response(
                    [{"record_id": "record-9", "measured_at": "2024-02-02T00:00:00+00:00"}]
                )
            if "health_checkup_results" in url:
                return _rows_response([{"item_code": "FBS", "value": "98", "status": "정상"}])
            return _rows_response([])

        with patch(
            "app.services.supabase_personal_data.requests.get",
            side_effect=fake_get,
        ) as requests_get:
            snapshot = self.service.get_latest_checkup(
                "access-token",
                "user-id",
                "record-9",
            )

        assert snapshot is not None
        self.assertEqual(snapshot["measured_at"], "2024-02-02")
        record_url = requests_get.call_args_list[0].args[0]
        self.assertIn("user_id=eq.user-id", record_url)
        self.assertIn("record_id=eq.record-9", record_url)
        self.assertNotIn("limit=1", record_url)

    def test_other_user_record_id_returns_none(self) -> None:
        """RLS와 user_id 조건에 걸려 빈 결과면 조회 결과도 비운다."""
        with patch(
            "app.services.supabase_personal_data.requests.get",
            side_effect=lambda url, **_: _rows_response([]),
        ) as requests_get:
            snapshot = self.service.get_latest_checkup(
                "access-token",
                "user-id",
                "other-user-record",
            )

        self.assertIsNone(snapshot)
        self.assertEqual(len(requests_get.call_args_list), 1)

    def test_checkup_records_returns_latest_first(self) -> None:
        """회차 목록은 최신순으로 record_id와 검진일만 반환한다."""

        def fake_get(url: str, **_: object) -> Mock:
            return _rows_response(
                [
                    {"record_id": "record-2", "measured_at": "2026-03-14T00:00:00+00:00"},
                    {"record_id": "record-1", "measured_at": "2024-02-02T00:00:00+00:00"},
                    {"record_id": None, "measured_at": "2023-01-01T00:00:00+00:00"},
                ]
            )

        with patch(
            "app.services.supabase_personal_data.requests.get",
            side_effect=fake_get,
        ) as requests_get:
            records = self.service.get_checkup_records("access-token", "user-id")

        self.assertEqual(
            records,
            [
                {"record_id": "record-2", "measured_at": "2026-03-14"},
                {"record_id": "record-1", "measured_at": "2024-02-02"},
            ],
        )
        record_url = requests_get.call_args_list[0].args[0]
        self.assertIn("user_id=eq.user-id", record_url)
        self.assertIn("order=measured_at.desc", record_url)

    def test_lifestyle_window_anchors_on_latest_record_date(self) -> None:
        """오늘이 아니라 보유한 최신 기록일을 기준으로 7일을 자른다."""

        def fake_get(url: str, **_: object) -> Mock:
            if "limit=1" in url:
                if "lifestyle_activity" in url:
                    return _rows_response([{"record_date": "2026-08-26"}])
                return _rows_response([])
            return _rows_response(
                [{"record_date": "2026-08-26", "steps": 8421}]
            )

        with patch(
            "app.services.supabase_personal_data.requests.get",
            side_effect=fake_get,
        ) as requests_get:
            window = self.service.get_lifestyle_window("access-token", "user-id")

        self.assertEqual(window["window_days"], 7)
        self.assertEqual(window["activity"]["until"], "2026-08-26")
        self.assertEqual(window["activity"]["since"], "2026-08-20")
        self.assertEqual(window["activity"]["rows"][0]["steps"], 8421)
        self.assertEqual(window["exercise"], {"since": "", "until": "", "rows": []})

        window_urls = [
            call.args[0]
            for call in requests_get.call_args_list
            if "limit=1" not in call.args[0]
        ]
        self.assertEqual(len(window_urls), 1)
        self.assertIn("record_date=gte.2026-08-20", window_urls[0])
        self.assertIn("limit=500", window_urls[0])

    def test_domain_without_record_skips_window_query(self) -> None:
        """기록이 없는 영역은 구간 조회를 보내지 않는다."""
        with patch(
            "app.services.supabase_personal_data.requests.get",
            side_effect=lambda url, **_: _rows_response([]),
        ) as requests_get:
            window = self.service.get_lifestyle_window("access-token", "user-id")

        for domain in ("activity", "exercise", "bio", "food", "water"):
            self.assertEqual(window[domain], {"since": "", "until": "", "rows": []})
        self.assertEqual(len(requests_get.call_args_list), 6)

    def test_unconfigured_service_returns_empty_shape(self) -> None:
        """Supabase 미설정 로컬 환경에서도 응답 형태를 유지한다."""
        service = SupabasePersonalDataService("", "")

        self.assertIsNone(service.get_latest_checkup("access-token", "user-id"))
        self.assertEqual(service.get_checkup_records("access-token", "user-id"), [])
        window = service.get_lifestyle_window("access-token", "user-id")
        self.assertEqual(window["window_days"], 7)
        self.assertEqual(window["bio"]["rows"], [])


if __name__ == "__main__":
    unittest.main()
