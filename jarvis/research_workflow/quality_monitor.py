"""Research Quality System (P106) — 연구 품질을 감시해 **약한 연구 누적을 방지**한다. **읽기 전용.**

ResearchQualityMonitor 는 sample size·out-of-sample·walk-forward·cost sensitivity·parameter stability·
reproducibility 를 평가해 Quality Score 를 낸다. **재사용**: quality_score.score_research(P84) +
research_ingestion.validate_backtest. 약한 연구(D등급/미검증)를 게이트로 표시 — 새 저장소 없음.

원칙(문서 §Constitution, §P106): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations

_WEAK_GRADE = ("C", "D")
_ACCEPT_FLOOR = 65.0     # 이 아래는 '약한 연구' — 누적 방지 게이트


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class ResearchQualityMonitor:
    """연구 품질 감시 — 결정적 점수 + 약점/누락 증거 + 약한 연구 게이트. 저장하지 않음, 관찰만."""

    def evaluate(self, backtest: dict, *, assistant=None) -> dict:
        """백테스트/연구 dict → Quality Score + 6개 핵심 차원 + 약점/누락 + 수용 게이트. 결정적."""
        from jarvis.research_workflow.quality_score import score_research
        sc = score_research(backtest, assistant=assistant)
        dims = sc.get("dimensions", {})
        m = (backtest or {}).get("metrics") or {}

        # 스펙이 요구하는 6개 핵심 차원(기존 dims + sample size 파생)
        n_obs = _num(m.get("n_obs") or m.get("sample_size") or m.get("observations"))
        sample_size = (1.0 if (n_obs and n_obs >= 500) else 0.6 if (n_obs and n_obs >= 100)
                       else 0.3 if n_obs else 0.0)
        param_stability = _num(m.get("parameter_stability"))
        core = {
            "sample_size": round(sample_size, 4),
            "out_of_sample": dims.get("out_of_sample", 0.0),
            "walk_forward": dims.get("walk_forward", 0.0),
            "cost_sensitivity": dims.get("transaction_cost", 0.0),
            "parameter_stability": round(param_stability, 4) if param_stability is not None else 0.0,
            "reproducibility": dims.get("reproducibility", 0.0),
        }
        weak = [k for k, v in core.items() if v < 0.5]
        overall = sc.get("overall_quality", 0.0)
        grade = sc.get("grade", "D")
        accepted = bool(overall >= _ACCEPT_FLOOR and sc.get("validation_complete"))
        return {"strategy": sc.get("strategy"), "core_dimensions": core, "all_dimensions": dims,
                "quality_score": overall, "grade": grade,
                "validation_complete": sc.get("validation_complete"),
                "missing_validations": sc.get("missing_validations", []),
                "weaknesses": weak, "weak_research": grade in _WEAK_GRADE,
                "accepted": accepted,
                "gate": ("ACCEPT" if accepted else "NEEDS_MORE_EVIDENCE"),
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("연구 품질 점수(읽기전용) — score_research 재사용. 약한 연구 누적 방지 게이트. "
                         "새 저장소 없음, 거래·집행 없음.")}


def evaluate(backtest: dict, *, assistant=None) -> dict:
    """모듈 진입점 — ResearchQualityMonitor.evaluate 래퍼."""
    return ResearchQualityMonitor().evaluate(backtest, assistant=assistant)
