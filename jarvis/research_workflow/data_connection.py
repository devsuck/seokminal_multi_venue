"""Data Connection Layer (P206-data) — 프로토타입 데이터를 **기관급**으로. **데이터만 개선, 지능 추가 없음.**

깊이 우선(폭 아님). 우선순위 소스: KRX · OpenDART · SEC EDGAR. **기존 provider 추상화(P112) 재사용** —
중복 provider 없음. jarvis 는 자격증명 없음(Constitution) → 실제 API 호출은 기존 Layer A 클라이언트가
raw 를 주입(dependency injection). 키/데이터 없으면 **정직하게 NEEDS_CREDENTIALS/UNKNOWN**(가짜 없음).

8개 목표: availability · freshness · schema validation · retry · backfill · gap detection · lineage ·
quality scoring. 연결된 각 소스는 **availability·freshness·quality·lineage** 를 노출. UNKNOWN 은 점진 감소
(구조적으로 아는 것 = availability·lineage 즉시 KNOWN, freshness·quality 는 데이터 흐르면 KNOWN).

**새 provider/DB/원장 없음 · 실행 없음 · 포트폴리오 로직 없음.** 원칙(§Constitution): 통합·데이터만.
"""
from __future__ import annotations

import os

# 우선순위 소스(기존 PROVIDER_CATALOG 이름 재사용) — 중복 생성 아님
PRIORITY_SOURCES = ("KRX", "OpenDART-fin", "SEC-EDGAR")
# 카테고리별 기대 스키마(schema validation 기준) — 정규화 후 필수 필드
_EXPECTED_SCHEMA = {
    "market": ("symbol", "date", "open", "high", "low", "close", "volume"),
    "fundamental": ("symbol", "period", "metric", "value"),
    "insider": ("symbol", "date", "insider", "shares"),
}
_KNOWN = "KNOWN"
_UNKNOWN = "UNKNOWN"


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _catalog(name: str) -> dict:
    from jarvis.research_workflow.providers import PROVIDER_CATALOG
    for c in PROVIDER_CATALOG:
        if c["name"] == name:
            return dict(c)
    return {}


# ── 목표 1: Availability (자격증명/구성 기반, 네트워크 없음) ──
def availability(name: str) -> dict:
    c = _catalog(name)
    env = c.get("env_key", "")
    if not env:
        status = "PUBLIC_AVAILABLE"
        avail = True
    elif os.environ.get(env):
        status = "AVAILABLE"
        avail = True
    else:
        status = "NEEDS_CREDENTIALS"
        avail = False
    return {"source": name, "available": avail, "status": status,
            "requires_credentials": bool(env), "env_key": env or None, "known": True}


# ── 목표 2: Freshness (주입된 데이터의 최신 timestamp; 없으면 UNKNOWN) ──
def freshness(name: str, *, records=None, now: str = "", max_age_days: int = 3) -> dict:
    ts = [str(r.get("date") or r.get("timestamp") or "") for r in (records or []) if isinstance(r, dict)]
    ts = [t for t in ts if t]
    if not ts:
        return {"source": name, "last_timestamp": None, "status": _UNKNOWN, "known": False,
                "detail": "데이터 미주입 — Layer A 클라이언트 연결 시 KNOWN"}
    last = max(ts)
    stale = bool(now and last < now[:len(last)])   # 문자열 ISO 비교(결정적)
    return {"source": name, "last_timestamp": last, "records": len(ts),
            "status": "STALE" if stale else "FRESH", "known": True, "max_age_days": max_age_days}


# ── 목표 3: Schema validation (정규화 후 필수 필드) ──
def schema_validation(category: str, records) -> dict:
    expected = _EXPECTED_SCHEMA.get((category or "").lower(), ())
    recs = list(records or [])
    if not expected:
        return {"category": category, "status": "NO_SCHEMA", "known": False}
    valid = 0
    missing_fields: dict = {}
    for r in recs:
        if not isinstance(r, dict):
            continue
        miss = [f for f in expected if f not in r]
        if not miss:
            valid += 1
        for f in miss:
            missing_fields[f] = missing_fields.get(f, 0) + 1
    return {"category": category, "expected_fields": list(expected),
            "records": len(recs), "valid_records": valid,
            "valid_pct": round(100.0 * valid / len(recs), 1) if recs else None,
            "missing_field_counts": dict(sorted(missing_fields.items())),
            "status": "VALIDATED" if recs else "NO_DATA", "known": bool(recs)}


# ── 목표 4: Retry (지수 백오프 계수, 결정적 — 실제 sleep 없음) ──
def with_retry(fetch_fn, *, attempts: int = 4):
    """주입된 fetch 콜러블을 재시도(결정적, 계수만). 네트워크 로직은 Layer A 클라이언트 소관."""
    last_err = None
    for i in range(max(1, attempts)):
        try:
            return {"ok": True, "attempt": i + 1, "result": fetch_fn()}
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
    return {"ok": False, "attempts": attempts, "error": last_err,
            "backoff_schedule_s": [2 ** i for i in range(attempts)]}


# ── 목표 5: Backfill (주입 배치 일괄 처리 — 멱등은 기존 ingestion 이 담당) ──
def backfill(name: str, batches, *, connector=None) -> dict:
    """과거 데이터 배치 백필. connector(주입)가 각 배치의 raw 를 제공. 없으면 미연결 보고(정직)."""
    if connector is None:
        return {"source": name, "backfilled": 0, "status": "NO_CONNECTOR",
                "detail": "Layer A 클라이언트 connector 주입 필요(자격증명 소유). 프레임워크만 제공."}
    done, failed = 0, 0
    for b in (batches or []):
        r = with_retry(lambda bb=b: connector(bb))
        if r["ok"]:
            done += 1
        else:
            failed += 1
    return {"source": name, "backfilled": done, "failed": failed,
            "batches": len(batches or []), "status": "COMPLETED" if done else "EMPTY"}


# ── 목표 6: Gap detection (기대 주기 대비 결측) ──
def detect_gaps(dates, *, expected_dates=None) -> dict:
    have = sorted({str(d) for d in (dates or []) if d})
    if expected_dates is not None:
        exp = sorted({str(d) for d in expected_dates})
        missing = [d for d in exp if d not in set(have)]
        return {"expected": len(exp), "present": len(have), "missing": missing,
                "gap_count": len(missing), "coverage_pct": round(100.0 * len(have) / len(exp), 1) if exp else None,
                "status": "GAPS" if missing else "COMPLETE"}
    # 기대 목록 없으면 인접 날짜 간격만 리포트(연속성 힌트)
    return {"present": len(have), "first": have[0] if have else None, "last": have[-1] if have else None,
            "status": "NO_EXPECTED_BASELINE", "detail": "expected_dates 주입 시 정확한 gap 산출"}


# ── 목표 7: Lineage (source → adapter → consumer, 카탈로그 구조 기반) ──
def lineage(name: str) -> dict:
    c = _catalog(name)
    if not c:
        return {"source": name, "status": "UNKNOWN_SOURCE", "known": False}
    return {"source": name, "vendor": c.get("vendor"), "category": c.get("category"),
            "chain": [f"vendor:{c.get('vendor')}", f"layer_a_client:{c.get('module')}",
                      f"provider:{c.get('category')}", f"consumer:{c.get('consumer')}"],
            "provider_interface": ["fetch", "normalize", "validate", "health_check"],
            "known": True}


# ── 목표 8: Quality scoring (availability·freshness·schema 합성) ──
def quality_score(avail: dict, fresh: dict, schema: dict) -> dict:
    a = 1.0 if avail.get("available") else (0.5 if avail.get("status") == "NEEDS_CREDENTIALS" else 0.0)
    f = 1.0 if fresh.get("status") == "FRESH" else (0.4 if fresh.get("status") == "STALE" else 0.0)
    s = (schema.get("valid_pct") or 0) / 100.0 if schema.get("known") else 0.0
    known_dims = sum(1 for d in (avail.get("known"), fresh.get("known"), schema.get("known")) if d)
    score = round(0.4 * a + 0.3 * f + 0.3 * s, 4)
    return {"quality_score": score, "components": {"availability": a, "freshness": f, "schema": s},
            "known_dimensions": known_dims, "known": known_dims > 0,
            "grade": "GOOD" if score >= 0.66 else ("PARTIAL" if score >= 0.33 else "LOW")}


def connect_source(name: str, *, raw=None, now: str = "", expected_dates=None) -> dict:
    """한 소스 연결 상태 — availability·freshness·quality·lineage 전부 노출(주입 raw 기반). 읽기전용."""
    c = _catalog(name)
    category = c.get("category", "")
    prov = _safe(lambda: __import__("jarvis.research_workflow.providers",
                                    fromlist=["provider_for"]).provider_for(category))
    # 정규화(주입 raw → 기존 어댑터). 없으면 빈 리스트(정직).
    normalized = []
    for item in (raw or []):
        n = _safe(lambda it=item: prov.normalize(it)) if prov else None
        if isinstance(n, dict):
            normalized.append(n)
    av = availability(name)
    fr = freshness(name, records=(raw or []), now=now)
    sc = schema_validation(category, raw or [])
    ln = lineage(name)
    q = quality_score(av, fr, sc)
    gaps = detect_gaps([str((r or {}).get("date") or (r or {}).get("timestamp") or "")
                        for r in (raw or [])], expected_dates=expected_dates)
    return {"source": name, "category": category,
            "availability": av, "freshness": fr, "schema": sc, "quality": q, "lineage": ln,
            "gaps": gaps, "normalized_count": len(normalized),
            "is_advisory": True, "is_decision": False,
            "note": ("Data Connection(읽기전용) — 기존 provider 재사용, raw 는 Layer A 주입. "
                     "키/데이터 없으면 정직하게 NEEDS_CREDENTIALS/UNKNOWN. 실행/포트폴리오 없음.")}


def data_connection_status(*, now: str = "", injected: dict | None = None) -> dict:
    """우선순위 3소스 종합 — 각 availability·freshness·quality·lineage + UNKNOWN 감소 추적. 읽기전용.

    injected(선택): {source_name: [raw records]} — Layer A 클라이언트가 주입. 없으면 프레임워크 상태만.
    """
    inj = injected or {}
    sources = []
    total_dims = 0
    known_dims = 0
    for name in PRIORITY_SOURCES:
        conn = connect_source(name, raw=inj.get(name), now=now)
        dims = {"availability": conn["availability"].get("known"),
                "freshness": conn["freshness"].get("known"),
                "quality": conn["quality"].get("known"),
                "lineage": conn["lineage"].get("known")}
        total_dims += 4
        known_dims += sum(1 for v in dims.values() if v)
        sources.append({"source": name, "status": conn["availability"]["status"],
                        "quality_grade": conn["quality"]["grade"],
                        "quality_score": conn["quality"]["quality_score"],
                        "known_dimensions": dims})
    unknown_dims = total_dims - known_dims
    return {"priority_sources": list(PRIORITY_SOURCES), "sources": sources,
            "dimensions_total": total_dims, "dimensions_known": known_dims,
            "dimensions_unknown": unknown_dims,
            "known_pct": round(100.0 * known_dims / total_dims, 1) if total_dims else None,
            "objectives": ["availability", "freshness", "schema_validation", "retry", "backfill",
                           "gap_detection", "lineage", "quality_scoring"],
            "requires_human_review": True, "is_advisory": True, "is_decision": False,
            "note": ("Data Connection Status(읽기전용) — 우선순위 3소스, 4차원 노출. "
                     "구조적(availability·lineage)은 즉시 KNOWN, 데이터 흐르면 freshness·quality 도 KNOWN → "
                     "UNKNOWN 감소. 기존 provider 재사용, 새 provider/DB/원장 없음, 실행 없음.")}
