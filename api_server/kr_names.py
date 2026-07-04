"""KR 종목코드 → 종목명 리졸버 (pykrx, 메모리 캐시).

KIS 모의 보유 조회가 name을 코드로만 주는 경우 보강용.
pykrx get_market_ticker_name = 단건 조회, 캐시로 반복 네트워크 방지."""
from __future__ import annotations

import threading

_lock = threading.Lock()
_cache: dict[str, str] = {}


def name_for(code: str) -> str | None:
    """종목코드(6자리) → 한글 종목명. 실패 시 None."""
    c = str(code or "").strip().zfill(6)
    if not c.isdigit():
        return None
    with _lock:
        if c in _cache:
            return _cache[c] or None
    nm: str | None = None
    try:
        from pykrx import stock
        raw = stock.get_market_ticker_name(c)
        if raw and isinstance(raw, str) and not raw.startswith("KRX"):
            nm = raw.strip()
    except Exception:  # noqa: BLE001
        nm = None
    with _lock:
        _cache[c] = nm or ""   # 실패도 캐시(음수 캐시, 반복 조회 방지)
    return nm


def names_for(codes: list[str]) -> dict[str, str]:
    return {c: (name_for(c) or c) for c in codes}
