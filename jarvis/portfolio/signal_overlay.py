"""Signal Overlay (P2.5) — 전략비중 × 종목신호 → 종목별 참고 포지션.

decision_engine/orchestrator 무수정. 기존 전략별 target_weight(이미 계산된 제안)를
그 전략 자신의 어댑터 신호(jarvis.fusion.adapters, 재구현 없음)로 종목 단위로 쪼개고,
이미 기록된 합성신호 원장(fusion ledger, 라이브 재계산 없음)과 대조해 상충 플래그만 얹는다.

**제안 전용. 주문/사이징 변경 없음 — 참고용 부가 필드.** 전략 자신의 신호가 없으면
빈 결과(정직) — 임의 균등분배로 대체하지 않는다.
"""
from __future__ import annotations

from collections import defaultdict


def _intra_strategy_split(strategy_id: str, as_of: str) -> dict[str, dict]:
    """전략 자신의 신호(어댑터, 무수정)로 종목별 비중 쪼개기. 신호 없으면 {}."""
    from jarvis.fusion.providers import PROVIDER_REGISTRY, _ensure_adapters
    _ensure_adapters()
    factory = PROVIDER_REGISTRY.get(strategy_id)
    if factory is None:
        return {}
    signals = factory(as_of) or []
    net: dict[str, float] = defaultdict(float)
    for s in signals:
        net[s.instrument] += s.direction * s.strength
    total = sum(abs(v) for v in net.values())
    if total <= 1e-9:
        return {}
    out = {}
    for instrument, v in net.items():
        direction = 1 if v > 0 else (-1 if v < 0 else 0)
        if direction == 0:
            continue
        out[instrument] = {"weight": round(abs(v) / total, 6), "direction": direction}
    return out


def _latest_fusion_by_instrument(limit: int = 200) -> dict[str, dict]:
    """fusion 원장(이미 기록된 결과만, 라이브 재계산 없음) → 계기별 최신 1건."""
    from jarvis.fusion.ledger import read_latest
    out: dict[str, dict] = {}
    for row in read_latest(limit):
        ins = row.get("instrument")
        if ins:
            out[ins] = row  # append-only → 뒤가 최신, 자연 덮어쓰기
    return out


def compute_overlay(strategy_weights: dict[str, float], as_of: str) -> list[dict]:
    """전략별 target_weight(무수정 입력) → 종목별 참고 포지션 + 퓨전 상충 플래그.

    strategy_weights: decision_engine/journal의 기존 결과({sid: weight}) — 여기선 재계산 안 함.
    반환: 종목별 row 리스트(정렬됨). 어댑터 없는 전략은 스킵(정직 — 균등분배 대체 없음).
    """
    fusion = _latest_fusion_by_instrument()
    rows: list[dict] = []
    for sid, tw in sorted(strategy_weights.items()):
        split = _intra_strategy_split(sid, as_of)
        for instrument, info in sorted(split.items()):
            fs = fusion.get(instrument)
            fusion_dir = fs.get("direction") if fs else None
            rows.append({
                "strategy_id": sid,
                "instrument": instrument,
                "strategy_target_weight": round(float(tw), 6),
                "intra_strategy_weight": info["weight"],
                "direction": info["direction"],
                "instrument_target_weight": round(float(tw) * info["weight"] * info["direction"], 6),
                "fusion_direction": fusion_dir,
                "fusion_confidence": fs.get("confidence") if fs else None,
                "conflict": bool(fusion_dir not in (None, 0) and fusion_dir != info["direction"]),
            })
    return rows
