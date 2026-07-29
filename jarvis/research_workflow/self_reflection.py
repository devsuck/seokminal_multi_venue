"""Self Reflection (P176) — 완료된 연구 사이클을 성찰한다. **성찰·교훈만, 실행 없음.**

사이클 종료 후 결정적으로 묻는다: 어떤 가정이 실패/생존했나 · 무엇이 놀라웠나 · 어떤 증거가 부족했나 ·
무엇이 강화됐나 · 다음에 무엇을 테스트할까 · 무엇은 다시 테스트하지 말까.

교훈은 **기존 메모리 인프라만** 사용해 저장한다(learning_engine P136 → rmi_ 원장). **새 메모리 시스템 없음.**
사이클 미제공 시 기존 research_ingestion 요약에서 성찰을 유도(읽기전용).

원칙(문서 §Constitution, §P176): 통합·조율만 · 결정적 · 자문 전용 · 새 메모리 없음 · 거래·집행 없음 · 사람 결정.
"""
from __future__ import annotations

_SHARPE_SUCCESS = 0.5


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _reflect_from_cycle(cycle):
    """사이클 dict {hypothesis, assumptions, backtest, paper, outcome} → 성찰(결정적)."""
    c = cycle or {}
    metrics = (c.get("backtest") or {}).get("metrics") or c.get("metrics") or {}
    outcome = str(c.get("outcome", "")).upper()
    sharpe = _num(metrics.get("sharpe"))
    oos = _num(metrics.get("out_of_sample"))
    wf = _num(metrics.get("walk_forward"))
    assumptions = list(c.get("assumptions") or [])

    failed, survived, surprises, missing, strengthened, test_next, never_again = \
        [], [], [], [], [], [], []

    # 가정 판정(결정적, 지표 기반)
    if outcome == "FAILURE" or (sharpe is not None and sharpe < 0):
        failed.append("핵심 엣지 가정이 검증에서 붕괴")
        if assumptions:
            failed.append(f"전제: {assumptions[0]}")
        never_again.append("동일 전제·동일 유니버스 재검증(교정 없이) 금지")
    if sharpe is not None and sharpe >= _SHARPE_SUCCESS:
        survived.append(f"엣지 가정 생존 (sharpe={sharpe})")
    if wf is not None and oos is not None:
        if wf > 0 and oos <= 0:
            surprises.append("워크포워드 전반부 양호했으나 OOS 붕괴 — 과적합 신호")
            missing.append("장기 OOS·레짐 밖 검증")
        elif wf > 0 and oos > 0:
            strengthened.append("워크포워드·OOS 양쪽 양호 — 엣지 지속성 강화")
    if "cost_impact" not in metrics:
        missing.append("비용 스트레스(cost_impact) 검증 누락")
    if "random_baseline" not in metrics:
        missing.append("랜덤 베이스라인 대비 검정 누락")

    # 다음 테스트 제안
    if surprises:
        test_next.append("레짐 조건부 필터를 붙인 변형 재검증")
    if missing:
        test_next.append("누락 검증(비용·랜덤·장기 OOS) 보강 후 재판정")
    if not (failed or survived):
        test_next.append("지표 불충분 — 완전한 검증 세트로 재실행")

    return failed, survived, surprises, missing, strengthened, test_next, never_again


def _reflect_from_ledger():
    """사이클 미제공 시 — 수집 요약에서 조직 수준 성찰(읽기전용)."""
    s = _safe(lambda: __import__("jarvis.research_ingestion.engine",
                                 fromlist=["ResearchIngestionEngine"]
                                 ).ResearchIngestionEngine().summary(), None)
    by = (getattr(s, "by_outcome", None) or {}) if s else {}
    cat = (getattr(s, "by_failure_category", None) or {}) if s else {}
    failed = [f"{cat[k]}건 {k}" for k in sorted(cat, key=lambda x: -cat[x])[:3]]
    survived = [f"{by.get('SUCCESS', 0)}건 성공 결론 생존"] if by.get("SUCCESS") else []
    missing = ["다수 실험이 INCOMPLETE — 검증 세트 불완전"] if by.get("INCOMPLETE") else []
    test_next = ["INCOMPLETE 실험의 누락 검증 보강"] if by.get("INCOMPLETE") else []
    never_again = ["반복 실패 카테고리의 무교정 재검증 금지"] if cat else []
    surprises, strengthened = [], []
    return failed, survived, surprises, missing, strengthened, test_next, never_again


def reflect_on_cycle(cycle: dict | None = None, *, now: str = "", commit: bool = False) -> dict:
    """완료 사이클(또는 원장) → 구조화된 성찰 + (선택)기존 메모리에 교훈 저장. 결정적·읽기전용.

    commit=True 시 learning_engine(기존 rmi_ 원장)로 교훈 저장 — 새 메모리 시스템 없음.
    """
    if cycle:
        failed, survived, surprises, missing, strengthened, test_next, never_again = \
            _reflect_from_cycle(cycle)
        scope = "cycle"
    else:
        failed, survived, surprises, missing, strengthened, test_next, never_again = \
            _reflect_from_ledger()
        scope = "ledger"

    reflection = {
        "assumptions_failed": failed, "assumptions_survived": survived,
        "surprises": surprises, "missing_evidence": missing,
        "strengthened_evidence": strengthened, "test_next": test_next,
        "never_test_again": never_again}

    # 교훈 저장 — 기존 메모리 인프라만(learning_engine → rmi_)
    stored = "none"
    if commit and (failed or survived or missing):
        def _store():
            from jarvis.research_workflow.learning_engine import learn
            lesson_outcome = "FAILURE" if failed else ("SUCCESS" if survived else "INCOMPLETE")
            learn(backtest=(cycle or {}).get("backtest"), outcome=lesson_outcome,
                  now=now, commit=True)
            return "learning_engine(rmi_)"
        stored = _safe(_store, "none")

    return {"scope": scope, "reflection": reflection,
            "questions": ["assumptions_failed", "assumptions_survived", "surprises",
                          "missing_evidence", "strengthened_evidence", "test_next",
                          "never_test_again"],
            "lessons_stored_via": stored,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Self Reflection(읽기전용) — 완료 사이클 성찰 + 기존 메모리에 교훈 저장. "
                     "새 메모리 시스템 없음. 자문 전용. 사람이 모든 결정.")}
