"""System Health 수집기 (P9.1) — 서브시스템별 관측만. **집행 아님.**

각 수집기는 서브시스템 하나를 관측해 SubsystemProbe 를 만든다. **집행 소유 서브시스템은
원장(JSONL)을 *데이터 파일*로만 읽는다 — 게이트웨이/arm/live/paper/risk거버너를 import 하지
않는다.** 상태 변경·거래 인가·브로커 접촉 없음. 결정적(헬스 상태만 해싱, latency 제외).

허용 import(읽기전용): config(경로), registry(레지스트리 상태), permissions 정책(FORBIDDEN
불변식), broker_readonly 어댑터(읽기전용 헬스). 집행 소유 서브시스템(집행 게이트웨이·arm·
live/paper 실행·리스크 거버너)은 import 하지 않고 원장 파일로만 관측한다.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from jarvis.config import state_path
from jarvis.system_health.models import (
    CRITICAL,
    DEGRADED,
    HEALTHY,
    OFFLINE,
    UNKNOWN,
    WARNING,
    SubsystemProbe,
    is_ok,
    probe_hash,
)

# ── 임계값(결정적·설정 가능) ──
_STALE_SECONDS = 24 * 3600.0        # 원장 마지막 갱신이 이보다 오래되면 WARNING
_DEGRADED_LATENCY_MS = 250.0        # 관측 지연이 이보다 크면 DEGRADED(다른 이상 없을 때)

# 오류/경고로 간주하는 상태 마커(원장 레코드의 status/overall 필드 값)
_ERROR_MARKERS = {"CRITICAL", "FAILED", "REJECTED", "BLOCKED", "ERROR", "BREACH", "BREACHED"}
_WARN_MARKERS = {"WARNING", "WARN", "DEGRADED", "STALE", "PARTIAL", "UNMATCHED", "PENDING"}


def _now_dt(now: str):
    try:
        return _dt.datetime.fromisoformat((now or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_ts(ts: str):
    try:
        return _dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _read_jsonl(filename: str) -> list[dict]:
    """원장을 *데이터 파일*로만 읽는다(집행 코드 import 없음). 없으면 []."""
    p = state_path(filename)
    if not os.path.exists(p):
        return []
    out: list[dict] = []
    with open(p) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except (ValueError, json.JSONDecodeError):
                continue
    return out


def _finalize(name: str, status: str, *, last_update: str = "", latency_ms: float = 0.0,
              warnings: list | None = None, errors: list | None = None,
              detail: str = "") -> SubsystemProbe:
    warnings = list(warnings or [])
    errors = list(errors or [])
    h = probe_hash(name, status, warnings, errors)
    return SubsystemProbe(
        name=name, status=status, last_update=last_update,
        latency_ms=round(float(latency_ms), 4), healthy=is_ok(status),
        warnings=warnings, errors=errors, hash=h, detail=detail)


def _grade_records(name: str, records: list, now: str, *,
                   status_keys=("overall_status", "status", "overall", "decision", "state"),
                   ts_keys=("timestamp", "last_update", "ts", "time"),
                   latency_ms: float = 0.0, allow_empty_unknown: bool = True) -> SubsystemProbe:
    """원장 레코드 목록을 결정적으로 등급화 → SubsystemProbe.

    규칙(우선순위): 데이터 없음→UNKNOWN → 오류마커→CRITICAL → 경고마커→WARNING →
    stale(임계 초과)→WARNING → latency 초과→DEGRADED → 그 외 HEALTHY.
    """
    warnings: list = []
    errors: list = []
    if not records:
        if allow_empty_unknown:
            return _finalize(name, UNKNOWN, latency_ms=latency_ms,
                             detail="원장 없음/미기록 — 관측 데이터 없음")
        return _finalize(name, HEALTHY, latency_ms=latency_ms, detail="빈 원장(정상 초기상태)")

    last = records[-1]
    last_update = ""
    for k in ts_keys:
        if last.get(k):
            last_update = str(last.get(k))
            break

    # 최근 레코드의 상태 마커 수집
    markers: list[str] = []
    for k in status_keys:
        v = last.get(k)
        if isinstance(v, str) and v:
            markers.append(v.upper())
    ok_flag = last.get("ok")
    if ok_flag is False:
        markers.append("FAILED")

    hit_err = [m for m in markers if m in _ERROR_MARKERS]
    hit_warn = [m for m in markers if m in _WARN_MARKERS]

    if hit_err:
        errors.append(f"error_marker:{hit_err[0]}")
        return _finalize(name, CRITICAL, last_update=last_update, latency_ms=latency_ms,
                         warnings=warnings, errors=errors,
                         detail=f"최근 레코드 오류상태 {hit_err[0]}")

    # stale 판정(now 와 last_update 비교)
    ndt, ldt = _now_dt(now), _parse_ts(last_update)
    age = None
    if ndt and ldt:
        age = (ndt - ldt).total_seconds()

    if hit_warn:
        warnings.append(f"warning_marker:{hit_warn[0]}")
        return _finalize(name, WARNING, last_update=last_update, latency_ms=latency_ms,
                         warnings=warnings, errors=errors,
                         detail=f"최근 레코드 경고상태 {hit_warn[0]}")

    if age is not None and age > _STALE_SECONDS:
        warnings.append(f"stale:{int(age)}s")
        return _finalize(name, WARNING, last_update=last_update, latency_ms=latency_ms,
                         warnings=warnings, errors=errors,
                         detail=f"원장 갱신 {int(age)}s 전 — stale(>{int(_STALE_SECONDS)}s)")

    if latency_ms > _DEGRADED_LATENCY_MS:
        warnings.append(f"latency:{round(latency_ms, 1)}ms")
        return _finalize(name, DEGRADED, last_update=last_update, latency_ms=latency_ms,
                         warnings=warnings, detail=f"관측 지연 {round(latency_ms, 1)}ms")

    return _finalize(name, HEALTHY, last_update=last_update, latency_ms=latency_ms,
                     detail=f"{len(records)}건 관측 — 정상")


# ── 집행 소유 서브시스템: 원장 파일로만 관측(import 금지) ──
_LEDGER_SUBSYSTEMS = [
    ("Paper Runtime", "paper_positions.jsonl"),
    ("Execution Control", "execution_decisions.jsonl"),
    ("Execution Readiness", "execution_readiness_certificates.jsonl"),
    ("Live Execution", "live_execution_responses.jsonl"),
    ("Order Lifecycle", "order_lifecycle_events.jsonl"),
    ("Fill Reconciliation", "fill_reconciliation_events.jsonl"),
    ("Execution Cost", "execution_cost_events.jsonl"),
    ("Execution Risk", "execution_risk_reports.jsonl"),
    ("Execution Audit", "execution_audit_certificates.jsonl"),
    ("Post Trade Analytics", "post_trade_reports.jsonl"),
    ("Reconciliation", "reconciliation_events.jsonl"),
]


def collect_ledger_subsystem(name: str, filename: str, now: str) -> SubsystemProbe:
    """집행 소유 서브시스템을 원장 데이터로만 관측(코드 import 없음)."""
    try:
        records = _read_jsonl(filename)
    except OSError as e:  # 파일시스템 오류 → 오프라인
        return _finalize(name, OFFLINE, errors=[f"read_error:{type(e).__name__}"],
                         detail=f"원장 접근 실패: {filename}")
    return _grade_records(name, records, now)


# ── 관측 소유 서브시스템: 읽기전용 import 허용 ──
def collect_registry(now: str) -> SubsystemProbe:
    name = "Registry"
    try:
        from jarvis.registry import StrategyRegistry
        reg = StrategyRegistry()
        current = reg.all_current()
    except Exception as e:  # noqa: BLE001 — 관측기는 어떤 서브시스템 예외도 CRITICAL 로만 흡수
        return _finalize(name, CRITICAL, errors=[f"registry_error:{type(e).__name__}"],
                         detail="레지스트리 관측 실패")
    if not current:
        return _finalize(name, UNKNOWN, detail="레지스트리 비어있음 — 등록 전략 없음")
    active = sum(1 for s in current if str(s.get("status", "")).upper() in
                 {"APPROVED", "PAPER_TRADING", "LIVE", "ACTIVE", "VALIDATED"})
    return _finalize(name, HEALTHY, detail=f"전략 {len(current)}개(활성 {active})")


def collect_permissions(now: str) -> SubsystemProbe:
    """권한 정책 불변식 관측: FORBIDDEN 집합 존재·핵심 금지항목 유지."""
    name = "Permissions"
    try:
        from jarvis.permissions.policy import FORBIDDEN
    except Exception as e:  # noqa: BLE001
        return _finalize(name, CRITICAL, errors=[f"policy_error:{type(e).__name__}"],
                         detail="권한 정책 로드 실패")
    required = {"expand_own_permission", "delete_audit_log", "rewrite_registry_history"}
    missing = required - set(FORBIDDEN)
    if missing:
        return _finalize(name, CRITICAL, errors=[f"forbidden_weakened:{sorted(missing)}"],
                         detail="FORBIDDEN 불변식 약화 감지")
    return _finalize(name, HEALTHY, detail=f"FORBIDDEN {len(FORBIDDEN)}개 유지")


def collect_configuration(now: str) -> SubsystemProbe:
    """설정/자율레벨 관측: live 게이트 폐쇄 여부(autonomy < MIN_LIVE)."""
    name = "Configuration"
    try:
        from jarvis.config import (
            AUTONOMY_LEVEL,
            MIN_LIVE_LEVEL,
            live_execution_enabled,
        )
    except Exception as e:  # noqa: BLE001
        return _finalize(name, CRITICAL, errors=[f"config_error:{type(e).__name__}"],
                         detail="설정 로드 실패")
    warnings: list = []
    if live_execution_enabled():
        # live 게이트가 열려있으면(레벨 상승) 경고로만 표기 — 관측기는 판단만
        warnings.append(f"live_gate_open:autonomy={AUTONOMY_LEVEL}")
        return _finalize(name, WARNING, warnings=warnings,
                         detail=f"autonomy={AUTONOMY_LEVEL} ≥ MIN_LIVE={MIN_LIVE_LEVEL}")
    return _finalize(name, HEALTHY,
                     detail=f"autonomy={AUTONOMY_LEVEL} < MIN_LIVE={MIN_LIVE_LEVEL} (live 폐쇄)")


def collect_broker_readonly(now: str) -> SubsystemProbe:
    """브로커 읽기전용 어댑터 헬스(주문 아님 — 상태 조회 표면만)."""
    name = "Broker Readonly"
    try:
        import jarvis.broker_readonly.adapters as _adapters  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return _finalize(name, UNKNOWN, warnings=[f"adapter_unavailable:{type(e).__name__}"],
                         detail="읽기전용 브로커 어댑터 미구성")
    return _finalize(name, HEALTHY, detail="읽기전용 브로커 어댑터 로드됨(주문 표면 없음)")


def collect_market_data(now: str) -> SubsystemProbe:
    """시장데이터 서브시스템 관측(원장/캐시 파일 기준)."""
    name = "Market Data"
    records = _read_jsonl("market_data_snapshots.jsonl")
    # 시장데이터는 원장이 없어도 서브시스템 부재가 아니므로 UNKNOWN 유지(정직)
    return _grade_records(name, records, now)


def collect_portfolio_runtime(now: str) -> SubsystemProbe:
    name = "Portfolio Runtime"
    records = _read_jsonl("portfolio_snapshots.jsonl")
    return _grade_records(name, records, now)


# 관측 소유(읽기전용 import 또는 비집행 원장) 수집기 목록
_MANAGED_COLLECTORS = [
    ("Market Data", collect_market_data),
    ("Broker Readonly", collect_broker_readonly),
    ("Portfolio Runtime", collect_portfolio_runtime),
    ("Registry", collect_registry),
    ("Permissions", collect_permissions),
    ("Configuration", collect_configuration),
]


def collect_all(now: str) -> list[SubsystemProbe]:
    """전 서브시스템 관측 → 결정적 순서의 SubsystemProbe 목록. **읽기전용.**"""
    probes: list[SubsystemProbe] = []
    for name, filename in _LEDGER_SUBSYSTEMS:
        probes.append(collect_ledger_subsystem(name, filename, now))
    for _name, fn in _MANAGED_COLLECTORS:
        probes.append(fn(now))
    return probes


def subsystem_names() -> list[str]:
    return [n for n, _ in _LEDGER_SUBSYSTEMS] + [n for n, _ in _MANAGED_COLLECTORS]
