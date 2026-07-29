"""Fill Matcher (P8.3) — 브로커 체결 → 내부 주문 매칭 + 집계. 결정적·순수함수.

매칭: ①broker_order_id(link_map 경유) ②fallback: request_id 동등.
다중 체결(부분체결) 집계: total_quantity · weighted_average_price · total_fee.
중복 체결(fill_id) 제거. **주문/집행/브로커 write 없음.**
"""
from __future__ import annotations

from dataclasses import dataclass, field

_EPS = 1e-12


@dataclass
class MatchResult:
    matched: dict = field(default_factory=dict)      # order_id -> [fill dict]
    missing: list = field(default_factory=list)      # 체결 없는 내부 기록 order_id
    unexpected: list = field(default_factory=list)   # 매칭 안 된 브로커 체결


def _fdict(f):
    return f.to_dict() if hasattr(f, "to_dict") else f


def _rdict(r):
    return r.to_dict() if hasattr(r, "to_dict") else r


def dedup_fills(fills: list) -> list:
    """fill_id 기준 중복 제거(첫 등장 유지). 순서 보존."""
    seen = set()
    out = []
    for f in fills:
        d = _fdict(f)
        fid = d.get("fill_id")
        if fid in seen:
            continue
        seen.add(fid)
        out.append(d)
    return out


def aggregate(fills: list) -> dict:
    """부분체결 집계: 총수량·수량가중평균가·총수수료. 중복 제거 후."""
    ded = dedup_fills(fills)
    tq = sum(float(f.get("quantity", 0.0)) for f in ded)
    tf = sum(float(f.get("fee", 0.0)) for f in ded)
    if abs(tq) > _EPS:
        wap = sum(float(f.get("quantity", 0.0)) * float(f.get("fill_price", 0.0))
                  for f in ded) / tq
    else:
        wap = 0.0
    last_ts = max((f.get("timestamp", "") for f in ded), default="")
    return {"total_quantity": round(tq, 8), "weighted_average_price": round(wap, 8),
            "total_fee": round(tf, 8), "n_fills": len(ded), "last_timestamp": last_ts}


def match(records: list, fills: list, link_map: dict | None = None) -> MatchResult:
    """내부 기록 ↔ 브로커 체결 매칭.

    link_map: broker_order_id -> order_id (P8.2 생애주기에서 유도). 없으면 request_id fallback.
    """
    link_map = link_map or {}
    recs = {_rdict(r)["order_id"]: _rdict(r) for r in records}
    req_index = {_rdict(r)["request_id"]: _rdict(r)["order_id"] for r in records}

    matched: dict = {oid: [] for oid in recs}
    unexpected: list = []
    for f in dedup_fills(fills):
        boid = f.get("broker_order_id", "")
        oid = link_map.get(boid)
        if oid is None or oid not in recs:
            # fallback: broker_order_id가 request_id를 참조(mock 등)
            oid = req_index.get(boid)
        if oid is not None and oid in recs:
            matched[oid].append(f)
        else:
            unexpected.append(f)

    missing = sorted(oid for oid, fs in matched.items() if not fs)
    matched = {oid: fs for oid, fs in matched.items() if fs}
    return MatchResult(matched=matched, missing=missing, unexpected=unexpected)
