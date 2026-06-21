from unittest.mock import MagicMock

from backends.kis.ws_auth import get_approval_key


def test_get_approval_key_posts_credentials_and_returns_key():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"approval_key": "approval-abc123"}
    response.raise_for_status.return_value = None
    session.post.return_value = response

    key = get_approval_key(app_key="key", app_secret="secret", session=session)

    assert key == "approval-abc123"
    session.post.assert_called_once()
    call_kwargs = session.post.call_args.kwargs
    assert call_kwargs["json"]["grant_type"] == "client_credentials"
    assert call_kwargs["json"]["appkey"] == "key"
    assert call_kwargs["json"]["secretkey"] == "secret"
    url = session.post.call_args.args[0]
    assert url.endswith("/oauth2/Approval")
