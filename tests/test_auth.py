import time
from unittest.mock import MagicMock

import pytest

from backends.kis.auth import KISAuth


def _mock_session(token: str = "tok123", expires_in: int = 86400) -> MagicMock:
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": expires_in,
    }
    response.raise_for_status.return_value = None
    session.post.return_value = response
    return session


def test_get_access_token_fetches_and_returns_token():
    session = _mock_session(token="abc")
    auth = KISAuth(app_key="key", app_secret="secret", session=session)

    token = auth.get_access_token()

    assert token == "abc"
    session.post.assert_called_once()
    call_kwargs = session.post.call_args.kwargs
    assert call_kwargs["json"]["appkey"] == "key"
    assert call_kwargs["json"]["appsecret"] == "secret"
    assert call_kwargs["json"]["grant_type"] == "client_credentials"


def test_get_access_token_reuses_cached_token():
    session = _mock_session(token="abc")
    auth = KISAuth(app_key="key", app_secret="secret", session=session)

    first = auth.get_access_token()
    second = auth.get_access_token()

    assert first == second == "abc"
    session.post.assert_called_once()


def test_get_access_token_refreshes_when_near_expiry():
    session = _mock_session(token="abc", expires_in=86400)
    auth = KISAuth(app_key="key", app_secret="secret", session=session)
    auth.get_access_token()

    auth._expires_at = time.time() + 10  # within the 60s refresh window

    session.post.return_value.json.return_value["access_token"] = "def"
    second = auth.get_access_token()

    assert second == "def"
    assert session.post.call_count == 2
