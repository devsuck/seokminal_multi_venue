"""Fill Reconciliation Engine (P8.3) — 브로커 체결 vs 내부 기대 대조. **집행 아님.**

Broker Fill Report → FillReconciliationEngine → FillReconciliationReport →
append-only 해시체인 원장. 브로커가 '보고한' 체결만 검증 — 주문/집행/write 없음.

검사(허용→WARNING→FAILED):
  quantity_difference · price_difference_bps · fee_difference · timing_difference_seconds
매칭: broker_order_id(link_map) → fallback request_id. 다중체결 집계(가중평균).
탐지: 체결 없음(missing) · 예상 밖 체결(unexpected) · 가격/수수료 편차.

**MUST NOT: 주문 제출·브로커 write·집행 게이트웨이 호출·포지션/포트폴리오/리스크 변경.**
결정적·재현가능.
"""
from __future__ import annotations

from jarvis.fill_reconciliation import ledger
from jarvis.fill_reconciliation.matcher import aggregate, match
from jarvis.fill_reconciliation.models import (
    FAILED,
    FillReconciliationReport,
    FillThresholds,
    GENESIS,
    MATCHED,
    grade,
    input_hash,
    max_status,
    report_hash,
    report_id,
    seconds_between,
)

_BPS = 10_000.0
_EPS = 1e-12


class FillReconciliationEngine:
    def __init__(self, thresholds: FillThresholds | None = None) -> None:
        self.t = thresholds or FillThresholds()

    # ── 단일 내부 기록 대조 ─────────────────────────────────
    def reconcile(self, record, fills: list, now: str = "", *, expected_fee: float = 0.0,
                  broker_order_id: str = "", commit: bool = False) -> FillReconciliationReport:
        rec = record.to_dict() if hasattr(record, "to_dict") else record
        agg = aggregate(fills or [])
        ih = input_hash(rec, agg)
        boid = broker_order_id or (fills and (fills[0].to_dict() if hasattr(fills[0], "to_dict")
                                              else fills[0]).get("broker_order_id", "")) or ""
        rid = report_id(rec["order_id"], boid, ih)

        # 체결 없음 → 누락(FAILED)
        if agg["n_fills"] == 0:
            return self._finish(rid, rec["order_id"], boid, FAILED, {}, agg, ih, now, commit,
                                reason="missing_fill")

        t = self.t
        exp_q = float(rec["expected_quantity"])
        exp_p = float(rec["expected_price"])
        tq = agg["total_quantity"]
        wap = agg["weighted_average_price"]
        tf = agg["total_fee"]

        qdev = round(abs(exp_q - tq), 10)
        qstat = grade(qdev, t.quantity_tolerance, t.fail_multiplier)
        base_p = abs(exp_p) or _EPS
        pdev = round(abs(exp_p - wap) / base_p * _BPS, 8)
        pstat = grade(pdev, t.price_tolerance_bps, t.fail_multiplier)
        fdev = round(abs(float(expected_fee) - tf), 10)
        fstat = grade(fdev, t.fee_tolerance, t.fail_multiplier)
        secs = seconds_between(rec["submitted_at"], agg["last_timestamp"])
        tdev = round(secs, 6) if secs is not None else None
        tstat = grade(tdev if tdev is not None else float("inf"), t.timing_seconds, t.fail_multiplier)

        checks = {"quantity_difference": qdev, "price_difference_bps": pdev,
                  "fee_difference": fdev, "timing_difference_seconds": tdev,
                  "grades": {"quantity": qstat, "price": pstat, "fee": fstat, "timing": tstat}}
        status = max_status([qstat, pstat, fstat, tstat])
        reason = ""
        # 사이드 불일치 → 강제 FAILED
        sides = {(f.to_dict() if hasattr(f, "to_dict") else f).get("side") for f in fills}
        if sides and sides != {rec["expected_side"]}:
            status, reason = FAILED, "side_mismatch"
        return self._finish(rid, rec["order_id"], boid, status, checks, agg, ih, now, commit,
                            reason=reason)

    # ── 배치 대조(누락·예상 밖 체결 탐지 포함) ───────────────
    def reconcile_batch(self, records: list, fills: list, now: str = "", *,
                        link_map: dict | None = None, expected_fees: dict | None = None,
                        commit: bool = False) -> list:
        mr = match(records, fills, link_map)
        expected_fees = expected_fees or {}
        recs = {(r.to_dict() if hasattr(r, "to_dict") else r)["order_id"]:
                (r.to_dict() if hasattr(r, "to_dict") else r) for r in records}
        out = []
        for oid in sorted(mr.matched):
            out.append(self.reconcile(recs[oid], mr.matched[oid], now,
                                      expected_fee=expected_fees.get(oid, 0.0), commit=commit))
        for oid in mr.missing:
            out.append(self.reconcile(recs[oid], [], now,
                                      expected_fee=expected_fees.get(oid, 0.0), commit=commit))
        for f in mr.unexpected:
            fd = f.to_dict() if hasattr(f, "to_dict") else f
            agg = aggregate([fd])
            ih = input_hash(None, agg)
            rid = report_id("", fd.get("broker_order_id", ""), ih)
            out.append(self._finish(rid, "", fd.get("broker_order_id", ""), FAILED, {}, agg,
                                    ih, now, commit, reason="unexpected_fill"))
        return out

    # ── 리포트 확정 + 해시체인 append ───────────────────────
    def _finish(self, rid: str, order_id: str, broker_order_id: str, status: str, checks: dict,
                aggregate_: dict, ih: str, now: str, commit: bool,
                reason: str = "") -> FillReconciliationReport:
        rh = report_hash(rid, order_id, status, checks, aggregate_, ih)
        report = FillReconciliationReport(
            report_id=rid, order_id=order_id, broker_order_id=broker_order_id, status=status,
            checks=checks, aggregate=aggregate_, reason=reason, input_hash=ih,
            report_hash=rh, timestamp=now)
        if commit and not ledger.event_exists(rid):
            head = ledger.chain_head()
            prev_hash = head["report_hash"] if head else GENESIS
            ledger.append_event({"event_id": rid, "order_id": order_id,
                                 "broker_order_id": broker_order_id, "status": status,
                                 "input_hash": ih, "report_hash": rh, "previous_hash": prev_hash,
                                 "reason": reason, "timestamp": now})
        return report
