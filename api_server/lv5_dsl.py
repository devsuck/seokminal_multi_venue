"""Lv5 전략 DSL — Claude가 생성한 구조화 규칙을 tick마다 적용.

Claude는 JSON DSL을 생성. 실제 실행은 이 모듈이 담당 (코드 exec 없음, 안전).

DSL 스키마:
{
  "time_rules":       [{"hour_start": 9, "hour_end": 10, "threshold_boost": 10, "position_scale": 1.0}],
  "vix_rules":        [{"vix_above": 28, "threshold_boost": 12, "position_scale": 0.75}],
  "symbol_overrides": [{"symbol": "NVDA", "threshold": 45, "position_scale": 1.2, "skip": false}],
  "earnings_buffer_days": 2,
  "banned_symbols":   ["TSLA"]
}
"""
from __future__ import annotations

import threading

_DSL_LOCK = threading.Lock()
_DSL_CACHE: dict[str, dict] = {}

_EMPTY_DSL: dict = {
    "time_rules": [],
    "vix_rules": [],
    "symbol_overrides": [],
    "earnings_buffer_days": 1,
    "banned_symbols": [],
}


def get_cached_dsl(agent_id: str) -> dict:
    with _DSL_LOCK:
        return dict(_DSL_CACHE.get(agent_id, _EMPTY_DSL))


def set_cached_dsl(agent_id: str, dsl: dict) -> None:
    """Claude가 생성한 DSL 저장. 알려진 키만 수용 (injection 방어)."""
    merged = dict(_EMPTY_DSL)
    for key in _EMPTY_DSL:
        if key in dsl:
            merged[key] = dsl[key]
    with _DSL_LOCK:
        _DSL_CACHE[agent_id] = merged


def apply_dsl(
    dsl: dict,
    symbol: str,
    base_threshold: float,
    base_position_pct: float,
    *,
    hour: int,
    vix: float | None,
    days_to_earnings: int | None,
) -> tuple[float, float, bool, str]:
    """DSL 규칙 적용.

    Returns: (threshold, position_pct, skip, reason)
    reason: skip 이유 (empty string = no skip)
    """
    threshold = base_threshold
    position_pct = base_position_pct
    clean = symbol.replace("xyz:", "").split(".")[0]

    # 금지 종목
    if symbol in dsl.get("banned_symbols", []) or clean in dsl.get("banned_symbols", []):
        return threshold, position_pct, True, f"[DSL] {symbol} 금지 종목"

    # 어닝 버퍼
    buf = int(dsl.get("earnings_buffer_days", 1))
    if days_to_earnings is not None and 0 <= days_to_earnings <= buf:
        return threshold, position_pct, True, f"[DSL] {symbol} 어닝 {days_to_earnings}일 후 — 진입 금지"

    # 시간 규칙 (US 거래소 기준, ET 사용자가 한국 서버면 UTC+9)
    for rule in dsl.get("time_rules", []):
        h_s = int(rule.get("hour_start", 0))
        h_e = int(rule.get("hour_end", 24))
        if h_s <= hour < h_e:
            boost = float(rule.get("threshold_boost", 0))
            scale = float(rule.get("position_scale", 1.0))
            threshold = min(threshold + boost, 90.0)
            position_pct = max(min(position_pct * scale, 0.25), 0.03)

    # VIX 규칙
    if vix is not None:
        for rule in dsl.get("vix_rules", []):
            if vix >= float(rule.get("vix_above", 9999)):
                boost = float(rule.get("threshold_boost", 0))
                scale = float(rule.get("position_scale", 1.0))
                threshold = min(threshold + boost, 90.0)
                position_pct = max(min(position_pct * scale, 0.25), 0.03)

    # 종목별 오버라이드
    for override in dsl.get("symbol_overrides", []):
        sym_match = override.get("symbol", "")
        if sym_match in (symbol, clean):
            if override.get("skip"):
                return threshold, position_pct, True, f"[DSL] {symbol} 오버라이드 skip"
            if "threshold" in override:
                threshold = float(override["threshold"])
            if "position_scale" in override:
                position_pct = max(min(position_pct * float(override["position_scale"]), 0.25), 0.03)

    return round(threshold, 1), round(position_pct, 4), False, ""
