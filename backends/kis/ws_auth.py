import requests


def get_approval_key(
    app_key: str,
    app_secret: str,
    base_url: str = "https://openapi.koreainvestment.com:9443",
    session: requests.Session | None = None,
) -> str:
    active_session = session or requests.Session()
    response = active_session.post(
        f"{base_url}/oauth2/Approval",
        json={
            "grant_type": "client_credentials",
            "appkey": app_key,
            "secretkey": app_secret,
        },
    )
    response.raise_for_status()
    return response.json()["approval_key"]
