"""Tests for core.cdn_auth — JWT session token lifecycle."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from sims4_updater.core.cdn_auth import CDNAuth, CDNTokenAuth
from sims4_updater.core.exceptions import AccessRequiredError, BannedError


@pytest.fixture()
def auth():
    """Fresh CDNAuth instance."""
    return CDNAuth(
        api_url="https://api.example.com",
        machine_id="test-machine-id",
        uid="test-uid",
        app_version="1.0.0",
    )


class TestCDNAuth:
    def test_token_request_success(self, auth):
        """Successful token request should store the token."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"token": "jwt-123", "expires_in": 3600}

        with patch("sims4_updater.core.cdn_auth.requests.post", return_value=mock_resp):
            token = auth.get_token()

        assert token == "jwt-123"

    def test_token_cached_until_expiry(self, auth):
        """Token should be reused when not near expiry."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"token": "jwt-cached", "expires_in": 3600}

        mock_post = MagicMock(return_value=mock_resp)
        with patch("sims4_updater.core.cdn_auth.requests.post", mock_post):
            t1 = auth.get_token()
            t2 = auth.get_token()

        assert t1 == t2
        mock_post.assert_called_once()  # Only one HTTP call

    def test_token_refreshes_near_expiry(self, auth):
        """Token should refresh when < 60s remaining."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"token": "jwt-new", "expires_in": 3600}

        with patch("sims4_updater.core.cdn_auth.requests.post", return_value=mock_resp):
            auth.get_token()

        # Simulate near-expiry by setting expires_at to now
        auth._expires_at = time.monotonic() + 30  # < 60s
        auth._last_refresh_attempt = 0  # Reset cooldown so refresh proceeds

        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {"token": "jwt-refreshed", "expires_in": 3600}

        with patch("sims4_updater.core.cdn_auth.requests.post", return_value=mock_resp2):
            token = auth.get_token()

        assert token == "jwt-refreshed"

    def test_banned_raises_error(self, auth):
        """403 with ban reason should raise BannedError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {
            "error": "banned",
            "reason": "Abuse detected",
            "ban_type": "machine",
            "expires_at": "2026-03-01T00:00:00Z",
        }

        with (
            patch("sims4_updater.core.cdn_auth.requests.post", return_value=mock_resp),
            pytest.raises(BannedError) as exc_info,
        ):
            auth.get_token()

        assert "Abuse detected" in str(exc_info.value)

    def test_access_required_raises_error(self, auth):
        """403 with access_required should raise AccessRequiredError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {
            "error": "access_required",
            "cdn_name": "Private CDN",
            "request_url": "/access/request",
        }

        with (
            patch("sims4_updater.core.cdn_auth.requests.post", return_value=mock_resp),
            pytest.raises(AccessRequiredError) as exc_info,
        ):
            auth.get_token()

        assert exc_info.value.cdn_name == "Private CDN"

    def test_network_error_raises(self, auth):
        """Network errors should raise RuntimeError after failed refresh."""
        import requests

        with (
            patch(
                "sims4_updater.core.cdn_auth.requests.post",
                side_effect=requests.ConnectionError("offline"),
            ),
            pytest.raises(RuntimeError, match="Token refresh failed"),
        ):
            auth.get_token()

    def test_non_200_raises(self, auth):
        """Non-200/403 response should raise RuntimeError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with (
            patch("sims4_updater.core.cdn_auth.requests.post", return_value=mock_resp),
            pytest.raises(RuntimeError, match="Token refresh failed"),
        ):
            auth.get_token()


class TestCDNTokenAuth:
    def test_injects_auth_header(self, auth):
        """CDNTokenAuth should add Authorization header to requests."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"token": "jwt-inject", "expires_in": 3600}

        with patch("sims4_updater.core.cdn_auth.requests.post", return_value=mock_resp):
            # Pre-fetch the token so it's cached
            auth.get_token()
            adapter = auth.get_auth_adapter()

            assert isinstance(adapter, CDNTokenAuth)

            # Simulate a PreparedRequest
            mock_request = MagicMock()
            mock_request.headers = {}
            result = adapter(mock_request)

        assert result.headers["Authorization"] == "Bearer jwt-inject"

    def test_skips_header_when_no_token(self):
        """If no token available, Authorization header should not be set."""
        auth = CDNAuth(
            api_url="https://api.example.com",
            machine_id="mid",
            uid="uid",
            app_version="1.0",
        )
        # Simulate token failure
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("sims4_updater.core.cdn_auth.requests.post", return_value=mock_resp):
            adapter = auth.get_auth_adapter()

            mock_request = MagicMock()
            mock_request.headers = {}
            result = adapter(mock_request)

        assert "Authorization" not in result.headers


class TestCooldown:
    def test_cooldown_logs_warning_when_no_token(self, auth):
        """When cooldown is active and no valid token, should log a warning."""
        import requests as req_lib

        # First attempt: network error → sets last_refresh_attempt
        with (
            patch(
                "sims4_updater.core.cdn_auth.requests.post",
                side_effect=req_lib.ConnectionError("offline"),
            ),
            pytest.raises(RuntimeError),
        ):
            auth.get_token()

        # Second attempt within cooldown: should log warning and raise
        with (
            patch("sims4_updater.core.cdn_auth.requests.post") as mock_post,
            patch("sims4_updater.core.cdn_auth.log") as mock_log,
            pytest.raises(RuntimeError, match="Token refresh failed"),
        ):
            auth.get_token()

        # Should NOT have made a new network request (cooldown active)
        mock_post.assert_not_called()
        # Should have logged a warning about cooldown
        mock_log.warning.assert_called()
        assert "cooldown" in mock_log.warning.call_args[0][0].lower()

    def test_cooldown_keeps_valid_token(self, auth):
        """When cooldown is active but token is still valid, return it."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"token": "jwt-valid", "expires_in": 3600}

        with patch("sims4_updater.core.cdn_auth.requests.post", return_value=mock_resp):
            token = auth.get_token()

        assert token == "jwt-valid"

        # Force near-cooldown state (recent attempt, but token still valid)
        auth._last_refresh_attempt = time.monotonic()
        auth._expires_at = time.monotonic() + 30  # < 60s but still valid

        # This should return the cached token without hitting the network
        with patch("sims4_updater.core.cdn_auth.requests.post"):
            # Token is near expiry (< 60s) so get_token will try to refresh
            # But cooldown is active and token hasn't expired yet
            token2 = auth.get_token()

        assert token2 == "jwt-valid"


class TestRequestAccess:
    def test_request_access_success(self, auth):
        """Access request should POST to the correct endpoint."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok", "message": "Submitted"}

        with patch(
            "sims4_updater.core.cdn_auth.requests.post",
            return_value=mock_resp,
        ) as mock_post:
            result = auth.request_access(reason="I need access")

        assert result["status"] == "ok"
        call_kwargs = mock_post.call_args
        assert "/access/request" in call_kwargs[0][0]
        body = call_kwargs[1]["json"]
        assert body["reason"] == "I need access"
        assert body["machine_id"] == "test-machine-id"
