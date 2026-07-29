"""Experiment Planner (P74) — 가설을 **재현 가능한 실험 스펙**으로 변환한다. **설계만, 실행 없음.**

universe·timeframe·rebalance·feature set·labels·transaction costs·walk-forward 요건·random baseline·
validation checklist 을 결정적으로 정의한다. **검증 체크리스트는 research_ingestion.REQUIRED_VALIDATIONS 재사용**
(기존 검증/백테스트 인프라). 동일 가설 → 동일 스펙(spec_hash) — 재현성.

원칙(문서 §Constitution, §P74): 새 지능/새 저장소 없음 — 조율. 거래·집행 없음. 결정적.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from jarvis.research_workflow import models as M

# 전략 유형(키워드) → 설계 프로파일 (결정적)
_PROFILES = (
    (("momentum", "tsmom", "trend", "breakout"),
     {"universe": "GLOBAL_FUT", "timeframe": "1d", "rebalance": "monthly",
      "features": ["ret_12m", "ret_3m", "vol_20d"], "labels": "forward_return_20d"}),
    (("reversion", "mean", "vwap", "pairs"),
     {"universe": "US_EQ", "timeframe": "1d", "rebalance": "weekly",
      "features": ["zscore_20d", "rsi_14", "vol_20d"], "labels": "forward_return_5d"}),
    (("value", "quality", "factor", "carry"),
     {"universe": "KR_EQ", "timeframe": "1d", "rebalance": "quarterly",
      "features": ["book_to_price", "earnings_yield", "roe"], "labels": "forward_return_60d"}),
    (("supply", "lead-lag", "lead lag", "propagate"),
     {"universe": "SECTOR_LINK", "timeframe": "1d", "rebalance": "weekly",
      "features": ["lead_lag_corr", "upstream_ret"], "labels": "forward_return_10d"}),
)
_DEFAULT = {"universe": "US_EQ", "timeframe": "1d", "rebalance": "monthly",
            "features": ["signal_score", "vol_20d"], "labels": "forward_return_20d"}

_TX_COSTS = {"cost_bps": 5.0, "slippage_bps": 2.0, "spread_bps": 4.0, "effective_bps": 11.0}
_WALK_FORWARD = {"n_windows": 5, "min_oos_fraction": 0.3, "consistency_threshold": 0.6}
_RANDOM_BASELINE = {"method": "same_frequency", "n_runs": 500, "seed": 42}


def _profile(text: str) -> dict:
    low = (text or "").lower()
    for keys, prof in _PROFILES:
        if any(k in low for k in keys):
            return prof
    return _DEFAULT


@dataclass(frozen=True)
class ExperimentSpec:
    spec_id: str
    hypothesis_id: str
    strategy_name: str
    universe: str
    timeframe: str
    rebalance: str
    feature_set: list
    labels: str
    transaction_costs: dict
    walk_forward: dict
    random_baseline: dict
    validation_checklist: list     # REQUIRED_VALIDATIONS 재사용
    spec_hash: str
    requires_human_review: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def to_ingestion_schema(self) -> dict:
        """research_ingestion(P53) 백테스트 스키마 스켈레톤 — 실행 후 metrics 채워짐(그전엔 INCOMPLETE)."""
        return {"strategy_name": self.strategy_name, "strategy_version": "plan",
                "hypothesis": self.strategy_name, "universe": self.universe,
                "period": {"start": "", "end": ""}, "features": list(self.feature_set),
                "entry_rules": f"{self.rebalance} rebalance on {self.labels}",
                "exit_rules": self.rebalance, "risk_rules": "equal risk per name",
                "metrics": {}, "source": "experiment_planner"}


class ExperimentPlanner:
    """가설 → 재현 가능한 실험 스펙. 기존 검증 체크리스트 재사용. 실행 권한 없음."""

    def plan(self, hypothesis) -> ExperimentSpec:
        """가설(dict 또는 Hypothesis) → ExperimentSpec. 결정적·재현 가능(동일 가설 → 동일 spec_hash)."""
        h = hypothesis.to_dict() if hasattr(hypothesis, "to_dict") else dict(hypothesis or {})
        stmt = str(h.get("statement", ""))
        hid = str(h.get("hypothesis_id", M.hypothesis_id(stmt)))
        prof = _profile(stmt + " " + str(h.get("source", "")))
        name = stmt.split(" produces")[0].strip() or "planned_strategy"

        from jarvis.research_ingestion.models import REQUIRED_VALIDATIONS
        checklist = [{"metric": m, "required": True, "status": "PENDING"} for m in REQUIRED_VALIDATIONS]

        core = {"strategy_name": name, "universe": prof["universe"], "timeframe": prof["timeframe"],
                "rebalance": prof["rebalance"], "feature_set": list(prof["features"]),
                "labels": prof["labels"], "transaction_costs": dict(_TX_COSTS),
                "walk_forward": dict(_WALK_FORWARD), "random_baseline": dict(_RANDOM_BASELINE),
                "validation_checklist": [c["metric"] for c in checklist]}
        spec_hash = M.content_digest(core)
        return ExperimentSpec(
            spec_id=M.spec_id(hid), hypothesis_id=hid, strategy_name=name,
            universe=prof["universe"], timeframe=prof["timeframe"], rebalance=prof["rebalance"],
            feature_set=list(prof["features"]), labels=prof["labels"],
            transaction_costs=dict(_TX_COSTS), walk_forward=dict(_WALK_FORWARD),
            random_baseline=dict(_RANDOM_BASELINE), validation_checklist=checklist,
            spec_hash=spec_hash)
