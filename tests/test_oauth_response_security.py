"""Security headers for OAuth redirects, including error and MFA paths."""
import asyncio
from unittest.mock import Mock, patch

from fastapi import Request

from api.auth_routes import oauth_callback, oauth_start


def _request():
    request = Mock(spec=Request)
    request.client.host = "198.51.100.77"
    return request


async def _inline(function, *args, **kwargs):
    return function(*args, **kwargs)


def _assert_no_store_redirect(response):
    assert response.status_code in (302, 303)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_oauth_start_redirect_has_no_store_and_no_referrer():
    with (
        patch("api.auth_routes.settings.auth_enabled", True),
        patch("api.auth_routes.settings.auth_cookie_secure", True),
        patch("api.auth_routes._enforce_rate_limit"),
        patch("api.auth_routes.run_in_threadpool", side_effect=_inline),
        patch("api.auth_routes.begin", return_value=("https://accounts.example/authorize?state=opaque", "opaque-state")),
    ):
        response = asyncio.run(oauth_start("google", _request(), terms_accepted=True))

    _assert_no_store_redirect(response)
    cookies = response.headers.getlist("set-cookie")
    state_cookie = next(value for value in cookies if value.startswith("axion_oauth_state="))
    assert "httponly" in state_cookie.lower()
    assert "secure" in state_cookie.lower()


def test_oauth_cancelled_callback_redirect_has_no_store_and_no_referrer():
    with (
        patch("api.auth_routes.settings.auth_enabled", True),
        patch("api.auth_routes._enforce_rate_limit"),
    ):
        response = asyncio.run(oauth_callback(
            "google", _request(), code="authorization-code",
            state="provider-state", browser_state="different-state",
        ))

    _assert_no_store_redirect(response)


def test_oauth_failed_callback_redirect_has_no_store_and_no_referrer():
    with (
        patch("api.auth_routes.settings.auth_enabled", True),
        patch("api.auth_routes._enforce_rate_limit"),
        patch("api.auth_routes.run_in_threadpool", side_effect=_inline),
        patch("api.auth_routes.consume_state", side_effect=ValueError("invalid state")),
    ):
        response = asyncio.run(oauth_callback(
            "github", _request(), code="authorization-code",
            state="matching-state", browser_state="matching-state",
        ))

    _assert_no_store_redirect(response)


def test_oauth_mfa_callback_redirect_has_no_store_and_no_referrer():
    user = {"id": "user-1", "email": "user@example.invalid"}
    with (
        patch("api.auth_routes.settings.auth_enabled", True),
        patch("api.auth_routes._enforce_rate_limit"),
        patch("api.auth_routes.run_in_threadpool", side_effect=_inline),
        patch("api.auth_routes.consume_state", return_value={"terms_accepted": True, "nonce": "nonce"}),
        patch("api.auth_routes.provider_profile", return_value={"email": user["email"], "subject": "subject", "name": "User"}),
        patch("api.auth_routes.resolve_user", return_value=user),
        patch("api.auth_routes.is_mfa_enabled", return_value=True),
        patch("api.auth_routes.issue_login_challenge", return_value="opaque-challenge"),
    ):
        response = asyncio.run(oauth_callback(
            "google", _request(), code="authorization-code",
            state="matching-state", browser_state="matching-state",
        ))

    _assert_no_store_redirect(response)
    cookies = response.headers.getlist("set-cookie")
    assert any(value.startswith("axion_mfa_challenge=") for value in cookies)


def test_oauth_success_callback_redirect_has_no_store_and_no_referrer():
    user = {"id": "user-2", "email": "user@example.invalid"}
    with (
        patch("api.auth_routes.settings.auth_enabled", True),
        patch("api.auth_routes._enforce_rate_limit"),
        patch("api.auth_routes.run_in_threadpool", side_effect=_inline),
        patch("api.auth_routes.consume_state", return_value={"terms_accepted": True, "nonce": "nonce"}),
        patch("api.auth_routes.provider_profile", return_value={"email": user["email"], "subject": "subject", "name": "User"}),
        patch("api.auth_routes.resolve_user", return_value=user),
        patch("api.auth_routes.is_mfa_enabled", return_value=False),
        patch("api.auth_routes.create_session", return_value=("session-token", "csrf-token")),
    ):
        response = asyncio.run(oauth_callback(
            "google", _request(), code="authorization-code",
            state="matching-state", browser_state="matching-state",
        ))

    _assert_no_store_redirect(response)
    cookies = response.headers.getlist("set-cookie")
    assert any(value.startswith("axion_session=session-token") for value in cookies)
