"""arm/kill 기준 사전등록 (FROZEN — 데이터 보기 전에 동결).

목적: 6개월 뒤 OOS 데이터를 본 사람이 자기합리화로 기준을 옮기는 것을 차단.
전략 검증에 적용한 규율(사전등록·동결·튜닝 금지)을 arm 결정 자체에 적용한다.

규칙(결정적):
  GO   — OOS ≥ 3개월 AND envelope 내 비율 ≥ 2/3 AND 페이퍼 ≥ 6개월.
         첫 arm 상한 1,000만원(사람이 낮추는 건 허용, 올리려면 v2 재등록).
  KILL — OOS ≥ 3개월 AND envelope 내 비율 < 1/2 (과반 이탈 = 엣지 소멸).
  WAIT — 그 외 전부. 1~2개월 이탈은 경고만(성급한 kill 금지).

기준 변경 = v2 파일 신규 등록(이 파일 수정 금지). test_arm_criteria가 값을 고정한다.
GO여도 실행은 사람 ADMIN arm() + autonomy>=6 이중 게이트 그대로(이 모듈은 판단 보조).
"""
from __future__ import annotations

FROZEN_AT = "2026-07-04"
VERSION = "arm_criteria_v1"

CRITERIA = {
    "min_oos_months": 3,             # buyback_config.MIN_OBSERVATION_MONTHS와 정합
    "go_in_envelope_ratio": 2 / 3,   # GO: OOS 2/3 이상 envelope 내
    "kill_in_envelope_ratio": 0.5,   # KILL: 과반 이탈
    "min_paper_months": 6,           # jarvis.execution.arm.MIN_PAPER_MONTHS와 정합
    "first_tranche_krw_max": 10_000_000,  # 첫 arm 상한(수용력 46억의 ~0.2%, 분산 유지 가능 최소단위)
}


def evaluate(edge: dict, paper_months: float) -> dict:
    """edge_status 출력 + 페이퍼 개월 → GO/WAIT/KILL. 결정적, 예외 없음."""
    reasons: list[str] = []
    status = edge.get("status", "unavailable")
    oos = int(edge.get("oos_months") or 0)
    inside = int(edge.get("oos_in_envelope") or 0)
    ratio = (inside / oos) if oos > 0 else None

    if status in ("warming", "unavailable"):
        return _out("WAIT", ["edge_pending"])

    # KILL — 충분한 OOS에서 과반 이탈(성급 금지: 3개월 미만이면 경고만)
    if oos >= CRITERIA["min_oos_months"] and ratio is not None and ratio < CRITERIA["kill_in_envelope_ratio"]:
        return _out("KILL", [f"envelope_ratio {ratio:.2f} < {CRITERIA['kill_in_envelope_ratio']} (n_oos={oos}) — 엣지 소멸"])

    # GO — 세 조건 전부
    ok_oos = oos >= CRITERIA["min_oos_months"]
    ok_ratio = ratio is not None and ratio >= CRITERIA["go_in_envelope_ratio"]
    ok_paper = paper_months >= CRITERIA["min_paper_months"]
    if ok_oos and ok_ratio and ok_paper:
        return _out("GO", [f"OOS {oos}개월 · envelope {inside}/{oos} · 페이퍼 {paper_months}mo — 소액 arm 검토 가능"])

    # WAIT — 부족분 명시
    if not ok_oos:
        reasons.append(f"need_oos_months({oos}<{CRITERIA['min_oos_months']})")
    if oos > 0 and ratio is not None and ratio < CRITERIA["kill_in_envelope_ratio"]:
        reasons.append(f"early_drift_watch(envelope {inside}/{oos} — kill은 {CRITERIA['min_oos_months']}개월부터)")
    elif ok_oos and not ok_ratio:
        reasons.append(f"envelope_ratio_insufficient({ratio:.2f}<{CRITERIA['go_in_envelope_ratio']:.2f})")
    if not ok_paper:
        reasons.append(f"need_paper_months({paper_months}<{CRITERIA['min_paper_months']})")
    return _out("WAIT", reasons or ["accumulating"])


def _out(decision: str, reasons: list[str]) -> dict:
    return {"decision": decision, "reasons": reasons,
            "version": VERSION, "frozen_at": FROZEN_AT,
            "first_tranche_krw_max": CRITERIA["first_tranche_krw_max"]}
