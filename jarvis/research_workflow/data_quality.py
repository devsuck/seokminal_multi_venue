"""Data Quality Operations (P118) — 데이터 소스 상태를 감시한다. **읽기 전용, 새 저장소 없음.**

DataQualityMonitor 점검: API availability·data freshness·schema changes·missing values·abnormal values.
산출: DataHealthReport. Executive Cockpit 에 통합. **재사용**: providers.provider_registry(P112)·
market_data.quality.assess_series(freshness/missing/abnormal, 기존)·market_data.models.hours_between.

원칙(문서 §Constitution, §P118): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

_STALE_HOURS = 48.0
_EXPECTED_SCHEMA = {"asset", "timestamp"}     # 최소 스키마(정규화 입력)


def _series_health(source: str, bars: list, now: str) -> dict:
    """단일 시계열 품질(freshness/missing/abnormal) — 기존 market_data.quality 재사용."""
    try:
        from jarvis.market_data.quality import assess_series
        rep = assess_series(source, bars or [], now, stale_hours=_STALE_HOURS)
        d = rep.to_dict() if hasattr(rep, "to_dict") else dict(rep)
        return {"source": source, "n_bars": d.get("n_bars", len(bars or [])),
                "quality_score": d.get("quality_score"), "issues": d.get("issues", []),
                "checks": d.get("checks", {})}
    except Exception as e:  # noqa: BLE001
        return {"source": source, "n_bars": len(bars or []), "issues": [{"type": "assess_error",
                "detail": str(e)}], "checks": {}}


def _schema_check(rows: list) -> dict:
    """스키마 변화/누락 필드 감지(결정적) — 정규화 최소 스키마 기준."""
    if not rows:
        return {"ok": True, "missing_fields": [], "checked": 0}
    keys = set()
    for r in rows[:50]:
        if isinstance(r, dict):
            keys |= set(r)
    missing = sorted(f for f in _EXPECTED_SCHEMA if not any(
        f in r or ("symbol" if f == "asset" else f) in r for r in rows[:50] if isinstance(r, dict)))
    return {"ok": not missing, "missing_fields": missing, "checked": len(rows)}


def build_data_health(series_by_source: dict | None = None, *, rows_by_source: dict | None = None,
                      now: str = "") -> dict:
    """DataHealthReport(읽기전용) — provider availability + freshness/missing/abnormal + schema. 결정적.

    series_by_source: {source: [OHLCVBar-like]} 주면 freshness/abnormal 점검.
    rows_by_source: {source: [raw dict]} 주면 스키마/누락 점검. 없으면 availability 만.
    """
    from jarvis.research_workflow.providers import provider_registry
    reg = provider_registry()
    providers = reg["providers"]
    available = [p for p in providers if p["available"]]
    unavailable = [p for p in providers if not p["available"]]

    series_reports = [_series_health(s, bars, now) for s, bars in (series_by_source or {}).items()]
    schema_reports = {s: _schema_check(rows) for s, rows in (rows_by_source or {}).items()}

    # 종합 상태
    n_issues = sum(len(r.get("issues", [])) for r in series_reports) + \
        sum(0 if v["ok"] else 1 for v in schema_reports.values())
    avail_ratio = round(len(available) / len(providers), 3) if providers else 0.0
    status = ("HEALTHY" if (avail_ratio >= 0.5 and n_issues == 0) else
              "DEGRADED" if avail_ratio >= 0.25 else "LIMITED")
    return {"generated_at": now or "", "overall_status": status,
            "api_availability": {"available": len(available), "total": len(providers),
                                 "ratio": avail_ratio,
                                 "unavailable": [p["name"] for p in unavailable]},
            "by_category": reg["by_category"],
            "freshness_and_values": series_reports,
            "schema_checks": schema_reports,
            "issue_count": n_issues,
            "checks": ["api_availability", "data_freshness", "schema_changes", "missing_values",
                       "abnormal_values"],
            "missing_integrations": reg["missing_integrations"],
            "is_advisory": True, "is_decision": False,
            "note": ("DataHealthReport(읽기전용) — provider availability + 기존 market_data.quality "
                     "재사용(freshness/missing/abnormal). 새 저장소 없음, 거래·집행 없음.")}


class DataQualityMonitor:
    """데이터 품질 모니터 — build_data_health 래퍼(클래스 형태 API)."""

    def report(self, series_by_source: dict | None = None, *, rows_by_source: dict | None = None,
               now: str = "") -> dict:
        return build_data_health(series_by_source, rows_by_source=rows_by_source, now=now)
