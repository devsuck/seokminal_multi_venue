"""Research Critic (P75) — 실험이 가치 있다고 보기 전에 **자동 비판**한다. **자동 수용 없음.**

8개 차원으로 결정적 비판: look-ahead·survivorship·data leakage·overfitting·parameter instability·
regime dependence·liquidity·cost sensitivity. 각 차원은 severity(PASS/WARN/BLOCK)·finding·evidence 를 낸다.
약한 연구는 BLOCK. **재사용**: research_ingestion.auto_classify_failure + research_assistant.classify_failure
분류체계, StrategyRiskReasoner 휴리스틱과 동일 임계.

원칙(문서 §Constitution, §P75): 새 지능/새 저장소 없음 — 조율. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

PASS, WARN, BLOCK = "PASS", "WARN", "BLOCK"
DIMENSIONS = ("look_ahead", "survivorship", "data_leakage", "overfitting",
              "parameter_instability", "regime_dependence", "liquidity", "cost_sensitivity")
_LOOKAHEAD_TOKENS = ("forward", "future", "next_", "lookahead", "look_ahead", "ahead")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Critique:
    dimension: str
    severity: str                # PASS | WARN | BLOCK
    finding: str
    evidence: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CritiqueReport:
    subject: str
    critiques: list
    verdict: str                 # PASS | WARN | BLOCK
    blocks: bool
    blocking_dimensions: list
    requires_human_review: bool = True   # 자동 수용 없음
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["critiques"] = [c.to_dict() if isinstance(c, Critique) else c for c in self.critiques]
        return d


class ResearchCritic:
    """실험 스펙/결과를 8차원으로 비판. 약한 연구 BLOCK. 자동 수용 없음. 실행 권한 없음."""

    def critique(self, spec, metrics: dict | None = None) -> CritiqueReport:
        """스펙(dict/ExperimentSpec) + (선택)백테스트 metrics → 구조화 비판. 결정적."""
        s = spec.to_dict() if hasattr(spec, "to_dict") else dict(spec or {})
        m = metrics or s.get("metrics") or {}
        name = str(s.get("strategy_name", "") or "experiment")
        features = [str(f).lower() for f in (s.get("feature_set") or s.get("features") or [])]
        cs: list = []

        def add(dim, sev, finding, evidence):
            cs.append(Critique(dimension=dim, severity=sev, finding=finding, evidence=str(evidence)))

        # 1) look-ahead — 피처가 미래 정보를 참조하는가
        la = [f for f in features if any(tok in f for tok in _LOOKAHEAD_TOKENS)]
        add("look_ahead", BLOCK if la else PASS,
            "피처가 미래 시점 정보를 참조" if la else "피처 시점 정합 — point-in-time 확인 권장",
            f"features={la}" if la else "no future-referencing feature")

        # 2) survivorship — 유니버스 생존편향
        pit = bool(s.get("point_in_time"))
        add("survivorship", PASS if pit else WARN,
            "point-in-time 유니버스 확인됨" if pit else "상장폐지 포함 여부 미확인 — 생존편향 위험",
            f"universe={s.get('universe', '?')}")

        # 3) data leakage — 라벨/피처 시점 중첩
        label = str(s.get("labels", "")).lower()
        leak = any(label and label.split("forward_")[-1][:6] in f for f in features) if label else False
        add("data_leakage", WARN if leak else PASS,
            "피처가 라벨 구간과 중첩 가능" if leak else "라벨/피처 시점 분리 — 재확인 권장",
            f"labels={s.get('labels', '?')}")

        # 4) overfitting — sharpe vs OOS 격차 / walk-forward
        sharpe, oos, wf = _num(m.get("sharpe")), _num(m.get("out_of_sample")), _num(m.get("walk_forward"))
        if sharpe is not None and oos is not None and (sharpe - oos) >= 0.5:
            add("overfitting", BLOCK, "인샘플-OOS 격차 과대 — 과적합", f"sharpe-oos={round(sharpe - oos, 3)}")
        elif wf is not None and wf < 0.5:
            add("overfitting", WARN, "walk-forward 일관성 낮음", f"walk_forward={wf}")
        else:
            add("overfitting", PASS if m else WARN, "과적합 신호 없음" if m else "백테스트 전 — 검증 대기",
                f"walk_forward={wf}")

        # 5) parameter instability
        pstab = _num(m.get("parameter_stability"))
        if pstab is not None and pstab <= 0.3:
            add("parameter_instability", BLOCK, "파라미터 매우 불안정", f"parameter_stability={pstab}")
        elif pstab is not None and pstab <= 0.5:
            add("parameter_instability", WARN, "파라미터 민감", f"parameter_stability={pstab}")
        else:
            add("parameter_instability", PASS if pstab is not None else WARN,
                "안정 구간" if pstab is not None else "민감도 분석 대기", f"parameter_stability={pstab}")

        # 6) regime dependence
        rd = m.get("regime_dependent") is True or (wf is not None and wf < 0.5)
        add("regime_dependence", WARN if rd else PASS,
            "레짐 의존 가능성" if rd else "레짐 로버스트니스 확인 권장",
            f"regime_dependent={m.get('regime_dependent')}")

        # 7) liquidity
        turnover = _num(m.get("turnover"))
        hi_turn = (turnover is not None and turnover >= 0.5) or s.get("rebalance") in ("weekly", "daily")
        add("liquidity", WARN if hi_turn else PASS,
            "높은 회전율 — 체결가능 규모 확인" if hi_turn else "유동성 이슈 신호 없음",
            f"rebalance={s.get('rebalance', '?')} turnover={turnover}")

        # 8) cost sensitivity
        cost = _num(m.get("cost_impact"))
        if cost is not None and cost >= 0.3:
            add("cost_sensitivity", BLOCK, "거래비용 민감 — 엣지 잠식", f"cost_impact={cost}")
        elif cost is not None and cost >= 0.15:
            add("cost_sensitivity", WARN, "거래비용 영향 상당", f"cost_impact={cost}")
        else:
            add("cost_sensitivity", PASS if cost is not None else WARN,
                "비용 강건" if cost is not None else "비용 반영 백테스트 대기", f"cost_impact={cost}")

        blocking = [c.dimension for c in cs if c.severity == BLOCK]
        verdict = BLOCK if blocking else (WARN if any(c.severity == WARN for c in cs) else PASS)
        return CritiqueReport(subject=name, critiques=cs, verdict=verdict,
                              blocks=bool(blocking), blocking_dimensions=blocking)
