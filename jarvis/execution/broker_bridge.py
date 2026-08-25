"""Gateway의 SIMULATED 종점 다음 단계 — 진짜 브로커 호출.

ExecutionGateway.execute()는 4중 게이트(레벨·무장·리스크·registry) 통과해도
"SIMULATED — mock/paper dry-run" 고정 반환(실브로커 호출 코드 없음, 의도된 설계).
route_order()는 그 이후 단계: mode가 진짜 live/micro_live이고 게이트를 실제로
통과했을 때만 호출되는 실주문 경로. KR은 api_server의 /orders/kr과 동일 패턴
(risk_guard → place_order → 감사/멱등성/oms 기록), HL도 동일.

이 모듈 자체는 어떤 게이트도 재구현하지 않는다 — 호출부(러너)가 Gateway 통과를
이미 확인했다고 신뢰한다. 이중 안전장치로 risk_guard는 여기서도 다시 돈다
(제안 단계 RiskGovernor 한도와, 통화단위 인지 risk_guard 한도가 다른 축이라
둘 다 통과해야 함).
"""
from __future__ import annotations

import os

from backends.kis.order_client import KISOrderClient
from jarvis.audit import record
from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
from live_engine.risk_guard import DailyLossLimitBreached, RiskConfig, RiskViolation, validate_order


class BrokerOrderRejected(Exception):
    """risk_guard 또는 브로커 크레덴셜 부재로 route_order가 거부됨."""


# ponytail: in-memory per 프로세스. api_server/main.py의 daily_pnl_tracker와는
# 별개 인스턴스 — 이 브릿지가 API 서버와 같은 프로세스에서 안 돈다면 일별 손실
# 합산이 어긋난다. 오늘은 무해(어떤 전략도 arm_criteria GO를 못 받아 이 경로 자체가
# 호출 안 됨). 실제 스케줄러를 API 서버 in-process로 붙이든지, durable 소스로
# realized() 계산을 옮기든지는 스케줄러 설계 시점에 결정.
_daily_pnl = None


def _tracker():
    global _daily_pnl
    if _daily_pnl is None:
        from live_engine.risk_guard import DailyPnLTracker
        _daily_pnl = DailyPnLTracker()
    return _daily_pnl


def route_order(order: dict) -> dict:
    """order: {venue: KR|HL, symbol, side, quantity, order_type, price, paper,
    client_order_id}. 반환: place_order 결과 dict. 실패 시 BrokerOrderRejected."""
    if not live_execution_enabled():
        reason = f"AUTONOMY_LEVEL={AUTONOMY_LEVEL} < MIN_LIVE_LEVEL={MIN_LIVE_LEVEL}"
        record({"layer": "broker_bridge", "action": "route_order", "venue": order.get("venue"),
                "symbol": order.get("symbol"), "result": "autonomy_blocked", "reason": reason})
        raise BrokerOrderRejected(f"live execution disabled ({reason})")
    venue = order["venue"]
    side = order["side"]
    quantity = float(order["quantity"])
    price = order.get("price")
    paper = bool(order.get("paper", True))

    cfg = RiskConfig.from_env(venue=venue)
    try:
        validate_order(
            side=side, quantity=quantity, price_estimate=price,
            current_position_qty=0, day_realized_pnl=_tracker().realized(),
            config=cfg,
        )
    except (RiskViolation, DailyLossLimitBreached) as exc:
        record({"layer": "broker_bridge", "action": "route_order", "venue": venue,
                "symbol": order.get("symbol"), "result": "risk_rejected", "reason": str(exc)})
        raise BrokerOrderRejected(str(exc)) from exc

    if venue == "KR":
        result = _place_kr(order, paper)
    elif venue == "HL":
        result = _place_hl(order, paper)
    else:
        raise BrokerOrderRejected(f"unknown venue: {venue}")

    try:
        record({"layer": "broker_bridge", "action": "route_order", "venue": venue,
                "symbol": order.get("symbol"), "side": side, "quantity": quantity,
                "paper": paper, "result": "submitted"})
        _notify(order, paper)
    except Exception:  # noqa: BLE001 — 브로커 제출은 이미 성공, 감사기록/알림 실패로
        pass            # route_order()가 예외를 던지면 호출부가 이미 나간 주문을 blocked로 오기록함
    return result


def _place_kr(order: dict, paper: bool) -> dict:
    if paper:
        app_key = os.environ.get("KIS_MOCK_APP_KEY", "")
        app_secret = os.environ.get("KIS_MOCK_APP_SECRET", "")
        cano = os.environ.get("KIS_MOCK_CANO", "")
    else:
        app_key = os.environ.get("KIS_APP_KEY", "")
        app_secret = os.environ.get("KIS_APP_SECRET", "")
        cano = os.environ.get("KIS_CANO", "")
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "")
    if not all([app_key, app_secret, cano, acnt_prdt_cd]):
        raise BrokerOrderRejected(f"KIS {'모의' if paper else '실전'} credentials not configured")
    client = KISOrderClient(app_key, app_secret, cano, acnt_prdt_cd, mock=paper)
    return client.place_order(
        order["symbol"], order["side"], order["quantity"],
        order.get("order_type", "MARKET"), order.get("price"),
    )


def _place_hl(order: dict, paper: bool) -> dict:
    from hyperliquid.trader import place_order
    return place_order(
        coin=order["symbol"], is_buy=(order["side"].upper() == "BUY"),
        size=order["quantity"], order_type=order.get("order_type", "market"),
        limit_px=order.get("price"), reduce_only=order.get("reduce_only", False),
        slippage=order.get("slippage", 0.05), paper=paper,
    )


def _notify(order: dict, paper: bool) -> None:
    from api_server.lv6_notify import notify_live_trade
    price = order.get("price") or 0.0
    notify_live_trade(
        agent_id=order.get("strategy_id", "ensemble"), venue=order["venue"],
        symbol=order["symbol"], side=order["side"].lower(),
        size=float(order["quantity"]), price=float(price), paper=paper,
    )
