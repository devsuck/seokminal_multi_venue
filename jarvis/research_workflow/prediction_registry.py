"""Forward Prediction Registry (P201) — 연구 예측을 사전등록·생명주기 관리한다. **기록만, 실행 없음.**

목적: Jarvis 를 "채점받는 연구 조직"으로. 연구 산출 시점의 **믿음을 박제**하고(사후 편향 차단),
horizon 후 결과로 채점한다. 지금은 **기록만** — 평가는 달력 시간 확보 후.

핵심 계약(사용자 P201 확정 7제약):
  1. evaluation_framework 는 strategy_family 에서 **결정적으로 유도**(capturer 가 못 고름 — 골대이동 차단).
  2. 결과 4상태: RIGHT · WRONG · INVALIDATED · INCONCLUSIVE. **INVALIDATED 는 실패 아님**(사전 리스크관리 성공).
  3. **모든 예측 기록**(STRONG 만 아님 — 생존편향 차단). confidence·source·thesis·invalidation·success_rule 저장.
  4. 사전등록: success_rule·evaluation_framework·thresholds 는 capture 후 **불변**(snapshot_hash).
  5. (점수 표시는 P205 — 여기 없음.)
  6. 쓰기는 Writer Authority Protocol(P202) 경유.
  7. **기존 rmi_ 원장만 재사용** — 새 원장/DB/벡터 없음(ALL_LEDGERS==3 유지).

생명주기: PENDING → ACTIVE → EVALUATED(outcome) / INVALIDATED / LEARNED.
원칙(§Constitution): 통합·조율만 · 결정적 · 자문 전용 · 거래·집행 없음 · 사람이 결정.
"""
from __future__ import annotations

import hashlib
import json

# 생명주기 상태
STATES = ("PENDING", "ACTIVE", "EVALUATED", "INVALIDATED", "LEARNED")
# 결과 4분류 — INVALIDATED 는 WRONG 이 아니다(사전 리스크관리 성공)
OUTCOMES = ("RIGHT", "WRONG", "INVALIDATED", "INCONCLUSIVE")
CONFIDENCE = ("HIGH", "MEDIUM", "LOW")
SOURCES = ("committee", "agent", "human_hypothesis", "automatic_discovery")
_DEFAULT_NODE = "local"

# ── Prediction Integrity(Phase 5-F) — capture 품질 분류. state/outcome 과 별개 축, append-only. ──
# LEGACY_CAPTURE: 기록 자체는 유효하나 현재 scoring 기준 이전 데이터.
# INVALIDATED   : capture 과정 오류(source 불명확·규칙 위반 등) — 예측 실패(WRONG)와 무관, 기록 품질 문제.
# RECAPTURED    : thesis 는 유지, capture 만 문제 — supersedes/superseded_by 로 신구 연결.
INTEGRITY_STATUSES = ("LEGACY_CAPTURE", "INVALIDATED", "RECAPTURED")
# Validation Score 대상에서 제외(단, 제외 이유는 append-only 원장에 남음 — 삭제 아님).
SCORE_INELIGIBLE_INTEGRITY = ("LEGACY_CAPTURE", "INVALIDATED", "RECAPTURED")

# strategy_family → 평가 프레임워크(결정적 유도, capturer 선택 불가). 유형별 적정 지표.
EVALUATION_FRAMEWORKS = {
    "momentum": {"framework": "risk_adjusted_vs_baseline", "primary_metric": "sharpe",
                 "thresholds": {"baseline_outperformance": True, "min_sharpe": 0.0}},
    "market_neutral": {"framework": "alpha_tstat", "primary_metric": "alpha_t_stat",
                       "thresholds": {"min_t_stat": 2.0, "baseline_outperformance": True}},
    "event": {"framework": "abnormal_return", "primary_metric": "CAR",
              "thresholds": {"car_positive": True, "max_p_value": 0.05}},
    "factor": {"framework": "information_coefficient", "primary_metric": "IC",
               "thresholds": {"min_ic": 0.02, "decay_acceptable": True}},
    "macro": {"framework": "regime_consistency", "primary_metric": "regime_hit_rate",
              "thresholds": {"min_consistency": 0.6}},
    # 미지/기본 — 절대수익이 아니라 baseline 대비 + 논리 유지
    "_default": {"framework": "baseline_relative", "primary_metric": "baseline_outperformance",
                 "thresholds": {"baseline_outperformance": True, "risk_adjusted_positive": True}},
}
# 최소 채점 표본(P205 게이트와 정합) — 이 미만이면 평가 결과는 신뢰구간 없이 쓰지 말 것
MIN_GRADED_SAMPLE = 20


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _pid(thesis, strategy_id, now):
    return "PRED:" + hashlib.sha1(f"{thesis}|{strategy_id}|{now}".encode()).hexdigest()[:12]


def _snapshot_hash(core: dict) -> str:
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def derive_framework(strategy_family: str) -> dict:
    """strategy_family → evaluation_framework(결정적). capturer 는 못 고른다 — 사전등록 무결성."""
    fam = str(strategy_family or "").strip().lower()
    return dict(EVALUATION_FRAMEWORKS.get(fam, EVALUATION_FRAMEWORKS["_default"]))


def _success_rule(framework: dict) -> dict:
    """사전등록 성공 규칙(불변) — 절대수익 아님. baseline 유지 + 논리 유지 + invalidation 미발생."""
    th = framework.get("thresholds", {})
    return {"require_baseline_outperformance": bool(th.get("baseline_outperformance", True)),
            "require_thesis_held": True,
            "fail_if_invalidation_triggered": True,       # → INVALIDATED(실패 아님)
            "inconclusive_if_insufficient_data": True,    # → INCONCLUSIVE
            "primary_metric": framework.get("primary_metric"),
            "thresholds": dict(th)}


def capture_prediction(*, thesis: str, strategy_id: str = "", strategy_family: str = "",
                       confidence: str = "MEDIUM", source: str = "human_hypothesis",
                       expected_return=None, expected_risk=None, expected_horizon: str = "",
                       invalidation_condition: str = "", evidence_used=None,
                       node_id: str = _DEFAULT_NODE, now: str = "", commit: bool = False) -> dict:
    """연구 예측 1건을 사전등록(불변 스냅샷). **모든 confidence 기록**(STRONG만 아님). 결정적·멱등.

    evaluation_framework·success_rule·thresholds 는 capture 시점 동결 → 사후 편향 차단.
    저장은 기존 rmi_ 원장(record_lesson, impact='prediction') 재사용 — 새 원장 없음. Writer Authority 경유.
    """
    conf = str(confidence or "MEDIUM").upper()
    conf = conf if conf in CONFIDENCE else "MEDIUM"
    src = str(source or "human_hypothesis")
    src = src if src in SOURCES else "human_hypothesis"
    framework = derive_framework(strategy_family)      # ★ 결정적 유도(선택 불가)
    success_rule = _success_rule(framework)

    core = {"thesis": thesis, "strategy_id": strategy_id,
            "strategy_family": str(strategy_family or "").lower(),
            "confidence": conf, "source": src,
            "expected_return": expected_return, "expected_risk": expected_risk,
            "expected_horizon": expected_horizon,
            "invalidation_condition": invalidation_condition,
            "evidence_used": list(evidence_used or []),
            "evaluation_framework": framework, "success_rule": success_rule}
    pid = _pid(thesis, strategy_id, now)
    snapshot = {"prediction_id": pid, **core, "captured_at": now, "state": "PENDING",
                "outcome": None, "snapshot_hash": _snapshot_hash(core),
                "immutable_fields": ["evaluation_framework", "success_rule", "thresholds",
                                     "thesis", "invalidation_condition"],
                "requires_human_review": True, "is_advisory": True, "is_decision": False}

    written = "preview"
    if commit:
        written = _persist(pid, thesis, snapshot, impact="prediction", node_id=node_id, now=now)
    return {**snapshot, "persisted": written,
            "note": ("Forward Prediction(사전등록) — 믿음·성공규칙·프레임워크 박제(불변). 모든 예측 기록. "
                     "지금은 기록만, 평가는 horizon 후. 기존 rmi_ 재사용, 새 원장 없음. 사람이 결정.")}


def transition(prediction_id: str, to_state: str, *, outcome: str = "", reason: str = "",
               node_id: str = _DEFAULT_NODE, now: str = "", commit: bool = False) -> dict:
    """생명주기 전이(append-only). PENDING→ACTIVE→EVALUATED/INVALIDATED/LEARNED. 원 스냅샷 불변."""
    st = str(to_state or "").upper()
    if st not in STATES:
        return {"error": f"unknown state: {to_state}", "states": list(STATES), "is_decision": False}
    oc = str(outcome or "").upper()
    if oc and oc not in OUTCOMES:
        return {"error": f"unknown outcome: {outcome}", "outcomes": list(OUTCOMES), "is_decision": False}
    rec = {"prediction_id": prediction_id, "to_state": st, "outcome": oc or None,
           "reason": reason, "at": now,
           # INVALIDATED 는 실패가 아니라 사전 리스크관리 성공임을 명시
           "invalidated_is_not_failure": (oc == "INVALIDATED"),
           "requires_human_review": True, "is_advisory": True, "is_decision": False}
    written = "preview"
    if commit:
        written = _persist(prediction_id, f"transition→{st}", rec, impact="prediction_transition",
                           node_id=node_id, now=now)
    return {**rec, "persisted": written}


def set_integrity_status(prediction_id: str, integrity_status: str, *, reason: str = "",
                         supersedes: str = "", superseded_by: str = "",
                         node_id: str = _DEFAULT_NODE, now: str = "", commit: bool = False) -> dict:
    """Prediction capture 품질 분류(Phase 5-F, append-only). 원본 스냅샷 필드는 **절대 수정하지 않음**.

    LEGACY_CAPTURE/INVALIDATED/RECAPTURED 중 하나만. state/outcome 생명주기와 별개 축 —
    이미 EVALUATED 된 예측이라도 capture 품질 문제는 독립적으로 기록 가능(과거를 안 건드리고 상태만 추가).
    """
    st = str(integrity_status or "").upper()
    if st not in INTEGRITY_STATUSES:
        return {"error": f"unknown integrity_status: {integrity_status}",
                "integrity_statuses": list(INTEGRITY_STATUSES), "is_decision": False}
    rec = {"prediction_id": prediction_id, "integrity_status": st, "reason": reason,
           "supersedes": supersedes or None, "superseded_by": superseded_by or None, "at": now,
           "score_eligible": st not in SCORE_INELIGIBLE_INTEGRITY,
           "requires_human_review": True, "is_advisory": True, "is_decision": False}
    written = "preview"
    if commit:
        written = _persist(prediction_id, f"integrity→{st}", rec, impact="prediction_integrity",
                           node_id=node_id, now=now)
    return {**rec, "persisted": written,
            "note": ("Prediction Integrity(Phase 5-F) — capture 품질만 분류, 원 스냅샷 불변. "
                     "INVALIDATED≠예측실패(WRONG). 기존 rmi_ 재사용, 새 원장 없음. 사람이 결정.")}


def evaluate(prediction_id: str, forward_result: dict, *, node_id: str = _DEFAULT_NODE,
             now: str = "", commit: bool = False) -> dict:
    """동결된 success_rule 로 결정적 채점 → RIGHT/WRONG/INVALIDATED/INCONCLUSIVE. (달력 시간 후 호출.)

    사후 편향 차단: 규칙은 capture 시점 것만 사용(여기서 새로 정하지 않음). INVALIDATED≠WRONG.
    """
    snap = get_prediction(prediction_id)
    if not snap:
        return {"error": "prediction not found", "prediction_id": prediction_id, "is_decision": False}
    rule = snap.get("success_rule", {})
    fr = forward_result or {}

    # 1) invalidation 발동 → INVALIDATED(실패 아님)
    if fr.get("invalidation_triggered") is True:
        outcome = "INVALIDATED"
    # 2) 데이터/표본/기간 부족 → INCONCLUSIVE
    elif fr.get("insufficient_data") is True or fr.get("sample_ok") is False:
        outcome = "INCONCLUSIVE"
    else:
        baseline_ok = (not rule.get("require_baseline_outperformance")) or bool(fr.get("baseline_outperformance"))
        thesis_ok = (not rule.get("require_thesis_held")) or bool(fr.get("thesis_held", True))
        outcome = "RIGHT" if (baseline_ok and thesis_ok) else "WRONG"

    to_state = "INVALIDATED" if outcome == "INVALIDATED" else "EVALUATED"
    res = transition(prediction_id, to_state, outcome=outcome,
                     reason=f"evaluated via frozen rule ({rule.get('primary_metric')})",
                     node_id=node_id, now=now, commit=commit)
    return {"prediction_id": prediction_id, "outcome": outcome,
            "invalidated_is_not_failure": (outcome == "INVALIDATED"),
            "used_frozen_rule": True, "transition": res,
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("동결된 success_rule 로 채점 — 사후 편향 없음. INVALIDATED 는 사전 리스크관리 성공(실패 아님). "
                     "INCONCLUSIVE 는 데이터/기간 부족(실패 아님). 사람이 최종 해석.")}


# ── 읽기(기존 rmi_ 원장에서) ──
def _prediction_records(impact: str) -> list:
    def _go():
        from jarvis.research_memory_intelligence import ledger as ml
        return [r for r in (ml.read_lessons() or []) if str(r.get("impact")) == impact]
    return _safe(_go, []) or []


def get_prediction(prediction_id: str) -> dict | None:
    for r in _prediction_records("prediction"):
        ev = r.get("evidence") or {}
        if ev.get("prediction_id") == prediction_id:
            return ev
    return None


def list_predictions() -> list:
    return [r.get("evidence") or {} for r in _prediction_records("prediction")]


def _latest_outcomes() -> tuple:
    """전이 원장에서 예측별 최신 상태·결과 추출(append-only 재구성)."""
    transitions = [r.get("evidence") or {} for r in _prediction_records("prediction_transition")]
    latest_state: dict = {}
    latest_outcome: dict = {}
    for t in transitions:
        pid = t.get("prediction_id")
        if not pid:
            continue
        latest_state[pid] = t.get("to_state") or latest_state.get(pid)
        if t.get("outcome"):
            latest_outcome[pid] = t.get("outcome")
    return latest_state, latest_outcome


def _latest_integrity() -> dict:
    """무결성 원장에서 예측별 최신 integrity_status 추출(append-only 재구성). 기록 없으면 미분류(=정상)."""
    recs = [r.get("evidence") or {} for r in _prediction_records("prediction_integrity")]
    latest: dict = {}
    for r in recs:
        pid = r.get("prediction_id")
        if pid:
            latest[pid] = r
    return latest


def graded_predictions(*, include_score_ineligible: bool = False) -> list:
    """평가 완료된 예측 [{prediction_id, confidence, source, outcome, score_eligible}] — P204.5/P205 입력.

    기본적으로 Score Eligibility Gate(Phase 5-F) 적용 — capture 무결성 문제(LEGACY_CAPTURE/INVALIDATED/
    RECAPTURED)로 분류된 예측은 채점 집계에서 제외(레지스트리 행 자체는 그대로 보존, 삭제 아님).
    include_score_ineligible=True 로 감사용 전체 목록 조회 가능. 읽기전용.
    """
    _, latest_outcome = _latest_outcomes()
    latest_integrity = _latest_integrity()
    out = []
    for p in list_predictions():
        pid = p.get("prediction_id")
        oc = latest_outcome.get(pid)
        if not oc:
            continue
        ig = latest_integrity.get(pid)
        eligible = ig.get("score_eligible", True) if ig else True
        if not eligible and not include_score_ineligible:
            continue
        out.append({"prediction_id": pid, "confidence": p.get("confidence"),
                    "source": p.get("source"), "outcome": oc,
                    "strategy_family": p.get("strategy_family"),
                    "score_eligible": eligible,
                    "integrity_status": ig.get("integrity_status") if ig else None})
    return out


def registry_status() -> dict:
    """예측 레지스트리 현황 — 상태/결과/confidence/source 분포. 생존편향 방지: graded vs pending 명시."""
    preds = list_predictions()
    transitions = [r.get("evidence") or {} for r in _prediction_records("prediction_transition")]
    latest_outcome: dict = {}
    latest_state: dict = {}
    for t in transitions:
        pid = t.get("prediction_id")
        if not pid:
            continue
        latest_state[pid] = t.get("to_state") or latest_state.get(pid)
        if t.get("outcome"):
            latest_outcome[pid] = t.get("outcome")

    latest_integrity = _latest_integrity()
    by_conf: dict = {}
    by_source: dict = {}
    by_state: dict = {}
    by_outcome: dict = {}
    by_integrity: dict = {}
    excluded_from_score = 0
    for p in preds:
        pid = p.get("prediction_id")
        by_conf[p.get("confidence", "?")] = by_conf.get(p.get("confidence", "?"), 0) + 1
        by_source[p.get("source", "?")] = by_source.get(p.get("source", "?"), 0) + 1
        st = latest_state.get(pid, p.get("state", "PENDING"))
        by_state[st] = by_state.get(st, 0) + 1
        ig = latest_integrity.get(pid)
        ig_label = ig.get("integrity_status") if ig else "VALID"
        by_integrity[ig_label] = by_integrity.get(ig_label, 0) + 1
        oc = latest_outcome.get(pid)
        if oc:
            eligible = ig.get("score_eligible", True) if ig else True
            if eligible:
                by_outcome[oc] = by_outcome.get(oc, 0) + 1
            else:
                excluded_from_score += 1

    graded = sum(by_outcome.values())
    # INVALIDATED/INCONCLUSIVE 는 RIGHT/WRONG 채점 대상에서 분리(정직). capture 무결성 제외분은 excluded_from_score.
    scorable = by_outcome.get("RIGHT", 0) + by_outcome.get("WRONG", 0)
    return {"total_predictions": len(preds),
            "by_confidence": dict(sorted(by_conf.items())),
            "by_source": dict(sorted(by_source.items())),
            "by_state": dict(sorted(by_state.items())),
            "by_outcome": dict(sorted(by_outcome.items())),
            "by_integrity": dict(sorted(by_integrity.items())),
            "excluded_from_score_capture_integrity": excluded_from_score,
            "graded": graded, "scorable_right_wrong": scorable, "pending": len(preds) - graded,
            "sufficient_sample_for_score": scorable >= MIN_GRADED_SAMPLE,
            "min_graded_sample": MIN_GRADED_SAMPLE,
            "captures_all_confidence": True,  # STRONG만 아님 — 생존편향 차단
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Prediction Registry 현황(읽기전용) — 모든 예측 기록(생존편향 차단). "
                     "INVALIDATED/INCONCLUSIVE 는 RIGHT/WRONG 과 분리. capture 무결성(LEGACY_CAPTURE/"
                     "INVALIDATED/RECAPTURED) 문제 예측은 excluded_from_score_capture_integrity 로 분리 집계"
                     "(제외 이유는 prediction_integrity 원장에 append-only 로 남음, 삭제 아님). "
                     "graded<20 이면 점수 미표시(P205). 기존 rmi_ 재사용, 새 원장 없음.")}


def _persist(origin: str, summary: str, payload: dict, *, impact: str, node_id: str, now: str):
    """Writer Authority 경유 → 기존 rmi_ 원장(record_lesson)에 append. 새 원장 없음."""
    def _append():
        from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
        eng = ResearchMemoryIntelligenceEngine()
        rec = eng.record_lesson(origin=origin, lesson=summary, evidence=payload,
                                impact=impact, now=now, commit=True)
        return rec.to_dict() if hasattr(rec, "to_dict") else str(rec)

    from jarvis.research_workflow.ledger_writer import WriterAuthority
    wa = WriterAuthority()
    # 단일 사용자 기본: 유효 리스 없으면 자동 획득(다른 노드가 잡고 있으면 거부됨)
    if not wa.has_authority(node_id, now=now):
        acq = wa.acquire(node_id, now=now)
        if acq.get("rejected"):
            return {"rejected": True, "reason": acq.get("reason")}
    guarded = wa.guarded_append(node_id, _append, now=now)
    return guarded.get("result") if not guarded.get("rejected") else {"rejected": True}
