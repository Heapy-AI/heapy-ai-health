"""Supabase 로그인·세션 API 테스트.

작성자: 김진우
"""

import unittest
from unittest.mock import Mock, PropertyMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import auth


class SupabaseAuthApiTest(unittest.TestCase):
    """토큰 비노출과 보안 쿠키 기반 세션 계약을 검증한다."""

    def setUp(self) -> None:
        auth._verified_user_cache.clear()
        app = FastAPI()
        app.include_router(auth.router)
        self.client = TestClient(app)

    @patch.object(auth.auth_service, "sign_in")
    def test_login_sets_http_only_cookies_without_exposing_tokens(self, sign_in: Mock) -> None:
        sign_in.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "user": {
                "id": "user-id",
                "email": "user@example.com",
                "user_metadata": {"display_name": "김진우"},
            },
        }

        response = self.client.post(
            "/auth/login",
            json={"email": "USER@example.com", "password": "password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["display_name"], "김진우")
        self.assertNotIn("access_token", response.json())
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertEqual(response.cookies.get(auth.ACCESS_COOKIE), "access-token")
        sign_in.assert_called_once_with("user@example.com", "password")

    @patch.object(auth.auth_service, "get_user")
    def test_me_validates_access_token_with_supabase(self, get_user: Mock) -> None:
        get_user.return_value = {
            "id": "user-id",
            "email": "user@example.com",
            "user_metadata": {},
        }
        self.client.cookies.set(auth.ACCESS_COOKIE, "access-token")

        with patch.object(
            type(auth.auth_service),
            "configured",
            new_callable=PropertyMock,
            return_value=True,
        ):
            response = self.client.get("/auth/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "user-id")
        get_user.assert_called_once_with("access-token")

    @patch.object(auth.auth_service, "get_user")
    def test_me_reuses_recent_user_verification(self, get_user: Mock) -> None:
        get_user.return_value = {
            "id": "cached-user-id",
            "email": "cached@example.com",
            "user_metadata": {},
        }
        self.client.cookies.set(auth.ACCESS_COOKIE, "cached-access-token")

        with patch.object(
            type(auth.auth_service),
            "configured",
            new_callable=PropertyMock,
            return_value=True,
        ):
            first = self.client.get("/auth/me")
            second = self.client.get("/auth/me")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        get_user.assert_called_once_with("cached-access-token")

    @patch.object(auth.auth_service, "sign_up")
    def test_signup_creates_profile_metadata_and_session_cookie(
        self,
        sign_up: Mock,
    ) -> None:
        sign_up.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "user": {"id": "user-id", "email": "user@example.com"},
        }

        response = self.client.post(
            "/auth/signup",
            json={
                "email": "USER@example.com",
                "password": "password123",
                "name": "김진우",
                "birth_date": "1990-01-02",
                "sex": "Male",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["display_name"], "김진우")
        self.assertFalse(response.json()["email_confirmation_required"])
        self.assertEqual(response.cookies.get(auth.ACCESS_COOKIE), "access-token")
        sign_up.assert_called_once_with(
            "user@example.com",
            "password123",
            name="김진우",
            birth_date="1990-01-02",
            sex="Male",
        )


if __name__ == "__main__":
    unittest.main()
