"""Polymarket 함의관계 위반 리포트 — 기존 BH-FDR compute_report와 다른 집계.

논리위반은 통계적 유의성이 아니라 (1)정성적 QA 오탐률(사람이 직접 확인,
자동화 밖) (2)포워드 페이퍼 로깅 pnl 집계로 검증한다(spec §6). 이 스크립트는
(2)만 자동화 — violations.jsonl을 pattern_type(A/B)별로 나눠 탐지건수/
해소건수/평균pnl/승률을 낸다. 최소 N=20~30건 쌓이기 전엔 결론 내지 말 것
(spec §6-2, 사용자 명시 요구 — sharp_wallet 표본부족 보류 반복 방지)."""
from __future__ import annotations

import json

from research.run_polymarket_market_implication_watch import load_violations

MIN_FORWARD_N = 20


def compute_report(violations: list[dict] | None = None) -> dict:
    violations = violations if violations is not None else load_violations()
    report = {}
    for pattern in ("A", "B"):
        pv = [v for v in violations if v["pattern_type"] == pattern]
        resolved = [v for v in pv if v.get("resolved")]
        pnls = [v["pnl_per_share"] for v in resolved]
        n = len(pnls)
        report[pattern] = {
            "detected": len(pv),
            "resolved": n,
            "mean_pnl": round(sum(pnls) / n, 4) if n else None,
            "win_rate": round(sum(1 for p in pnls if p > 0) / n, 4) if n else None,
            "verdict": "insufficient_sample" if n < MIN_FORWARD_N else "ready_for_review",
        }
    return report


def main() -> None:
    print(json.dumps(compute_report(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
