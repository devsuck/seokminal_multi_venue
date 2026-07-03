"""단일 판정 함수 — LAB 라이브 루프와 Auto-Research 배치의 유일한 진실원.

두 시스템 장점 결합:
  - Auto-Research 강점: 배치 BH-FDR(다중검정 보정) → '몇 개 시도했는지' 반영.
  - LAB 강점: net>0 + walk-forward 양쪽 양수(강건성 게이트).
candidate = bh_survivor AND 레드팀 CLEARED AND net>0 AND wf 양쪽 양수.

bh_survivor 의미:
  True  — 최신 배치 BH-FDR 생존(확정).
  False — 배치서 탈락(우연 가능).
  None  — LAB 라이브: 아직 배치 미확정. BH-FDR은 전체 배치가 있어야만 계산 가능하므로
          개별 통계만 통과해도 candidate 도장 불가 → pending_bh(잠정). 통계적 정직성.
"""
from __future__ import annotations

# canonical status
CANDIDATE = "candidate"
WATCHLIST = "watchlist"
PENDING_BH = "pending_bh"
REJECT_BH = "reject_bh"
REJECT_REDTEAM = "reject_redteam"
REJECT_STATS = "reject_stats"

DISPLAY: dict[str, str] = {
    CANDIDATE: "CANDIDATE",
    WATCHLIST: "WATCHLIST",
    PENDING_BH: "PENDING",
    REJECT_BH: "REJECT_BH",
    REJECT_REDTEAM: "REJECT_REDTEAM",
    REJECT_STATS: "REJECT_STATS",
}


def _robust(net: float | None, wf_first: float | None, wf_second: float | None) -> bool:
    return (net is not None and net > 0
            and wf_first is not None and wf_first > 0
            and wf_second is not None and wf_second > 0)


def _weak(net: float | None, percentile: float | None) -> bool:
    return net is not None and net > 0 and percentile is not None and percentile >= 80


def classify(*, net: float | None, percentile: float | None, p: float | None,
             wf_first: float | None, wf_second: float | None,
             redteam_verdict: str, bh_survivor: bool | None) -> tuple[str, str]:
    """(status, verdict_text) — 두 시스템 공유. 위 docstring 규칙 적용."""
    redteam_ok = redteam_verdict == "CLEARED"
    robust = _robust(net, wf_first, wf_second)
    weak = _weak(net, percentile)

    if bh_survivor is None:                       # 라이브: 배치 BH 미확정
        if not redteam_ok:
            return REJECT_REDTEAM, "REJECT — 레드팀 통제 실패"
        if robust:
            return PENDING_BH, "PENDING — 개별 통계 통과, 배치 BH-FDR 확정 대기"
        if weak:
            return WATCHLIST, "WATCHLIST — 양수이나 walk-forward 불안정"
        return REJECT_STATS, "REJECT — 매칭 random·비용 못 넘음"

    if not bh_survivor:
        return REJECT_BH, "REJECT — 배치 BH-FDR 탈락(다중검정 우연 가능)"

    # bh_survivor True
    if not redteam_ok:
        return REJECT_REDTEAM, "REJECT — 레드팀 통제 실패"
    if robust:
        return CANDIDATE, "CANDIDATE — BH-FDR 생존 + 레드팀 + net·walk-forward 통과"
    if weak:
        return WATCHLIST, "WATCHLIST — BH 생존이나 walk-forward 불안정"
    return REJECT_STATS, "REJECT — net·walk-forward 미달"
