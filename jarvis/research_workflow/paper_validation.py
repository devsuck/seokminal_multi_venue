"""Paper Validation System (P103) — 기존 paper_feedback 고도화. **읽기 전용, 새 저장소 없음.**

PaperValidationMonitor 는 페이퍼 대비 백테스트를 return·volatility·drawdown·turnover·exposure·
benchmark difference 로 추적하고 PaperValidationReport 를 만든다. 목적: **백테스트는 성공했지만 페이퍼는
실패**한 경우를 감지. **재사용**: PaperTradingFeedback.compare(P63) — 학습은 기존 rmi_ 로.

원칙(문서 §Constitution, §P103): 통합·조율만. 결정적. 거래·집행 없음. 사람 결정.
"""
from __future__ import annotations

_TRACKED = ("return", "volatility", "drawdown", "turnover", "exposure", "benchmark_difference")
_SUCCESS_RETURN = 0.0     # 백테스트 성공 기준(양의 수익 기대)
_FAIL_RATIO = 0.5         # 페이퍼가 기대의 절반 미만이면 실패 신호


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _metrics(d: dict) -> dict:
    d = d or {}
    return d.get("metrics") if isinstance(d.get("metrics"), dict) else d


def _drawdown(m: dict):
    return _num(m.get("drawdown") if m.get("drawdown") is not None else m.get("max_drawdown"))


class PaperValidationMonitor:
    """페이퍼 검증 모니터 — 백테스트 기대 vs 페이퍼 실현을 다차원 추적. 실행 안 함, 관찰만."""

    def monitor(self, backtest: dict, paper: dict, *, benchmark: dict | None = None) -> dict:
        """백테스트 vs 페이퍼 → PaperValidationReport(결정적). 추적: 수익·변동성·낙폭·회전·노출·벤치마크차."""
        e, p = _metrics(backtest), _metrics(paper)
        bm = _metrics(benchmark) if benchmark else {}

        # 기존 차이 분석(수익/샤프/낙폭·원인·심각도) 재사용
        try:
            from jarvis.research_ingestion.paper_feedback import PaperTradingFeedback
            diff = PaperTradingFeedback().compare(backtest, paper).to_dict()
        except Exception:  # noqa: BLE001
            diff = {}

        metrics = {}
        for key in _TRACKED:
            if key == "drawdown":
                exp, act = _drawdown(e), _drawdown(p)
            elif key == "benchmark_difference":
                pr, br = _num(p.get("return")), _num(bm.get("return"))
                exp = None
                act = round(pr - br, 4) if (pr is not None and br is not None) else None
            else:
                exp, act = _num(e.get(key)), _num(p.get(key))
            gap = round(act - exp, 4) if (exp is not None and act is not None) else None
            metrics[key] = {"expected": exp, "actual": act, "gap": gap}

        # 백테스트 성공 but 페이퍼 실패 감지
        er, pr = _num(e.get("return")), _num(p.get("return"))
        backtest_success = er is not None and er > _SUCCESS_RETURN
        paper_failure = bool(backtest_success and pr is not None and pr < er * _FAIL_RATIO)
        divergence = paper_failure or (diff.get("severity") == "HIGH")

        status = ("BACKTEST_SUCCESS_PAPER_FAILURE" if paper_failure else
                  "DIVERGENCE" if divergence else
                  "CONSISTENT" if (er is not None and pr is not None) else "INSUFFICIENT_DATA")
        return {"strategy": str((backtest or {}).get("strategy_name", "") or "research"),
                "tracked_metrics": metrics, "difference": diff,
                "backtest_success": backtest_success, "paper_failure": paper_failure,
                "divergence_detected": divergence, "status": status,
                "cause": diff.get("cause", ""), "severity": diff.get("severity", "LOW"),
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("페이퍼 검증 리포트(읽기전용) — 백테스트 성공/페이퍼 실패 감지. "
                         "학습은 기존 rmi_ 로(paper_feedback). 거래·집행 없음.")}


def validate(backtest: dict, paper: dict, *, benchmark: dict | None = None) -> dict:
    """모듈 진입점 — PaperValidationMonitor.monitor 래퍼."""
    return PaperValidationMonitor().monitor(backtest, paper, benchmark=benchmark)
