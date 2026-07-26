"""Operational Metrics (P167) — 운영 효율 지표를 측정한다. **읽기 전용, 결정적.**

측정: research throughput·research latency·agent utilization·API availability·data freshness·
research completion·review backlog. 출력: OperationalMetricsReport. **재사용**: 기존 원장 읽기(rwf/ring/rmi/expt)·
data_production(P151)·ops_events(P107). 새 저장소 없음. 목적: 운영 효율 개선(사람 판단).

원칙(문서 §Constitution, §P167): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations


def _read(mod, fn):
    try:
        m = __import__(mod, fromlist=[fn])
        return list(getattr(m, fn)() or [])
    except Exception:  # noqa: BLE001
        return []


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_operational_metrics() -> dict:
    """OperationalMetricsReport(읽기전용) — 처리량·지연·활용·가용성·신선도·완료·백로그. 결정적."""
    # 처리량 — 완료된 연구(ring_ingestions) + 실험(expt_runs)
    ingestions = _read("jarvis.research_ingestion.ledger", "read_ingestions")
    expt_runs = _read("jarvis.experiment_tracking.ledger", "read_runs")
    loops = _read("jarvis.research_workflow.ledger", "read_loops")
    runs = _read("jarvis.research_workflow.ledger", "read_runs")

    # 연구 완료율 — SUCCESS/전체
    outcomes = [str(r.get("outcome", "")).upper() for r in ingestions]
    completed = sum(1 for o in outcomes if o in ("SUCCESS", "PARTIAL"))
    completion_rate = round(completed / len(outcomes), 3) if outcomes else None

    # API 가용성 + 데이터 신선도 — data_production
    dp = _safe(lambda: __import__("jarvis.research_workflow.data_production",
                                  fromlist=["build_data_production"]).build_data_production(), {})
    api_availability = (round(dp.get("available_count", 0) / max(dp.get("count", 1), 1), 3) if dp else None)
    data_freshness = dp.get("overall_status") if dp else "UNKNOWN"

    # 리뷰 백로그 — ops_events review_queue
    ops = _safe(lambda: __import__("jarvis.research_workflow.ops_events", fromlist=["ops_events"])
                .ops_events(), {"review_queue": []})
    review_backlog = len(ops.get("review_queue", []))

    # 에이전트 활용(근사) — 워크플로 실행 대비 에이전트 역할 수
    n_agents = _safe(lambda: __import__("jarvis.research_workflow.agent_capability",
                                        fromlist=["capability_map"]).capability_map().get("count", 6), 6)

    return {"metrics": {
                "research_throughput": {"ingestions": len(ingestions), "experiment_runs": len(expt_runs),
                                        "loops": len(loops)},
                "research_latency": {"note": "타임스탬프 기반 지연 — 원장 이벤트 간격(데이터 축적 시 산출)",
                                     "workflow_events": len(runs)},
                "agent_utilization": {"agents": n_agents, "workflow_runs": len(runs),
                                      "note": "활용도 = 실행/에이전트(축적 시 정밀화)"},
                "api_availability": api_availability,
                "data_freshness": data_freshness,
                "research_completion": {"rate": completion_rate, "completed": completed,
                                        "total": len(outcomes)},
                "review_backlog": review_backlog,
            },
            "report_type": "OperationalMetricsReport",
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("OperationalMetricsReport(읽기전용) — 처리량·지연·활용·가용성·신선도·완료·백로그. "
                     "기존 원장/모니터 재사용, 새 저장소 없음. 운영 효율 개선용.")}
