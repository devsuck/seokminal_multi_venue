import hashlib
import json
import time
from pathlib import Path

import requests

# 토큰 캐시 파일 위치 (프로세스 간 공유)
_CACHE_DIR = Path.home() / ".cache" / "kis_tokens"


class KISAuth:
    """Fetches and caches a KIS OAuth2 access token.

    Token is persisted to ~/.cache/kis_tokens/<key_hash>.json so that
    separate Python processes reuse the same token and avoid KIS rate limits
    on the tokenP endpoint.
    """

    REFRESH_MARGIN_SECONDS = 300  # 만료 5분 전에 갱신

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        base_url: str = "https://openapi.koreainvestment.com:9443",
        session: requests.Session | None = None,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base_url = base_url
        self._session = session or requests.Session()
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._cache_file = _cache_file_for(app_key, base_url)
        self._load_cache()

    def get_access_token(self) -> str:
        if self._token is not None and time.time() < self._expires_at - self.REFRESH_MARGIN_SECONDS:
            return self._token
        return self._fetch_token()

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0
        if self._cache_file.exists():
            self._cache_file.unlink(missing_ok=True)

    def _load_cache(self) -> None:
        try:
            data = json.loads(self._cache_file.read_text())
            if time.time() < data["expires_at"] - self.REFRESH_MARGIN_SECONDS:
                self._token = data["token"]
                self._expires_at = data["expires_at"]
        except Exception:
            pass

    def _save_cache(self) -> None:
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(
                json.dumps({"token": self._token, "expires_at": self._expires_at})
            )
        except Exception:
            pass

    def _fetch_token(self) -> str:
        response = self._session.post(
            f"{self._base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            },
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        self._expires_at = time.time() + payload["expires_in"]
        self._save_cache()
        return self._token


def _cache_file_for(app_key: str, base_url: str) -> Path:
    key_hash = hashlib.sha256(f"{app_key}:{base_url}".encode()).hexdigest()[:16]
    return _CACHE_DIR / f"{key_hash}.json"
