"""시장 컨텍스트 수집기 — VIX, 어닝 캘린더, 뉴스 헤드라인 (30분 캐시).

daytrade_tick 시작 시 한 번만 호출. Claude 프롬프트에 주입해 판단력 향상.
yfinance만 사용 (이미 설치됨, 추가 API 키 불필요).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

_log = logging.getLogger(__name__)
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict]] = {}  # {venue: (fetched_ts, data)}
_TTL = 1800  # 30분


def _fetch_vix() -> float | None:
    try:
        import yfinance as yf
        hist = yf.Ticker("^VIX").history(period="2d")
        return float(hist["Close"].iloc[-1]) if not hist.empty else None
    except Exception:
        return None


def _days_to_earnings(symbol: str) -> int | None:
    """다음 어닝까지 일수. 없거나 실패 시 None."""
    try:
        import yfinance as yf
        cal = yf.Ticker(symbol).calendar
        if cal is None:
            return None
        # yfinance 버전마다 dict 또는 DataFrame
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
        elif hasattr(cal, "columns") and "Earnings Date" in cal.columns:
            vals = cal["Earnings Date"].dropna()
            ed = vals.iloc[0] if len(vals) else None
        else:
            return None
        if ed is None:
            return None
        if isinstance(ed, (list, tuple)):
            ed = ed[0] if ed else None
        if ed is None:
            return None
        ed_date = ed.date() if hasattr(ed, "date") else ed
        today = datetime.now(timezone.utc).date()
        delta = (ed_date - today).days
        return max(delta, 0)
    except Exception:
        return None


def _fetch_news_headlines(symbols: list[str]) -> list[dict]:
    """yfinance .news 각 종목 최근 3건 헤드라인 수집 (최대 5종목)."""
    results = []
    try:
        import yfinance as yf
        for sym in symbols[:5]:
            clean = sym.replace("xyz:", "").split(".")[0]
            try:
                items = yf.Ticker(clean).news or []
                for item in items[:3]:
                    title = item.get("title") or item.get("headline", "")
                    if title:
                        results.append({"symbol": sym, "headline": title[:120]})
            except Exception:
                pass
    except Exception:
        pass
    return results


def get_cached_context(venue: str, universe: list[str]) -> dict:
    """캐시된 시장 컨텍스트 반환. TTL 만료 시 백그라운드 갱신 없이 즉시 재fetch."""
    now = time.time()
    with _LOCK:
        cached = _CACHE.get(venue)
        if cached and (now - cached[0]) < _TTL:
            return cached[1]

    # US/KR 심볼만 어닝/뉴스 조회 (HL 암호화폐는 yfinance 미지원)
    us_syms = [
        s for s in universe
        if ":" not in s and len(s) <= 5 and s.isalpha()
    ][:8]

    vix = None
    earnings_days: dict[str, int] = {}
    news: list[dict] = []

    try:
        vix = _fetch_vix()
    except Exception as e:
        _log.debug("[lv5_context] VIX fetch 실패: %s", e)

    if venue in ("US", "KR") and us_syms:
        for sym in us_syms:
            try:
                d = _days_to_earnings(sym)
                if d is not None:
                    earnings_days[sym] = d
            except Exception:
                pass
        try:
            news = _fetch_news_headlines(us_syms)
        except Exception:
            pass

    data = {
        "vix": round(vix, 2) if vix else None,
        "earnings_days": earnings_days,
        "news": news,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with _LOCK:
        _CACHE[venue] = (now, data)
    _log.info("[lv5_context] venue=%s vix=%s earnings=%s news=%d건",
              venue, vix, earnings_days, len(news))
    return data


def format_context_for_prompt(ctx: dict) -> str:
    """Claude 프롬프트용 컨텍스트 텍스트 생성."""
    lines = []
    vix = ctx.get("vix")
    if vix:
        regime = "고변동성" if vix > 25 else ("저변동성" if vix < 15 else "중간")
        lines.append(f"VIX: {vix:.1f} ({regime})")
    earnings = ctx.get("earnings_days", {})
    if earnings:
        near = [(s, d) for s, d in earnings.items() if d <= 5]
        if near:
            lines.append("어닝 임박 (5일 이내): " + ", ".join(f"{s}({d}일)" for s, d in sorted(near, key=lambda x: x[1])))
    news = ctx.get("news", [])
    if news:
        lines.append("최근 뉴스:")
        for n in news[:6]:
            lines.append(f"  [{n['symbol']}] {n['headline']}")
    return "\n".join(lines) if lines else "(컨텍스트 없음)"
