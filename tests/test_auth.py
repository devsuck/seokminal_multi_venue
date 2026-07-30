import time
from unittest.mock import MagicMock

import pytest

from backends.kis import auth as kis_auth
from backends.kis.auth import KISAuth


@pytest.fixture(autouse=True)
def _isolated_token_cache(tmp_path, monkeypatch):
    # KISAuth는 ~/.cache/kis_tokens/<hash(app_key+base_url)>.json에 토큰을 영구
    # 캐시함(프로세스 간 공유 목적). 테스트가 고정 app_key="key"를 쓰면 이전 테스트
    # 실행이 남긴 파일을 다음 실행이 읽어버려 격리가 깨짐 — 실제로 이 문제 때문에
    # session mock을 무시하고 디스크의 stale 토큰을 반환해 테스트가 실패했었음.
    # 실제 KIS 캐시 디렉토리(~/.cache/kis_tokens)도 오염시키고 있었음.
    monkeypatch.setattr(kis_auth, "_CACHE_DIR", tmp_path / "kis_tokens")


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
