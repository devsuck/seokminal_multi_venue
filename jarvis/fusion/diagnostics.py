"""어댑터 커버리지 진단 — 데이터 가용성 · buyback 신선도 · tom 캘린더 검증.

전부 결정적·읽기전용. Date.now 미사용(as_of 주입). CLI `python -m jarvis.fusion diagnose`.
"""
from __future__ import annotations

import datetime as _dt

from jarvis.fusion.adapters.base import add_business_days, as_date, last_business_day


def _days_between(a: str, b: str) -> int:
    return (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days


# ── buyback 신선도 ───────────────────────────────────────────
def buyback_freshness(as_of: str, rows: list[dict] | None = None,
                      stale_after_days: int = 30) -> dict:
    """포지션 원장 신선도. exit_date 결측분은 동결 hold 규칙으로 만료 판정.

    반환: newest_entry, days_since_newest, n_positions, n_active, n_missing_exit,
    n_expired_missing_exit(만료됐어야 하나 exit 미기록), ledger_fresh(bool).
    """
    from jarvis.fusion.adapters.buyback import DEFAULT_HOLD_DAYS, _read_rows
    d = as_date(as_of)
    rows = rows if rows is not None else _read_rows()
    entries = [r["entry_date"] for r in rows if r.get("entry_date")]
    newest = max(entries) if entries else None
    n_active = 0
    n_missing_exit = 0
    n_expired_missing = 0
    for r in rows:
        entry = r.get("entry_date")
        if not entry or entry > d:
            continue
        hold = int(r.get("hold_days") or DEFAULT_HOLD_DAYS)
        scheduled = r.get("exit_date") or add_business_days(entry, hold)
        if not r.get("exit_date"):
            n_missing_exit += 1
            if d >= scheduled:
                n_expired_missing += 1
        if d < scheduled:
            n_active += 1
    return {
        "as_of": d, "newest_entry": newest,
        "days_since_newest": _days_between(newest, d) if newest else None,
        "n_positions": len(rows), "n_active": n_active,
        "n_missing_exit": n_missing_exit, "n_expired_missing_exit": n_expired_missing,
        "ledger_fresh": bool(newest and _days_between(newest, d) <= stale_after_days),
        "note": "exit_date 결측분은 동결 hold 규칙으로 만료 판정(stale 롱 방지).",
    }


# ── tom 캘린더 검증 ──────────────────────────────────────────
def verify_tom_calendar(trading_dates: list[str], hold_days: int = 4) -> dict:
    """실제 거래일 목록 대비 business-day 근사 월말진입일 검증.

    실제 월 마지막 거래일 = 해당 월 최대 거래일. 근사(last_business_day)와 비교.
    반환: {n_months, match_rate, mismatches:[{month, actual, approx}]}.
    휴장일이 월말평일이면 불일치 발생 → 정직하게 노출(KRX 캘린더 필요 신호).
    """
    by_month: dict[str, list[str]] = {}
    for d in sorted(set(trading_dates)):
        by_month.setdefault(d[:7], []).append(d)
    mismatches = []
    for m, days in by_month.items():
        actual = days[-1]
        y, mo = int(m[:4]), int(m[5:7])
        approx = last_business_day(y, mo)
        if actual != approx:
            mismatches.append({"month": m, "actual": actual, "approx": approx})
    n = len(by_month)
    return {"n_months": n, "hold_days": hold_days,
            "match_rate": round((n - len(mismatches)) / n, 4) if n else None,
            "mismatches": mismatches}


# ── 어댑터 데이터 가용성 ─────────────────────────────────────
def adapter_status(as_of: str) -> dict:
    """등록 어댑터별 현재 신호 산출량 + 사유(정직한 커버리지 현주소)."""
    from jarvis.fusion.adapters import ADAPTERS
    out = {}
    for sid, prov in ADAPTERS.items():
        try:
            sigs = prov.signals(as_of)
            n = len(sigs)
            out[sid] = {"n_signals": n,
                        "status": "emitting" if n else "no_signals",
                        "reason": "" if n else "데이터/날짜 조건 미충족(배선은 완료)"}
        except Exception as exc:  # noqa: BLE001
            out[sid] = {"n_signals": 0, "status": "error", "reason": str(exc)}
    return out
