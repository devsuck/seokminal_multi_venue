"""fusion 합성신호 → armed+GO 필터 → broker_bridge 실주문. ensemble.py 대체
(신호결합 로직은 재구현하지 않고 이미 검증된 jarvis/fusion/을 그대로 소비).

불변식: armed+GO 기여자가 최소 1개, 같은 방향으로 있어야만 트레이드 성립
(Tier B — draft 상태 후보 — 단독 트리거 절대 불가. 애초에 fusion PROVIDER_REGISTRY에
adapter가 등록된 전략만 신호를 내므로 draft 후보는 신호 자체가 안 생김).
포지션사이징은 armed 전략의 capital_limit(사람이 arm() 때 지정)만 사용 —
jarvis/portfolio/(역변동성+상관페널티 배분)는 미편입. armed 전략 2개+가 동시에
운용되기 시작하면 그때 편입 검토.
# ponytail: 단일-capital_limit 사이징. 배분 최적화는 armed 전략 2개+ 되면 추가.
"""
from __future__ import annotations

from jarvis.execution import broker_bridge
from jarvis.execution.arm import arm_state, is_armed
from jarvis.execution.edge_providers import EDGE_PROVIDER_VENUE, edge_go
from jarvis.fusion.fusion import FusionEngine
from jarvis.fusion.performance import perf_for
from jarvis.fusion.providers import collect_signals

BOOST_MULTIPLIER = 1.3


def _kr_last_close(code: str) -> float | None:
    """최근 종가(quotation 엔드포인트는 mock/실전 구분 없이 실전 앱키 사용 —
    place_test_order.py와 동일 패턴). 크레덴셜 없거나 데이터 없으면 None."""
    import datetime as _dt
    import os
    from backends.kis.client import KISClient

    app_key = os.environ.get("KIS_APP_KEY", "")
    app_secret = os.environ.get("KIS_APP_SECRET", "")
    if not app_key or not app_secret:
        return None
    client = KISClient(app_key=app_key, app_secret=app_secret)
    today = _dt.date.today()
    start = (today - _dt.timedelta(days=10)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    rows = client.get_daily_price(code, start, end)
    if not rows:
        return None
    return float(rows[-1]["stck_clpr"])


def _build_order(fs, capital: float, backer_strategy_id: str) -> dict | None:
    """가격 못 구하거나 1주도 못 사면 None(호출부가 blocked 처리).
    paper=False 명시 — broker_bridge.route_order 기본값이 True라, 생략하면
    게이트가 다 열려도 계속 페이퍼로만 나감(실거래 라우터의 핵심 전제)."""
    venue = EDGE_PROVIDER_VENUE.get(backer_strategy_id)
    side = "BUY" if fs.direction == 1 else "SELL"
    if venue != "KR":
        return None  # HL 등 다른 venue의 edge provider 생기면 그때 분기 추가
    price = _kr_last_close(fs.instrument)
    if price is None or price <= 0:
        return None
    quantity = int(capital // price)
    if quantity < 1:
        return None
    return {"venue": "KR", "symbol": fs.instrument, "side": side, "quantity": quantity,
            "order_type": "MARKET", "price": price, "paper": False,
            "strategy_id": backer_strategy_id}


def route_all(as_of: str = "") -> dict:
    """fusion 합성신호 전체를 armed+GO 필터 후 라우팅. 반환: {as_of, routed, blocked, skipped}."""
    signals, skipped = collect_signals(as_of)
    if not signals:
        return {"as_of": as_of, "routed": [], "blocked": [], "skipped": skipped,
                "note": "fusion-eligible 신호 없음"}
    perfs = {s.strategy_id: perf_for(s.strategy_id) for s in signals}
    fused = FusionEngine().fuse(signals, perfs, as_of)

    routed: list[dict] = []
    blocked: list[dict] = []
    for fs in fused:
        if fs.direction == 0:
            continue
        armed_backers = [c for c in fs.contributions
                          if c.direction == fs.direction
                          and is_armed(c.strategy_id)
                          and edge_go(c.strategy_id)]
        if not armed_backers:
            blocked.append({"instrument": fs.instrument, "reason": "no_armed_go_backer",
                             "n_strategies": fs.n_strategies})
            continue
        lead = armed_backers[0]
        base_capital = min(arm_state(b.strategy_id)["capital_limit"] for b in armed_backers)
        size_mult = (BOOST_MULTIPLIER if fs.n_strategies >= 2 else 1.0) * fs.confidence
        order = _build_order(fs, base_capital * size_mult, lead.strategy_id)
        if order is None:
            blocked.append({"instrument": fs.instrument, "reason": "unpriceable_or_too_small"})
            continue
        try:
            result = broker_bridge.route_order(order)
            routed.append({"instrument": fs.instrument, "result": result})
        except broker_bridge.BrokerOrderRejected as exc:
            blocked.append({"instrument": fs.instrument, "reason": str(exc)})
    return {"as_of": as_of, "routed": routed, "blocked": blocked, "skipped": skipped}
