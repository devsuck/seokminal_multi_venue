"""Research Ledger Backfill Runbook (P171-ops) — 기존 실험 이력을 연구 메모리로 흘려보내는 **재실행 가능한 룬북**. **실행 없음.**

목적(문서 §Constitution — Integration over Expansion / §P170 Future Guidance = operations·data quality):
  기존 트레이딩 플랫폼의 **실제 실험 이력**(research.agents.experiment_registry)을 읽어, 이미 존재하는 P53
  수집 파이프라인(ResearchIngestionEngine → expt_/rmi_/ring_ 원장)으로 흘려보낸다. 그 결과 Research OS 의
  lifecycle·knowledge-graph·failure-intelligence·recall 이 **실데이터**로 채워진다.

핵심 원칙:
  · **새 저장소/새 엔진 없음.** 기존 registry(읽기) + 기존 ResearchIngestionEngine(쓰기)만 재사용.
  · **계산·해석 없음, 충실한 매핑만.** 각 실험의 **실제 status/verdict** 를 연구-메모리 결과로 번역할 뿐,
    새 판정을 만들지 않는다(수치 조작·지표 날조 금지). 없는 검증지표는 정직하게 비운다(UNKNOWN).
  · **멱등.** 동일 실험 재수집은 no-op(P53 backtest_hash 기반 중복탐지). 안전하게 반복 실행 가능.
  · **결정적.** 동일 입력 → 동일 출력(실험의 자기 timestamp 를 감사시각으로 사용).
  · 거래·집행·배포·자본배분 없음. 산출은 자문(is_advisory). 사람 판단은 항상 필수.

중복 축소 규칙(정직·비임의): 전략별로 **distinct verdict 당 최신 1건**만 채택 —
  자동스캔의 반복 로깅(예: auto_fac_* 158회 동일 verdict)은 1건으로 접히고, 실제 반복 실험(서로 다른
  verdict)은 각각 보존된다. 잘라낸 건수는 로그로 명시(무언 절삭 금지).

사용:
  python -m jarvis.research_workflow.backfill            # 드라이런(원장 무변경, 미리보기)
  python -m jarvis.research_workflow.backfill --commit   # 기존 원장에 수집(멱등)
"""
from __future__ import annotations

# 실험의 **실제** status(원본 연구 결론) → 연구-메모리 결과(P53 OUTCOMES). 충실한 번역, 새 판정 아님.
#   FAILURE  = 원본이 이미 부정 결론(rejected/무효과/음의 드리프트) — 실패 지능에 보존(교훈 가치 최상).
#   SUCCESS  = 원본이 검증 통과해 paper 후보로 승격 — 성공 메모리에 보존(투자 승인 아님, 연구 성과).
#   PARTIAL  = 후보/그림자 — 실험/결과는 기록하되 성공·실패 메모리는 만들지 않음(미확정).
#   INCOMPLETE = 약함/저검정력/판정불가/데이터차단 — 실험만 기록(정직한 미완).
STATUS_OUTCOME = {
    "rejected": "FAILURE", "no_effect": "FAILURE", "research_negative_drift": "FAILURE",
    "paper_candidate": "SUCCESS", "paper_candidate_forward_test_required": "SUCCESS",
    "paper_candidate_yellow": "SUCCESS",
    "candidate": "PARTIAL", "v2_shadow": "PARTIAL", "watchlist": "PARTIAL",
    "weak": "INCOMPLETE", "underpowered": "INCOMPLETE", "inconclusive": "INCOMPLETE",
    "blocked_by_data": "INCOMPLETE", "analysis": "INCOMPLETE",
}

# 원본 실험 필드 → P53 표준 검증지표 이름(별칭 우선순위). 순수 매핑 — 값 계산 없음.
_METRIC_MAP = (
    ("sharpe", ("sharpe",)),
    ("return", ("ann_return", "mean_return")),
    ("max_drawdown", ("max_drawdown", "mdd")),
    ("walk_forward", ("wf_first", "wf_first_sharpe")),
    ("out_of_sample", ("wf_second", "wf_second_sharpe")),
    ("random_baseline", ("random_percentile", "random_pct", "percentile")),
    # 필수는 아니나 신호가 풍부한 원본 지표(감사·판정 보조)
    ("empirical_p", ("p", "p_taker", "empirical_p")),
    ("net", ("net", "net_pnl", "net_base")),
)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _metrics(row: dict) -> dict:
    """원본 실험 row → 표준 지표 dict. 없는 값은 담지 않는다(정직한 결측)."""
    out: dict = {}
    for std, aliases in _METRIC_MAP:
        for a in aliases:
            if a in row and row[a] is not None:
                num = _num(row[a])
                if num is not None:
                    out[std] = num
                    break
    if row.get("regime_dependent") is True:
        out["regime_dependent"] = True
    return out


def _schema(strategy_id: str, row: dict) -> dict:
    """원본 실험 row → P53 research_ingestion 스키마. 실제 status→outcome + verdict/note 보존."""
    status = str(row.get("status", "")).strip().lower()
    outcome = STATUS_OUTCOME.get(status, "INCOMPLETE")
    verdict = str(row.get("verdict", "") or "").strip()
    note = str(row.get("note", "") or "").strip()
    schema = {
        "strategy_name": strategy_id,
        "strategy_version": str(row.get("hypothesis_id", "") or ""),
        "hypothesis": note or verdict,
        "universe": str(row.get("data_quality", "") or ""),
        "metrics": _metrics(row),
        "outcome": outcome,
        "source": "registry_experiment_backfill",
    }
    # 실패의 원인·교훈 = 원본 연구 결론(한글 노트가 실패지능의 핵심 자산). 날조하지 않고 원문 보존.
    if outcome == "FAILURE":
        schema["root_cause"] = verdict or note
        schema["lesson"] = note or verdict
    elif outcome == "SUCCESS" and (verdict or note):
        schema["lesson"] = verdict or note
    return schema


def _distinct_by_verdict(rows: list) -> list:
    """전략의 실험들 중 distinct verdict 당 최신 1건만 채택(반복 로깅 축소, 실제 반복 보존)."""
    by_verdict: dict = {}
    for e in rows or []:            # rows 는 시간순 → 나중 값이 최신
        by_verdict[str(e.get("verdict"))] = e
    return list(by_verdict.values())


def _strategy_ids() -> list:
    """registry 의 모든 전략 id(현재 상태 스냅샷). 읽기전용."""
    try:
        from jarvis.registry import StrategyRegistry
        return sorted({s["strategy_id"] for s in StrategyRegistry().all_current()})
    except Exception:  # noqa: BLE001
        return []


def _experiments(strategy_id: str) -> list:
    """전략의 실제 실험 이력(불변). research.agents.experiment_registry 재사용. 읽기전용."""
    try:
        from research.agents.experiment_registry import already_tested
        return already_tested(strategy_id) or []
    except Exception:  # noqa: BLE001
        return []


def plan() -> dict:
    """드라이런 미리보기 — 무엇을 어떤 결과로 수집할지(원장 무변경). 결정적·읽기전용."""
    strategies = _strategy_ids()
    records, dropped = [], 0
    by_outcome: dict = {}
    for sid in strategies:
        raw = _experiments(sid)
        kept = _distinct_by_verdict(raw)
        dropped += max(0, len(raw) - len(kept))
        for e in kept:
            s = _schema(sid, e)
            by_outcome[s["outcome"]] = by_outcome.get(s["outcome"], 0) + 1
            records.append({"strategy": sid, "verdict": str(e.get("verdict", ""))[:80],
                            "status": e.get("status", ""), "outcome": s["outcome"],
                            "metrics": sorted(s["metrics"].keys())})
    return {"strategies_scanned": len(strategies),
            "strategies_with_data": len({r["strategy"] for r in records}),
            "records_to_ingest": len(records),
            "rows_collapsed_by_verdict_dedup": dropped,
            "by_outcome": dict(sorted(by_outcome.items())),
            "records": records,
            "is_advisory": True, "is_decision": False,
            "note": ("Backfill 드라이런(읽기전용) — 기존 실험 이력 → 연구 메모리 매핑 미리보기. "
                     "commit=False 이므로 원장 무변경. 자동 투자 행위 없음, 새 원장 없음.")}


def run_backfill(*, commit: bool = False, engine=None) -> dict:
    """기존 실험 이력을 연구 메모리로 수집. 멱등·결정적. commit=False=드라이런.

    실행/집행/배포 없음. 기존 ResearchIngestionEngine + 기존 원장만 사용(새 원장 없음).
    """
    if engine is None:
        from jarvis.research_ingestion.engine import ResearchIngestionEngine
        engine = ResearchIngestionEngine()

    strategies = _strategy_ids()
    ingested, deduped, dropped = 0, 0, 0
    by_outcome: dict = {}
    memory: dict = {}
    for sid in strategies:
        raw = _experiments(sid)
        kept = _distinct_by_verdict(raw)
        dropped += max(0, len(raw) - len(kept))
        for e in kept:
            schema = _schema(sid, e)
            # 실험 자기 timestamp 를 감사시각으로(충실·결정적). backtest_hash 에는 미포함 → 멱등 보존.
            now = str(e.get("timestamp", "") or "")
            res = engine.ingest(schema, now, commit=commit)
            by_outcome[res.outcome] = by_outcome.get(res.outcome, 0) + 1
            if res.memory_written and res.memory_written != "none":
                memory[res.memory_written] = memory.get(res.memory_written, 0) + 1
            if res.deduplicated:
                deduped += 1
            else:
                ingested += 1
    return {"committed": bool(commit),
            "strategies_scanned": len(strategies),
            "records_ingested": ingested,
            "records_deduplicated": deduped,
            "rows_collapsed_by_verdict_dedup": dropped,
            "by_outcome": dict(sorted(by_outcome.items())),
            "memory_written": dict(sorted(memory.items())),
            "is_advisory": True, "is_decision": False,
            "note": ("Backfill 실행(멱등) — 기존 실험 이력 → 기존 연구 원장(expt_/rmi_/ring_). "
                     "재실행 안전(중복 no-op). 거래·집행·배포 없음. 사람 판단 필수.")}


def sync() -> dict:
    """자동 동기화 진입점 — 기존 실험 이력을 연구 원장에 멱등 반영(신규분만 추가). **실행 없음.**

    스케줄러/cron/사람이 반복 호출해도 안전(멱등). 이것이 '데이터가 쌓이면 자동으로 연구 OS 에
    반영된다'의 단일 진입점이다. 새 백테스트가 experiment_registry 에 추가되면 다음 sync 에서만 흡수된다.
    """
    return run_backfill(commit=True)


def main(argv=None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="jarvis.research_workflow.backfill",
                                 description="기존 실험 이력 → 연구 메모리 멱등 백필(실행 없음, 자문 전용).")
    ap.add_argument("--commit", action="store_true",
                    help="기존 원장에 수집(생략 시 드라이런 미리보기)")
    args = ap.parse_args(argv)
    if args.commit:
        out = run_backfill(commit=True)
    else:
        p = plan()
        out = {k: v for k, v in p.items() if k != "records"}
        out["sample_records"] = p["records"][:12]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
