"""Research Planner 자료형 (P5) — 커버리지 최적화기(아이디어 생성기 아님).

ResearchGap(관찰된 격차) → PlannerProposal(연구방향 제안). 제안 전용, 집행 없음.
결정적: 같은 projection/graph → 같은 제안. 점수는 설명가능 인자곱(ML/난수 없음).
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

# 제안 카테고리(6)
CATEGORIES = ["MISSING_REGIME", "MISSING_STRATEGY_FAMILY", "REPLACE_FAILED_STRATEGY",
              "REDUCE_REDUNDANCY", "DATA_GAP", "KNOWLEDGE_GAP"]

# 연구 매트릭스 기준 정규 패밀리(GENERATOR.md) + 레짐(regime_filter vocab)
CANONICAL_FAMILIES = ["event", "trend", "mean_reversion", "factor",
                      "microstructure", "carry", "seasonality"]
CANONICAL_REGIMES = ["bull_low_vol", "bull_high_vol", "bear_low_vol", "bear_high_vol"]

# id/이름 → 패밀리(구체 규칙 우선). 미매칭 = unclassified.
_FAMILY_RULES = [
    ("auto_ev_", "event"), ("buyback", "event"), ("dart", "event"), ("spinoff", "event"),
    ("insider", "event"), ("congress", "event"), ("form4", "event"), ("capital_reduction", "event"),
    ("supply_contract", "event"), ("treasury", "event"), ("turn_to_profit", "event"),
    ("cb_bw", "event"), ("bonus", "event"), ("rights", "event"), ("index_forced", "event"),
    ("auto_fac_", "factor"), ("factor", "factor"), ("smb", "factor"), ("size", "factor"),
    ("amihud", "factor"), ("illiq", "factor"), ("turnover_neglect", "factor"),
    ("tsmom", "trend"), ("momentum", "trend"), ("mom_", "trend"), ("breakout", "trend"),
    ("orb", "trend"), ("gap_", "trend"), ("xs_momentum", "trend"),
    ("reversion", "mean_reversion"), ("vwap", "mean_reversion"), ("mean_rev", "mean_reversion"),
    ("pairs", "mean_reversion"), ("cointegration", "mean_reversion"), ("compression", "mean_reversion"),
    ("ict", "microstructure"), ("orderflow", "microstructure"), ("smt", "microstructure"),
    ("skew", "microstructure"), ("gex", "microstructure"), ("absorption", "microstructure"),
    ("funding", "carry"), ("basis", "carry"), ("carry", "carry"), ("gold", "carry"), ("haven", "carry"),
    ("turn_of_month", "seasonality"), ("tom", "seasonality"), ("seasonal", "seasonality"),
    ("weekend", "seasonality"), ("overnight", "seasonality"),
]


def family_of(identifier: str) -> str:
    s = (identifier or "").lower()
    for kw, fam in _FAMILY_RULES:
        if kw in s:
            return fam
    return "unclassified"


@dataclass(frozen=True)
class ResearchGap:
    id: str
    type: str                 # = 제안 카테고리
    description: str
    evidence: dict = field(default_factory=dict)
    priority_score: float = 0.0
    related_entities: list = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PlannerProposal:
    proposal_id: str
    category: str
    target_area: str
    rationale: list = field(default_factory=list)
    expected_value: float = 0.0
    confidence: float = 0.0
    priority_score: float = 0.0
    dependencies: list = field(default_factory=list)
    status: str = "proposed"
    factors: dict = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def gap_id(gap_type: str, key: str) -> str:
    return "G:" + hashlib.sha1(f"{gap_type}|{key}".encode()).hexdigest()[:12]


def proposal_id(category: str, target_area: str) -> str:
    return "P:" + hashlib.sha1(f"{category}|{target_area}".encode()).hexdigest()[:12]
