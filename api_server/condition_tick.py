"""Lv1 조건식 페이퍼 실행 — 백테스트에서 검증한 조건식을 그대로 매 tick 평가.

의미론은 backtest의 gated 모드(strategy_spawner)와 동일하게 맞춘다: 조건식이 한 번이라도
True가 되면 그 이후로는 EMACrossFlat과 같은 fast/slow EMA 크로스로 계속 진입/청산한다
(조건은 1회성 게이트, 실제 매매 로직은 EMA 크로스). 백테스트가 검증한 것과 같은 daily bar
catalog를 그대로 써서 "백테스트에서 본 것과 실제로 도는 것"의 정합성을 유지한다.
"""
from __future__ import annotations

import json

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from adapters.data_provider import bar_type_for
from condition_engine.evaluator import ConditionEvaluator
from condition_engine.indicator_registry import IndicatorRegistry
from condition_engine.parser import ConditionParser

CATALOG_PATH = "./catalog"


def _ema_series_position(bars: list, fast_period: int, slow_period: int) -> str:
    """전체 히스토리에 대해 fast/slow EMA 크로스를 재생해 현재 논리적 포지션 산출."""
    fast_k = 2 / (fast_period + 1)
    slow_k = 2 / (slow_period + 1)
    fast_ema = slow_ema = None
    prev_fast = prev_slow = None
    position = "FLAT"

    for b in bars:
        price = float(b.close)
        fast_ema = price if fast_ema is None else price * fast_k + fast_ema * (1 - fast_k)
        slow_ema = price if slow_ema is None else price * slow_k + slow_ema * (1 - slow_k)

        if prev_fast is not None and prev_slow is not None:
            if prev_fast <= prev_slow and fast_ema > slow_ema:
                position = "LONG"
            elif prev_fast >= prev_slow and fast_ema < slow_ema:
                position = "FLAT"
        prev_fast, prev_slow = fast_ema, slow_ema

    return position


def evaluate_agent(agent: dict) -> dict:
    """Lv1 조건식 tick 판단. 브로커 호출은 하지 않음 — 순수 의사결정만.

    agent["condition_json"]은 buildSpawnRules(rules, instrumentId)가 만드는 rule 1개를
    그대로 JSON 직렬화한 것 — 백테스트가 실제로 돌린 것과 동일한 스펙(condition + strategy
    params의 fast_ema_period/slow_ema_period)을 그대로 재사용해 정합성을 유지한다.

    Returns {"action": "BUY"|"SELL"|"HOLD"|"WATCH", "price": float|None, "note": str,
             "spawned": bool, "position_state": "FLAT"|"LONG"}.
    """
    instrument_id = agent.get("instrument_id")
    condition_json = agent.get("condition_json")

    if not (instrument_id and condition_json):
        return {
            "action": "SKIP", "price": None, "note": "조건식/종목 미설정",
            "spawned": False, "position_state": "FLAT",
        }

    rule = json.loads(condition_json)
    inst = InstrumentId.from_str(instrument_id)
    bar_type_str = str(bar_type_for(inst))

    catalog = ParquetDataCatalog(CATALOG_PATH)
    bars = sorted(catalog.bars(bar_types=[bar_type_str]), key=lambda b: b.ts_event)

    if len(bars) < 2:
        return {
            "action": "SKIP", "price": None, "note": "bar 데이터 부족",
            "spawned": bool(agent.get("spawned")),
            "position_state": agent.get("position_state", "FLAT"),
        }

    price = float(bars[-1].close)
    spawned = bool(agent.get("spawned"))
    strategy_params = rule.get("strategy", {}).get("params", {})
    fast_p = int(strategy_params.get("fast_ema_period", 10))
    slow_p = int(strategy_params.get("slow_ema_period", 20))

    if not spawned:
        evaluator = ConditionEvaluator(ConditionParser.parse(rule["condition"]), IndicatorRegistry())
        for b in bars:
            evaluator.on_bar(b)
        if not evaluator.evaluate():
            return {
                "action": "WATCH", "price": price, "note": "조건 미충족 (게이트 대기)",
                "spawned": False, "position_state": "FLAT",
            }
        spawned = True

    target = _ema_series_position(bars, fast_p, slow_p)
    prev_position = agent.get("position_state", "FLAT")

    if target == "LONG" and prev_position != "LONG":
        action = "BUY"
    elif target == "FLAT" and prev_position == "LONG":
        action = "SELL"
    else:
        action = "HOLD"

    return {
        "action": action,
        "price": price,
        "note": f"EMA({fast_p}/{slow_p}) 크로스 → {target}",
        "spawned": spawned,
        "position_state": target,
    }
