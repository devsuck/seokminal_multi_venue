"""서버측 DART 기업행위 자동매매 봇.

브라우저 탭과 무관하게 uvicorn 프로세스 안에서 주기적으로 돈다. 자사주 취득·
소각(호재) 신규 공시를 KIS 모의로 매수. 상태·로그는 파일에 남겨 프론트가 조회.
개인 내부자 매매는 5영업일 지연이라 대상 아님(기업행위만).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/dart/auto", tags=["dart-autobot"])

_DATA = Path(os.environ.get("DART_BOT_DIR", "data"))
_CFG = _DATA / "dart_autobot.json"
_LOG = _DATA / "dart_autobot_log.jsonl"
_BUY_TYPES = {"BUYBACK", "CANCELLATION"}

_DEFAULT = {
    "enabled": False, "budget": 1000000.0, "spent": 0.0, "interval_sec": 300,
    "acted": [], "last_run": None,
    # 매도 규칙 — 익절/손절/최대보유. 매도되면 spent에서 원금이 빠져 예산 재활용됨.
    "tp_pct": 0.15, "sl_pct": 0.07, "max_hold_days": 20,
    "positions": [],  # [{code, corp, qty, entry_price, entry_ts}]
}


def _load() -> dict:
    try:
        cfg = {**_DEFAULT, **json.loads(_CFG.read_text())}
    except Exception:
        return dict(_DEFAULT)
    # 1회 마이그레이션: 매도 로직 도입 전의 매수 이력을 포지션으로 복원.
    # (이전엔 매도가 아예 없었으므로 로그의 모든 buy = 현재 보유가 정확함)
    if "positions" not in json.loads(_CFG.read_text() or "{}"):
        positions = []
        for ev in _recent_log(500)[::-1]:
            if ev.get("kind") == "buy" and ev.get("code") and ev.get("qty"):
                positions.append({
                    "code": ev["code"], "corp": ev.get("corp", ""),
                    "qty": int(ev["qty"]), "entry_price": float(ev.get("price") or 0),
                    "entry_ts": ev.get("ts", ""),
                })
        cfg["positions"] = positions
        _save(cfg)
    return cfg


def _save(cfg: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _CFG.write_text(json.dumps(cfg))


def _log_event(ev: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    ev["ts"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    with _LOG.open("a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _recent_log(n: int = 40) -> list[dict]:
    try:
        lines = _LOG.read_text().strip().splitlines()
        return [json.loads(x) for x in lines[-n:]][::-1]
    except Exception:
        return []


def _kr_market_open(now: _dt.datetime | None = None) -> bool:
    # 09:00–15:30 KST, 평일. KST = UTC+9.
    now = now or _dt.datetime.now(_dt.timezone.utc)
    kst = now + _dt.timedelta(hours=9)
    if kst.weekday() >= 5:
        return False
    mins = kst.hour * 60 + kst.minute
    return 9 * 60 <= mins <= 15 * 60 + 30


def _current_price(code: str) -> float | None:
    """현재가 (KOSPI .KS → KOSDAQ .KQ 폴백). 둘 다 빈 응답이면 None."""
    import yfinance as yf
    for suffix in (".KS", ".KQ"):
        try:
            hist = yf.Ticker(f"{code}{suffix}").history(period="1d")
            if len(hist) and "Close" in hist:
                return float(hist["Close"].iloc[-1])
        except Exception:
            continue
    return None


def _kis():
    from backends.kis.order_client import KISOrderClient
    kk, ks, kc = (os.environ.get("KIS_MOCK_APP_KEY", ""), os.environ.get("KIS_MOCK_APP_SECRET", ""), os.environ.get("KIS_MOCK_CANO", ""))
    return KISOrderClient(kk, ks, kc, os.environ.get("KIS_ACNT_PRDT_CD", "01"), mock=True)


def _kst_today_str() -> str:
    return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=9)).strftime("%Y%m%d")


def _round_down_tick(price: float) -> int:
    """KRX 호가단위로 내림. 지정가 주문은 유효 tick 아니면 거부됨."""
    if price < 2000:
        t = 1
    elif price < 5000:
        t = 5
    elif price < 20000:
        t = 10
    elif price < 50000:
        t = 50
    elif price < 200000:
        t = 100
    elif price < 500000:
        t = 500
    else:
        t = 1000
    return int(price // t * t)


def _buy(code: str, krw: float) -> dict:
    """KIS 모의 시장가 매수 (원화예산÷현재가). tick 전용 헬퍼."""
    px = _current_price(code)
    if px is None or px <= 0:
        raise ValueError("현재가 조회 실패 (상장폐지/신규상장/코스닥 심볼)")
    qty = int(krw // px)
    if qty < 1:
        raise ValueError(f"예산 부족 (현재가 ₩{px:,.0f})")
    from jarvis.execution.broker_bridge import route_order
    r = route_order({"venue": "KR", "symbol": code, "side": "BUY", "quantity": qty,
                      "order_type": "MARKET", "price": px, "paper": True})
    return {"code": code, "qty": qty, "price": round(px, 0), "order_id": r.get("order_id")}


def _place_sl_order(code: str, qty: int, entry_price: float, sl_pct: float) -> dict | None:
    """손절가에 지정가 매도 주문을 걸어둔다(당일유효 — KRX는 GTC 미지원, 매일 재상신 필요).
    실패해도 None 반환 — 호출자는 시세 폴링 방식으로 폴백한다."""
    limit_px = _round_down_tick(round(entry_price * (1 - abs(sl_pct)), 4))  # 부동소수 오차(929.999…) 방지
    try:
        from jarvis.execution.broker_bridge import route_order
        r = route_order({"venue": "KR", "symbol": code, "side": "SELL", "quantity": qty,
                          "order_type": "LIMIT", "price": limit_px, "paper": True})
        return {"order_id": r.get("order_id"), "limit_px": limit_px}
    except Exception:
        return None


def _cancel_sl_order(pos: dict, qty: int) -> None:
    """TP/최대보유일로 다른 사유 매도 전에 걸려있던 손절 지정가 주문부터 취소(중복매도 방지).
    이미 체결/만료됐으면 취소 실패해도 무시 — 시장가 매도가 최종 판정."""
    order_id = pos.get("sl_order_id")
    if not order_id:
        return
    try:
        _kis().cancel_order(order_id, pos.get("code", ""), qty)
    except Exception:
        pass


def _query_fill_price(pos: dict) -> float | None:
    """당일 손절 지정가 주문의 실제 체결 평균가 조회. inquire-daily-ccld는 모의계좌에서
    빈 output1을 반환하는 경우가 확인돼 있음(order_client.py _row_to_status_dict 주석) —
    조회 실패/미체결/빈 응답은 전부 None, 호출자는 지정가 근사치로 폴백한다."""
    order_id, order_date = pos.get("sl_order_id"), pos.get("sl_order_date")
    if not order_id or not order_date:
        return None
    try:
        status = _kis().get_order_status(order_date, order_id)
    except Exception:
        return None
    if status and status.get("status") == "FILLED" and status.get("avg_price"):
        return float(status["avg_price"])
    return None


def _process_exits(cfg: dict) -> int:
    """보유 포지션 매도 판정 — 지정가 손절 주문(당일 재상신) + TP/최대보유일 폴링.

    Returns: 매도 건수. cfg를 제자리 수정(저장은 호출자 책임).
    """
    tp = float(cfg.get("tp_pct", 0.15))
    sl = float(cfg.get("sl_pct", 0.07))
    max_days = int(cfg.get("max_hold_days", 20))
    now = _dt.datetime.now(_dt.timezone.utc)
    today = _kst_today_str()
    keep: list[dict] = []
    sold = 0
    for pos in cfg.get("positions", []):
        code, qty, entry = pos.get("code", ""), int(pos.get("qty", 0)), float(pos.get("entry_price") or 0)
        if not code or qty < 1 or entry <= 0:
            continue  # 불량 레코드는 버림

        # 지정가 손절 주문 — 당일 상신분 없으면(신규 포지션 or 전일 만료) 새로 건다.
        if pos.get("sl_order_date") != today:
            sl_order = _place_sl_order(code, qty, entry, sl)
            pos["sl_order_date"] = today
            pos["sl_order_id"] = sl_order.get("order_id") if sl_order else None
            pos["sl_limit_px"] = sl_order.get("limit_px") if sl_order else None  # 둘 다 None이면 폴링 폴백만 동작

        px = _current_price(code)
        if px is None or px <= 0:
            keep.append(pos)  # 시세 조회 실패 — 다음 tick에 재시도
            continue
        pnl = (px - entry) / entry
        held_days = None
        try:
            entry_ts = _dt.datetime.fromisoformat(pos.get("entry_ts", ""))
            held_days = (now - entry_ts).days
        except Exception:
            pass

        reason = None
        exit_px = px
        if pnl >= tp:
            reason = f"익절 +{pnl*100:.1f}%"
        elif pnl <= -abs(sl):
            # 지정가 손절 주문이 이미 체결됐을 가능성이 높음(장중 갭 아니어도 시세폴링보다
            # 먼저 발동) — 실제 체결가 조회 시도, 실패하면 지정가로 근사.
            reason = f"손절 {pnl*100:.1f}%"
            fill_px = _query_fill_price(pos)
            if fill_px:
                exit_px = fill_px
            elif pos.get("sl_limit_px"):
                exit_px = pos["sl_limit_px"]
        elif held_days is not None and held_days >= max_days:
            reason = f"보유 {held_days}일 만기 ({pnl*100:+.1f}%)"
        if reason is None:
            keep.append(pos)
            continue

        # 시장가로 매도하기 전에 걸려있던 손절 지정가 주문부터 취소 — 안 하면 같은 수량을
        # 두 번 매도 시도하게 됨(지정가 체결 후 시장가 재시도, 혹은 그 반대).
        _cancel_sl_order(pos, qty)

        try:
            from jarvis.execution.broker_bridge import route_order
            route_order({"venue": "KR", "symbol": code, "side": "SELL", "quantity": qty,
                         "order_type": "MARKET", "price": exit_px, "paper": True})
            cost = qty * entry
            cfg["spent"] = round(max(float(cfg.get("spent", 0.0)) - cost, 0.0), 2)
            _log_event({"kind": "sell", "corp": pos.get("corp", ""), "code": code,
                        "qty": qty, "entry_price": entry, "exit_price": round(exit_px, 0),
                        "pnl_pct": round(((exit_px - entry) / entry) * 100, 2), "reason": reason,
                        "spent": cfg["spent"]})
            sold += 1
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "잔고내역이 없습니다" in msg:
                # 브로커에 실보유가 없음 = 로컬 state가 stale — 지정가 손절 주문이 이 tick
                # 전에 이미 체결돼 실물 보유가 사라진 경우(가장 흔함)가 있어 체결가 조회를
                # 시도한다. 조회 성공하면 정확한 손익으로 sell 로그 남김, 실패하면
                # migration 복원 오류 등 원인불명으로 보고 예전처럼 조용히 드롭(중복 재시도
                # 방지 — spent는 과거 정산됐다고 간주, 다시 차감 안 함).
                fill_px = _query_fill_price(pos)
                if fill_px:
                    cfg["spent"] = round(max(float(cfg.get("spent", 0.0)) - qty * entry, 0.0), 2)
                    fill_pnl = (fill_px - entry) / entry
                    _log_event({"kind": "sell", "corp": pos.get("corp", ""), "code": code,
                                "qty": qty, "entry_price": entry, "exit_price": round(fill_px, 0),
                                "pnl_pct": round(fill_pnl * 100, 2),
                                "reason": f"손절 {fill_pnl*100:.1f}% (지정가 선체결, 체결가 조회)",
                                "spent": cfg["spent"]})
                    sold += 1
                else:
                    _log_event({"kind": "desync", "corp": pos.get("corp", ""), "code": code,
                                "msg": "브로커 잔고 없음 — 손절 지정가 주문 선체결 추정(체결가 조회 실패), 로컬 포지션 정리(재시도 중단)"})
                continue
            _log_event({"kind": "fail", "corp": pos.get("corp", ""), "code": code,
                        "msg": f"매도 실패: {msg[:80]}"})
            keep.append(pos)  # 실패 시 보유 유지, 다음 tick 재시도
    cfg["positions"] = keep
    return sold


def _reconcile_positions(cfg: dict) -> None:
    """로컬 포지션 장부 vs 실제 KIS 보유 대조 — 모의계좌가 외부 리셋되는 등으로
    브로커 보유가 사라졌는데 로컬 spent/positions만 남아있으면 예산이 영구히
    묶여 신규 매수가 막힌다. 브로커에 없는 코드는 원금을 spent에서 돌려주고 드롭.
    """
    positions = cfg.get("positions", [])
    if not positions:
        return
    try:
        held_codes = {h.get("code") for h in _kis().get_holdings()}
    except Exception:
        return  # 조회 실패 — 다음 tick에 재시도, 잘못 드롭하지 않음
    keep, dropped = [], []
    for pos in positions:
        if pos.get("code") in held_codes:
            keep.append(pos)
        else:
            dropped.append(pos)
    if not dropped:
        return
    for pos in dropped:
        cost = int(pos.get("qty", 0)) * float(pos.get("entry_price") or 0)
        cfg["spent"] = round(max(float(cfg.get("spent", 0.0)) - cost, 0.0), 2)
        _log_event({"kind": "desync", "corp": pos.get("corp", ""), "code": pos.get("code"),
                    "msg": "브로커 보유 없음(계좌 리셋 등) — 로컬 포지션 드롭, 예산 회수",
                    "spent": cfg["spent"]})
    cfg["positions"] = keep


def tick() -> dict:
    """1회 실행: 신규 자사주 취득/소각 공시를 모의 매수. 장 마감 시 스킵."""
    cfg = _load()
    if not cfg["enabled"]:
        return {"skipped": "disabled"}
    # 킬스위치(수동 or MDD 자동차단) — 모든 자동 매수 중단
    try:
        from api_server.risk_state import is_killed
        if is_killed():
            _log_event({"kind": "kill", "msg": "리스크 킬스위치 — 매수 중단"})
            return {"skipped": "kill_switch"}
    except Exception:
        pass
    _reconcile_positions(cfg)
    _save(cfg)
    if not _kr_market_open():
        cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        _save(cfg)
        return {"skipped": "market_closed"}

    # 매도 먼저 — 예산이 풀려야 신규 매수 여력이 생김
    sold = _process_exits(cfg)
    _save(cfg)

    from insider.dart_client import get_recent_kr_corporate_actions, action_weight
    try:
        rows = get_recent_kr_corporate_actions(days=7, max_items=40)
    except Exception as e:  # noqa: BLE001
        _log_event({"kind": "error", "msg": f"DART 조회 실패: {str(e)[:80]}"})
        return {"error": str(e)[:80]}

    acted = set(cfg.get("acted", []))
    bought = 0
    budget = float(cfg["budget"])
    spent = float(cfg.get("spent", 0.0))
    for r in rows:
        if r.get("trade_type") not in _BUY_TYPES:
            continue
        code = (r.get("ticker") or "").strip()
        if not code:
            continue
        key = f"{r.get('corp_name')}:{r.get('trade_type')}:{r.get('trade_date')}"
        if key in acted:
            continue
        remaining = max(budget - spent, 0.0)
        if remaining < 1.0:
            # 예산 소진 — 남은 공시는 acted 처리하지 않고 다음 tick에서 재평가
            # (budget 증액/spent 리셋 시 놓치지 않게).
            continue
        try:
            w = action_weight(r.get("trade_type", ""), r.get("report_type", ""))
            # weight로 예산을 늘리지 않고 남은 예산 안에서만 가중 배분.
            krw = min(remaining, budget * w)
            res = _buy(code, krw)
            spent += res["qty"] * res["price"]
            cfg["spent"] = round(spent, 2)
            acted.add(key)
            cfg.setdefault("positions", []).append({
                "code": code, "corp": r.get("corp_name", ""),
                "qty": res["qty"], "entry_price": res["price"],
                "entry_ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            })
            _log_event({"kind": "buy", "corp": r.get("corp_name"), "code": code,
                        "action": r.get("trade_type"), "weight": w, "spent": cfg["spent"], **res})
            bought += 1
        except Exception as e:  # noqa: BLE001
            acted.add(key)  # 재시도 폭주 방지
            msg = str(e)
            # 매매불가 종목/모의 미지원 = 정상 조건 → skip (실패 아님)
            kind = "skip" if ("매매불가" in msg or "매매 불가" in msg or "처리가 안" in msg) else "fail"
            _log_event({"kind": kind, "corp": r.get("corp_name"), "code": code, "msg": msg[:80]})
        if bought >= 5:
            break

    cfg["acted"] = list(acted)[-500:]
    cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _save(cfg)
    return {"bought": bought, "sold": sold, "scanned": len(rows),
            "positions": len(cfg.get("positions", [])), "spent": cfg["spent"], "budget": budget}


async def _loop() -> None:
    # uvicorn --reload 로 여러 번 뜰 수 있으니 예외는 삼키고 계속.
    while True:
        try:
            cfg = _load()
            interval = int(cfg.get("interval_sec", 300))
            if cfg.get("enabled"):
                await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001
            interval = 300
        await asyncio.sleep(max(interval, 60))


def start_loop() -> None:
    try:
        asyncio.get_event_loop().create_task(_loop())
    except RuntimeError:
        pass


# ── API ──────────────────────────────────────────────────────────────────────
class BotConfig(BaseModel):
    enabled: bool | None = None
    budget: float | None = None
    interval_sec: int | None = None
    reset_spent: bool | None = None
    tp_pct: float | None = None
    sl_pct: float | None = None
    max_hold_days: int | None = None


@router.get("/status")
def status() -> dict:
    cfg = _load()
    return {
        "enabled": cfg["enabled"], "budget": cfg["budget"],
        "spent": cfg.get("spent", 0.0), "remaining": max(cfg["budget"] - cfg.get("spent", 0.0), 0.0),
        "interval_sec": cfg["interval_sec"],
        "tp_pct": cfg.get("tp_pct", 0.15), "sl_pct": cfg.get("sl_pct", 0.07),
        "max_hold_days": cfg.get("max_hold_days", 20),
        "positions": cfg.get("positions", []),
        "last_run": cfg.get("last_run"), "market_open": _kr_market_open(),
        "acted_count": len(cfg.get("acted", [])), "log": _recent_log(40),
    }


@router.post("/config")
def set_config(body: BotConfig) -> dict:
    cfg = _load()
    if body.enabled is not None:
        cfg["enabled"] = body.enabled
    if body.budget is not None:
        cfg["budget"] = max(float(body.budget), 0.0)
    if body.interval_sec is not None:
        cfg["interval_sec"] = max(int(body.interval_sec), 60)
    if body.reset_spent:
        cfg["spent"] = 0.0
    if body.tp_pct is not None:
        cfg["tp_pct"] = min(max(float(body.tp_pct), 0.01), 1.0)
    if body.sl_pct is not None:
        cfg["sl_pct"] = min(max(float(body.sl_pct), 0.01), 0.5)
    if body.max_hold_days is not None:
        cfg["max_hold_days"] = max(int(body.max_hold_days), 1)
    _save(cfg)
    _log_event({"kind": "config", "enabled": cfg["enabled"], "budget": cfg["budget"], "spent": cfg.get("spent", 0.0)})
    return {"ok": True, **{k: cfg[k] for k in ("enabled", "budget", "spent", "interval_sec", "tp_pct", "sl_pct", "max_hold_days")}}


@router.post("/run-now")
def run_now() -> dict:
    """수동 1회 실행 (테스트용)."""
    return tick()
