"""Regresión de rutas para el segundo factor antes de crear sesiones."""
import asyncio
from unittest.mock import Mock, patch

from fastapi import HTTPException, Request, Response

from api.auth_routes import mfa_challenge_verify
from api.schemas import MfaChallengeVerifyRequest


def _request(host: str) -> Request:
    request = Mock(spec=Request)
    request.client.host = host
    request.headers.get.return_value = "mfa-route-test"
    return request


def test_invalid_mfa_challenge_never_creates_session():
    request = _request("198.51.100.21")
    with patch("api.auth_routes.settings.auth_enabled", True):
        with patch("api.auth_routes._enforce_rate_limit"):
            with patch("api.auth_routes.verify_login_challenge", return_value=None) as verify:
                with patch("api.auth_routes.create_session") as create:
                    try:
                        asyncio.run(mfa_challenge_verify(
                            MfaChallengeVerifyRequest(
                                challenge_token="opaque-login-challenge",
                                code="123456",
                            ),
                            request,
                            Response(),
                            None,
                        ))
                    except HTTPException as exc:
                        assert exc.status_code == 401
                    else:
                        raise AssertionError("Un desafío inválido no debe autenticar")

    assert verify.call_args.kwargs["expected_purpose"] == "login"
    create.assert_not_called()


def test_valid_mfa_challenge_creates_session_and_sets_no_store_cookies():
    request = _request("198.51.100.22")
    response = Response()
    with patch("api.auth_routes.settings.auth_enabled", True):
        with patch("api.auth_routes._enforce_rate_limit"):
            with patch("api.auth_routes.verify_login_challenge", return_value="user-123") as verify:
                with patch("api.auth_routes.create_session", return_value=("session-token", "csrf-token")) as create:
                    result = asyncio.run(mfa_challenge_verify(
                        MfaChallengeVerifyRequest(
                            challenge_token="opaque-login-challenge",
                            code="123456",
                        ),
                        request,
                        response,
                        None,
                    ))

    assert result["status"] == "authenticated"
    assert verify.call_args.kwargs["expected_purpose"] == "login"
    create.assert_called_once()
    assert response.headers["cache-control"] == "no-store"
    assert "axion_session=session-token" in response.headers["set-cookie"]


def test_oauth_cookie_requires_oauth_purpose_before_session_creation():
    request = _request("198.51.100.23")
    with patch("api.auth_routes.settings.auth_enabled", True):
        with patch("api.auth_routes._enforce_rate_limit"):
            with patch("api.auth_routes.verify_login_challenge", return_value=None) as verify:
                with patch("api.auth_routes.create_session") as create:
                    try:
                        asyncio.run(mfa_challenge_verify(
                            MfaChallengeVerifyRequest(code="123456"),
                            request,
                            Response(),
                            "opaque-oauth-challenge",
                        ))
                    except HTTPException as exc:
                        assert exc.status_code == 401
                    else:
                        raise AssertionError("Un desafío OAuth inválido no debe autenticar")

    assert verify.call_args.kwargs["challenge_token"] == "opaque-oauth-challenge"
    assert verify.call_args.kwargs["expected_purpose"] == "oauth"
    create.assert_not_called()
