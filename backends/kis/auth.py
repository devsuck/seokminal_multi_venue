import time

import requests


class KISAuth:
    """Fetches and caches a KIS OAuth2 access token."""

    REFRESH_MARGIN_SECONDS = 60

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

    def get_access_token(self) -> str:
        if self._token is not None and time.time() < self._expires_at - self.REFRESH_MARGIN_SECONDS:
            return self._token
        return self._fetch_token()

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
        return self._token
