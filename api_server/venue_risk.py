"""Venue별 독립 MDD 드로다운 감시 + 킬스위치 트리거.

KR/HL/US_IB/US_ALPACA 4개 venue의 NAV를 자체 스냅샷(jsonl)으로 추적해 각자
peak 대비 드로다운을 계산하고, 임계 초과시 자기 venue만 킬한다. 4개 합산 NAV로
firm-wide aggregate도 별도로 킬 판정(_AGGREGATE 키). risk_state.py는 킬 상태
저장/조회만 하고, 평가(드로다운 계산 → 자동킬 트리거)는 여기가 전담한다.

한 venue의 조회 실패가 다른 venue나 aggregate 계산을 막지 않는다 — venue별로
격리된 try/except. venue_risk_loop()가 300초 주기로 tick()을 돌린다(main.py
startup에서 다른 백그라운드 루프들과 같은 패턴으로 등록).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
from pathlib import Path

from api_server import risk_state

VENUES = ("KR", "HL", "US_IB", "US_ALPACA")
_DATA = Path(os.environ.get("DART_BOT_DIR", "data"))
_SNAPSHOT_PATH = _DATA / "venue_risk_snapshots.jsonl"
_TICK_INTERVAL_SEC = 300


def _kr_equity_usd() -> float | None:
    from jarvis.broker_readonly.aggregator import _usdkrw_rate
    from jarvis.broker_readonly.live_providers import KISReadOnlyProvider
    try:
        snap = KISReadOnlyProvider(paper=True).account_snapshot()
        if snap is None:
            return None
        return snap.equity / _usdkrw_rate()
    except Exception:
        return None


def _hl_equity_usd() -> float | None:
    from jarvis.broker_readonly.live_providers import HLReadOnlyProvider
    try:
        snap = HLReadOnlyProvider(paper=False).account_snapshot()
        return snap.equity if snap else None
    except Exception:
        return None


async def _us_ib_equity_usd() -> float | None:
    from backends.ib.client import IBClient
    try:
        summary = await IBClient().get_account_summary()
        return float(summary["net_liquidation"])
    except Exception:
        return None


def _us_alpaca_equity_usd() -> float | None:
    key = os.environ.get("ALPACA_API_KEY", "")
    sec = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        return None
    try:
        from alpaca.trading.client import TradingClient
        acct = TradingClient(key, sec, paper=True).get_account()
        return float(acct.equity)
    except Exception:
        return None


_EQUITY_FETCHERS = {
    "KR": _kr_equity_usd,
    "HL": _hl_equity_usd,
    "US_ALPACA": _us_alpaca_equity_usd,
}


async def _equity_usd(venue: str) -> float | None:
    if venue == "US_IB":
        return await _us_ib_equity_usd()
    return await asyncio.to_thread(_EQUITY_FETCHERS[venue])


def _append_snapshot(venue: str, equity_usd: float) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    entry = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), "venue": venue, "equity_usd": equity_usd}
    with _SNAPSHOT_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def history(venue: str) -> list[float]:
    if not _SNAPSHOT_PATH.exists():
        return []
    out = []
    for line in _SNAPSHOT_PATH.read_text().splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("venue") == venue:
            out.append(float(row["equity_usd"]))
    return out


def drawdown_pct(venue: str, current: float) -> float:
    """히스토리 + 현재값 기준 peak 대비 dd%. 히스토리 없으면(첫 관측) 0.0."""
    hist = history(venue) + [current]
    peak = hist[0]
    dd = 0.0
    for e in hist:
        peak = max(peak, e)
        if peak:
            dd = min(dd, (e - peak) / peak * 100)
    return round(dd, 2)


def max_dd_limit(venue: str) -> float:
    override = os.environ.get(f"MAX_DRAWDOWN_PCT_{venue}")
    if override:
        return float(override)
    return float(os.environ.get("MAX_DRAWDOWN_PCT", "15"))


def _check_and_kill(venue: str, dd: float) -> None:
    if risk_state.venue_engaged(venue):
        return  # sticky — 이미 killed면 재호출 안 함(최초 원인 보존)
    limit = max_dd_limit(venue)
    if dd <= -limit:
        risk_state.set_kill(venue, True, f"MDD {dd}% <= -{limit}% 자동 차단")


async def tick() -> None:
    latest: dict[str, float] = {}
    for venue in VENUES:
        try:
            equity = await _equity_usd(venue)
        except Exception:
            equity = None
        if equity is None:
            hist = history(venue)
            if hist:
                latest[venue] = hist[-1]  # 조회 실패 — 마지막 알려진 값으로 aggregate엔 남김
            continue
        try:
            _append_snapshot(venue, equity)
            latest[venue] = equity
            dd = drawdown_pct(venue, equity)
            _check_and_kill(venue, dd)
        except Exception:
            pass

    if latest:
        try:
            total = sum(latest.values())
            _append_snapshot("_AGGREGATE", total)
            dd = drawdown_pct("_AGGREGATE", total)
            _check_and_kill("_AGGREGATE", dd)
        except Exception:
            pass


async def venue_risk_loop() -> None:
    while True:
        try:
            await tick()
        except Exception:
            pass
        await asyncio.sleep(_TICK_INTERVAL_SEC)
