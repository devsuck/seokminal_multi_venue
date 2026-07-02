"""검증 결과 통합 요약 — registry → VALIDATION_SUMMARY.md.

"검증된 엣지 0개"를 명시. 실패 사유 분류. 알파 사냥 정리(Week 1) 산출물.
실행: PYTHONPATH=. python3 research/summarize_registry.py
"""
from __future__ import annotations

import os

from research.agents.experiment_registry import load_all

OUT = os.path.join(os.path.dirname(__file__), "reports", "VALIDATION_SUMMARY.md")

# 실패 기전 분류 (분해 결과 기반, 수동 큐레이션)
FAILURE_CLASS = {
    "orb_rvol_vwap": "signal_dead (gross도 음수)",
    "atr_compression": "signal_dead (gross도 음수)",
    "vwap_mean_reversion": "cost_killed (gross+, 거래당 엣지<비용)",
    "orb_failed_reversal": "cost_killed (gross+, 거래당 엣지<비용)",
    "gap_continuation": "cost_killed (gross+, 거래당 엣지<비용)",
    "sector_relative_momentum": "cost_killed (gross+, 거래당 엣지<비용)",
    "funding_extreme_reversal": "indistinguishable_from_random (net+ but <80pct)",
    "cross_sectional_funding": "cost_killed (일 리밸런스 과잉거래)",
    "cross_sectional_funding_weekly": "indistinguishable_from_random (net+ but 82.6pct, WF 불안정)",
    "delta_neutral_carry_hl": "blocked_by_data (메이저 spot 부재)",
    "futures_tsmom": "decayed/marginal (Sharpe 0.44 최고근접·buyhold초과·91.5pct지만 <95·WF후반 붕괴=감쇠)",
}


def main():
    entries = load_all()
    rejected = [e for e in entries if e.get("status") == "rejected"]
    blocked = [e for e in entries if "blocked" in (e.get("status") or "")]
    candidates = [e for e in entries if e.get("status") in ("candidate", "watchlist", "paper_candidate")]

    lines = [
        "# Strategy Validation — Results Summary",
        "",
        "> **검증된 엣지: 0개.** 이 시스템은 \"돈 버는 봇\"이 아니라 **전략을 냉정하게 죽이는 검증 터미널**이다.",
        "> 방법: 비용 반영 + random same-frequency 분포 + walk-forward + BH-FDR + underpowered guard + gross/net 분해.",
        "",
        f"- 테스트한 가설: **{len(rejected) + len(blocked) + len(candidates)}**",
        f"- REJECT: **{len(rejected)}**  |  BLOCKED(데이터): {len(blocked)}  |  후보: {len(candidates)}",
        "- **Lv3 자율 리서치 에이전트: 진입 보류**(탐색할 검증 엣지 0개)",
        "",
        "## 판정 테이블",
        "| 가설 | 상태 | net | 실패 기전 |",
        "|---|---|---|---|",
    ]
    for e in entries:
        hid = e.get("hypothesis_id", "?")
        net = e.get("net_pnl", e.get("net", ""))
        lines.append(f"| {hid} | {e.get('status','?')} | {net} | {FAILURE_CLASS.get(hid,'')} |")

    lines += [
        "",
        "## 실패 기전 분류",
        "- **signal_dead**: gross(비용 0)도 음수 → 신호 자체 없음. (ORB, ATR압축)",
        "- **cost_killed**: gross 양수지만 거래당 엣지가 비용보다 작음(과잉거래). (VWAP-MR, 실패돌파, 갭, 섹터, cross-sectional daily)",
        "- **indistinguishable_from_random**: net 양수지만 random 분포 95pct 미달 = 운/변동성. (funding reversal, weekly funding)",
        "- **blocked_by_data**: 데이터 게이트 실패. (delta-neutral carry — 메이저 spot 부재)",
        "",
        "## 핵심 교훈",
        "1. 교과서 알파(주식 인트라데이 + 크립토 funding)는 리테일 규모·현실 비용에서 척박.",
        "2. gross 양수 ≠ 엣지. 거래당 엣지가 비용을 넘고 random 분포를 이겨야 함.",
        "3. weekly funding이 net+13.6k 냈지만 random 82.6pct = 엣지 아니라 변동성.",
        "4. 값진 자산 = 알파가 아니라 **알파 없음을 싸게 증명하는 검증 프레임워크**.",
        "",
        "## 포지셔닝",
        "- ❌ AI Trading Bot  →  ⭕ **Strategy Validation Terminal**",
        "- 실투자: 패시브/저빈도. 고급 알파원(이벤트/온체인/옵션)은 학습·제품기능 한정.",
    ]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {OUT}")
    print("\n".join(lines[:14]))


if __name__ == "__main__":
    main()
