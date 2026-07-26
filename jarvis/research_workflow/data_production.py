"""Data Production Intelligence (P151) — 기존 provider 통합을 **생산급 인텔리전스 모니터링**으로. **읽기 전용.**

기존 통합을 재사용해 API health·data freshness·schema consistency·missing data·source reliability 를 감시한다.
**재사용**: providers(P112)·data_quality(P118)·market/news/fundamental/ownership pipeline(P113-116).
출력: DataProductionReport {provider, source, availability, freshness, quality_score, failure_reason, lineage}.
**데이터 변형 없음**(no mutation). 새 저장소 없음.

원칙(문서 §Constitution, §P151): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def build_data_production(*, series_by_source: dict | None = None) -> dict:
    """DataProductionReport(읽기전용) — provider별 availability·freshness·quality·lineage. 데이터 변형 없음."""
    reg = _safe(lambda: __import__("jarvis.research_workflow.providers", fromlist=["provider_registry"])
                .provider_registry(), {"providers": []}) or {}
    health = _safe(lambda: __import__("jarvis.research_workflow.data_quality",
                                      fromlist=["build_data_health"])
                   .build_data_health(series_by_source or {}), {"freshness_and_values": []}) or {}

    # 소스별 freshness/품질(있으면) 매핑
    fresh_by = {r.get("source"): r for r in health.get("freshness_and_values", [])}

    reports = []
    for p in reg.get("providers", []):
        fr = fresh_by.get(p["name"], {})
        n_issues = len(fr.get("issues", []))
        # quality_score: available=+, 이슈=- (결정적 0..1)
        base = 1.0 if p.get("available") else 0.3
        quality = round(max(0.0, base - n_issues * 0.15), 3)
        failure_reason = ("" if p.get("available") else "not configured (no credentials)")
        if n_issues:
            failure_reason = (failure_reason + "; " if failure_reason else "") + \
                f"{n_issues} data issues"
        reports.append({
            "provider": p["name"], "source": p.get("vendor"), "category": p["category"],
            "availability": "available" if p.get("available") else "not_configured",
            "freshness": ("fresh" if fr and n_issues == 0 else "stale/missing" if fr else "unknown"),
            "quality_score": quality,
            "failure_reason": failure_reason,
            "lineage": {"module": p.get("module"), "consumer": p.get("consumer"),
                        "env_key": p.get("env_key") or None},
        })

    n_avail = sum(1 for r in reports if r["availability"] == "available")
    avg_q = round(sum(r["quality_score"] for r in reports) / len(reports), 3) if reports else 0.0
    status = ("HEALTHY" if (n_avail / max(len(reports), 1) >= 0.5 and health.get("issue_count", 0) == 0)
              else "DEGRADED" if n_avail else "LIMITED")
    return {"reports": reports, "count": len(reports), "available_count": n_avail,
            "average_quality": avg_q, "overall_status": status,
            "api_availability": health.get("api_availability", {}),
            "monitored": ["API health", "data freshness", "schema consistency", "missing data",
                          "source reliability"],
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("DataProductionReport(읽기전용) — provider availability·freshness·quality·lineage. "
                     "providers/data_quality/pipeline 재사용. 데이터 변형 없음, 새 저장소 없음.")}
