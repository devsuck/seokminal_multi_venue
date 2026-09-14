"""Jina Reader(r.jina.ai) 무료 URL→본문텍스트 fetcher — Layer A 벤더 호출.
jarvis는 credential-free라 여기(api_server)에만 존재, jarvis 안에 안 둔다."""
from __future__ import annotations

import requests

_JINA_BASE = "https://r.jina.ai/"


def fetch_article_text(url: str, timeout: int = 10) -> str | None:
    """URL 기사 본문을 Jina Reader로 마크다운 텍스트로 가져온다. 키 불필요.
    실패(타임아웃/HTTP 에러/네트워크 오류/빈 본문)시 None — 호출부가 summary로 폴백."""
    if not url or not url.startswith("http"):
        return None
    try:
        resp = requests.get(f"{_JINA_BASE}{url}", timeout=timeout)
        resp.raise_for_status()
        text = resp.text.strip()
        return text or None
    except Exception:  # noqa: BLE001
        return None
