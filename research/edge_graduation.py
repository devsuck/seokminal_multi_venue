"""엣지 졸업 스코어카드 — "이 엣지에 돈 걸어도 되나"를 명시적 합격선으로 판정(순수).

수익 목적 규율: "충분히 좋은가?"라는 애매함을 커밋된 게이트로 바꾼다. 검증 요약
(summarize_report)과 감쇠 궤적(edge_history)만으로 하드 기준 4개를 매기고, 넷 다
통과해야 'graduated'(소액 라이브 후보). 표본이 충분한데 신호가 없으면 'failed'(진짜
음성 — 다음 후보로), 아직 데이터/이력이 모자라면 'accumulating'(수집 계속).

기준(전부 명시·고정, 결과 보고 안 바꿈):
  1. powered        — 표본 n_events >= min_events (검정력 확보, 언더파워 아님)
  2. p_strong       — 최소 p-value <= alpha
  3. fdr_survivor   — BH-FDR 생존 > 0 (다중검정·비용 반영 후에도 살아남음)
  4. oos_persistence— 누적되는 forward 데이터에서 반복 검증 시 계속 유의
                      (최근 min_history회 중 oos_ratio 이상 유의) = 사후 out-of-sample 지속성

핵심: graduated는 과거 한 방이 아니라 **시간에 걸쳐 forward로 버틴 것**만. 매 워밍이
새 데이터를 포함하므로 궤적 위 지속성이 사실상 OOS 증거다.
"""
from __future__ import annotations

from dataclasses import dataclass

_CRITERIA_ORDER = ["powered", "p_strong", "fdr_survivor", "oos_persistence"]


@dataclass
class GradeCriteria:
    alpha: float = 0.05
    min_events: int = 30
    min_history: int = 10            # OOS 지속성 판단에 필요한 검증 반복 횟수
    oos_significant_ratio: float = 0.6   # 최근 이력 중 유의 비율 하한


def grade_edge(summary: dict | None, trajectory: list[dict], criteria: GradeCriteria | None = None) -> dict:
    """엣지 요약 + 감쇠 궤적 → 졸업 판정. summary=None(검증 리포트 없음)이면 accumulating.
    반환: {status, readiness, checks:{name:{pass,detail}}, reason}."""
    c = criteria or GradeCriteria()
    if summary is None:
        return {"status": "accumulating", "readiness": 0.0, "checks": {},
                "reason": "검증 리포트 없음(수집/조립 대기)"}

    n_events = int(summary.get("n_events") or 0)
    min_p = summary.get("min_p_value")
    n_surv = int(summary.get("n_survivors") or 0)

    powered = n_events >= c.min_events
    p_strong = min_p is not None and min_p <= c.alpha
    fdr_survivor = n_surv > 0

    history = len(trajectory)
    recent = trajectory[-c.min_history:] if history else []
    recent_sig = sum(1 for r in recent if r.get("significant"))
    oos_ratio = (recent_sig / len(recent)) if recent else 0.0
    enough_history = history >= c.min_history
    oos_persistence = enough_history and oos_ratio >= c.oos_significant_ratio

    checks = {
        "powered": {"pass": powered, "detail": f"표본 {n_events} / 최소 {c.min_events}"},
        "p_strong": {"pass": p_strong,
                     "detail": f"최소 p={min_p if min_p is not None else '—'} / α={c.alpha}"},
        "fdr_survivor": {"pass": fdr_survivor, "detail": f"FDR 생존 {n_surv}"},
        "oos_persistence": {"pass": oos_persistence,
                            "detail": (f"최근 {len(recent)}회 중 유의 {recent_sig}"
                                       f"({oos_ratio:.0%}), 이력 {history}/{c.min_history}")},
    }
    n_pass = sum(1 for k in _CRITERIA_ORDER if checks[k]["pass"])
    readiness = round(n_pass / len(_CRITERIA_ORDER), 2)

    # 상태 판정: powered 전엔 판단유보(축적), powered인데 신호없으면 탈락(진짜 음성),
    # 신호는 있으나 forward 지속성 미확보면 축적, 넷 다 통과해야 졸업.
    if not powered:
        status, reason = "accumulating", "표본 부족 — 데이터 축적 중"
    elif not (p_strong and fdr_survivor):
        status, reason = "failed", "표본 충분한데 비용·FDR 후 유의성 없음(진짜 음성)"
    elif not oos_persistence:
        status, reason = "accumulating", "유의하나 forward 지속성 미확보 — 반복검증 축적 중"
    else:
        status, reason = "graduated", "전 기준 통과 — 소액 라이브 후보"
    return {"status": status, "readiness": readiness, "checks": checks, "reason": reason}
