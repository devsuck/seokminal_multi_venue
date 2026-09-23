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
import logging
import os
from pathlib import Path

from api_server import risk_state

_log = logging.getLogger(__name__)

VENUES = ("KR", "HL", "US_IB", "US_ALPACA")
_DATA = Path(os.environ.get("DART_BOT_DIR", "data"))
_SNAPSHOT_PATH = _DATA / "venue_risk_snapshots.jsonl"
_TICK_INTERVAL_SEC = 300
_STALE_AFTER_SEC = 3 * _TICK_INTERVAL_SEC  # 15분 — 이보다 오래된 값 재사용시 로그 경고
_MAX_SNAPSHOT_BYTES = 5_000_000  # ponytail: 넘으면 오래된 절반 버림, 무제한 증가 방지


def _kr_equity_native() -> float | None:
    """원화(KRW) 그대로 반환 — FX환산은 안 함. 자기 venue 드로다운/킬 판정은 이
    값(자국통화 원금)으로 해야 환율 변동이 가짜 손익으로 잡히지 않는다. USD환산은
    tick()이 aggregate 합산 시점에만 별도로 한다."""
    from jarvis.broker_readonly.live_providers import KISReadOnlyProvider
    try:
        snap = KISReadOnlyProvider(paper=False).account_snapshot()
        if snap is None:
            return None
        eq = snap.equity
        return eq if eq > 0 else None
    except Exception as e:
        _log.warning("venue_risk: KR equity fetch failed: %s", e)
        return None


def _hl_equity_usd() -> float | None:
    from jarvis.broker_readonly.live_providers import HLReadOnlyProvider
    try:
        snap = HLReadOnlyProvider(paper=False).account_snapshot()
        eq = snap.equity if snap else None
        return eq if eq and eq > 0 else None
    except Exception as e:
        _log.warning("venue_risk: HL equity fetch failed: %s", e)
        return None


async def _us_ib_equity_usd() -> float | None:
    from backends.ib.client import IBClient
    import random
    try:
        port = int(os.environ.get("IB_PORT", "7498"))
        summary = await IBClient(port=port, client_id=random.randint(500, 599)).get_account_summary()
        eq = float(summary["net_liquidation"])
        return eq if eq > 0 else None
    except Exception as e:
        _log.warning("venue_risk: US_IB equity fetch failed: %s", e)
        return None


def _us_alpaca_equity_usd() -> float | None:
    key = os.environ.get("ALPACA_API_KEY", "")
    sec = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        return None
    try:
        from alpaca.trading.client import TradingClient
        acct = TradingClient(key, sec, paper=True).get_account()
        eq = float(acct.equity)
        return eq if eq > 0 else None
    except Exception as e:
        _log.warning("venue_risk: US_ALPACA equity fetch failed: %s", e)
        return None


_EQUITY_FETCHERS = {
    "KR": _kr_equity_native,
    "HL": _hl_equity_usd,
    "US_ALPACA": _us_alpaca_equity_usd,
}


async def _equity_usd(venue: str) -> float | None:
    """이름과 달리 KR은 KRW 원화 그대로 반환한다(자기 venue 판정용 자국통화 원금).
    나머지 venue는 원래부터 USD 네이티브라 이름 그대로."""
    if venue == "US_IB":
        return await _us_ib_equity_usd()
    return await asyncio.to_thread(_EQUITY_FETCHERS[venue])


def _to_usd_for_aggregate(venue: str, native: float) -> float:
    """firm-wide aggregate 합산 전용 USD 환산 — KR의 자기 드로다운/킬 판정에는
    안 쓴다(그건 native KRW 그대로, FX노이즈 차단)."""
    if venue != "KR":
        return native
    from jarvis.broker_readonly.aggregator import _usdkrw_rate
    return native / _usdkrw_rate()


def _append_snapshot(venue: str, equity_usd: float) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    entry = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), "venue": venue, "equity_usd": equity_usd}
    with _SNAPSHOT_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    _prune_snapshot_file()


def _prune_snapshot_file() -> None:
    if _SNAPSHOT_PATH.stat().st_size <= _MAX_SNAPSHOT_BYTES:
        return
    lines = _SNAPSHOT_PATH.read_text().splitlines()
    _SNAPSHOT_PATH.write_text("\n".join(lines[len(lines) // 2:]) + "\n")


def _rows(venue: str) -> list[dict]:
    if not _SNAPSHOT_PATH.exists():
        return []
    out = []
    for line in _SNAPSHOT_PATH.read_text().splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("venue") == venue:
            out.append(row)
    return out


def history(venue: str) -> list[float]:
    return [float(r["equity_usd"]) for r in _rows(venue)]


def drawdown_pct(venue: str, current: float) -> float:
    """현재 관측값의 peak(자기 자신 포함 역대 최고) 대비 dd%. 히스토리 없으면 0.0."""
    hist = history(venue)
    peak = max(hist + [current]) if hist else current
    if not peak:
        return 0.0
    return round((current - peak) / peak * 100, 2)


def max_dd_limit(venue: str) -> float:
    override = os.environ.get(f"MAX_DRAWDOWN_PCT_{venue}")
    if override:
        try:
            return float(override)
        except ValueError:
            _log.warning("venue_risk: MAX_DRAWDOWN_PCT_%s=%r invalid, falling back to default", venue, override)
    default = os.environ.get("MAX_DRAWDOWN_PCT", "15")
    try:
        return float(default)
    except ValueError:
        _log.warning("venue_risk: MAX_DRAWDOWN_PCT=%r invalid, falling back to 15", default)
        return 15.0


def _check_and_kill(venue: str, dd: float) -> None:
    if risk_state.venue_engaged(venue):
        return  # sticky — 이미 killed면 재호출 안 함(최초 원인 보존)
    limit = max_dd_limit(venue)
    if dd <= -limit:
        _log.warning("venue_risk: %s kill triggered dd=%s%% limit=-%s%%", venue, dd, limit)
        risk_state.set_kill(venue, True, f"MDD {dd}% <= -{limit}% 자동 차단")


async def tick() -> None:
    latest: dict[str, float] = {}
    for venue in VENUES:
        try:
            equity = await _equity_usd(venue)
        except Exception:
            equity = None
        if equity is None:
            rows = _rows(venue)
            if rows:
                last_ts = _dt.datetime.fromisoformat(rows[-1]["ts"])
                age = (_dt.datetime.now(_dt.timezone.utc) - last_ts).total_seconds()
                if age > _STALE_AFTER_SEC:
                    _log.warning(
                        "venue_risk: %s stale %.0fs (> %ds) — reusing last known value for aggregate anyway",
                        venue, age, _STALE_AFTER_SEC,
                    )
                # 조회 실패 — 마지막 알려진 값으로 aggregate엔 남김. staleness는 로그만
                # 하고 aggregate에서 빼진 않는다 — 뺐다간 벤뉴 하나 죽었을 뿐인데
                # 나머지 합산이 줄어든 걸 진짜 손실로 오인해 firm-wide kill을 유발할
                # 수 있음(실제 손실보다 더 위험한 false positive).
                latest[venue] = _to_usd_for_aggregate(venue, float(rows[-1]["equity_usd"]))
            continue
        try:
            _append_snapshot(venue, equity)
            dd = drawdown_pct(venue, equity)
            _check_and_kill(venue, dd)
            latest[venue] = _to_usd_for_aggregate(venue, equity)
        except Exception as e:
            _log.warning("venue_risk: tick failed for venue=%s: %s", venue, e)

    if latest:
        try:
            total = sum(latest.values())
            _append_snapshot("_AGGREGATE", total)
            dd = drawdown_pct("_AGGREGATE", total)
            _check_and_kill("_AGGREGATE", dd)
        except Exception as e:
            _log.warning("venue_risk: tick failed for venue=_AGGREGATE: %s", e)


async def venue_risk_loop() -> None:
    while True:
        try:
            await tick()
        except Exception:
            pass
        await asyncio.sleep(_TICK_INTERVAL_SEC)
