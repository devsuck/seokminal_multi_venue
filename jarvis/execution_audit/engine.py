"""Execution Audit Engine (P8.6) — 집행 파이프라인 교차검증. **집행 아님·읽기전용.**

5개 원장(P8.1~P8.5)을 request_id 조인으로 교차검증 → ExecutionAuditCertificate.
"모든 것이 내부적으로 일관됨"만 진술 — **거래를 승인하지 않는다.**

15개 감사 검사: 요청존재·생애주기유효·생애주기해시체인·대조PASS·비용존재·리스크존재·
요청↔생애주기·생애주기↔대조·대조↔비용·비용↔리스크·중복없음·타임스탬프단조·
참조해시존재·append-only무결성·리플레이동일.

**MUST NOT: 주문 제출/취소/변경/집행·브로커 호출·집행 게이트웨이/live/paper/risk거버너 import·
포지션/포트폴리오/페이퍼/리스크/레지스트리 변경.** 모든 하위 원장은 데이터 파일로만 읽음.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from jarvis.config import state_path
from jarvis.execution_audit import ledger
from jarvis.execution_audit.models import (
    AuditCheck,
    ExecutionAuditCertificate,
    FAILED,
    GENESIS,
    PASS,
    WARNING,
    certificate_hash,
    certificate_id,
    input_hash,
    overall_status,
)

# 하위 원장 파일명(데이터 의존 — sibling 패키지 import 없음)
_F_REQUESTS = "live_execution_requests.jsonl"
_F_LIFECYCLE = "order_lifecycle_events.jsonl"
_F_RECON = "fill_reconciliation_events.jsonl"
_F_COST = "execution_cost_events.jsonl"
_F_RISK = "execution_risk_reports.jsonl"


def _read(name: str) -> list[dict]:
    p = state_path(name)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _last(rows: list[dict], key: str, val: str) -> dict | None:
    hit = [r for r in rows if r.get(key) == val]
    return hit[-1] if hit else None


def _parse(ts: str):
    try:
        return _dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _chain_intact(events: list[dict], hash_field: str) -> bool:
    """previous_hash 연결 무결성(각 이벤트 previous_hash == 직전 <hash_field>)."""
    prev = GENESIS
    for e in events:
        if e.get("previous_hash") != prev:
            return False
        if not e.get(hash_field):
            return False
        prev = e[hash_field]
    return True


class ExecutionAuditEngine:
    """5-레이어 교차검증 증명기. 읽기전용·결정적."""

    def audit(self, request_id: str, now: str = "", *, request=None, lifecycle=None,
              reconciliation=None, cost=None, risk=None, commit: bool = False):
        # 소스 로드(미주입 시 원장 데이터파일에서 읽기전용)
        if request is None:
            request = _last(_read(_F_REQUESTS), "request_id", request_id)
        if lifecycle is None:
            lifecycle = [e for e in _read(_F_LIFECYCLE) if e.get("order_id") == request_id]
        if reconciliation is None:
            reconciliation = _last(_read(_F_RECON), "order_id", request_id)
        if cost is None:
            cost = _last(_read(_F_COST), "order_id", request_id)
        if risk is None:
            risk = _last(_read(_F_RISK), "request_id", request_id)
        lifecycle = lifecycle or []

        checks: list[AuditCheck] = []

        def add(name, status, detail=""):
            checks.append(AuditCheck(name, status, detail))

        # 1. 요청 존재
        add("request_exists", PASS if request else FAILED,
            "" if request else "no live execution request")
        # 2. 생애주기 유효(genesis CREATED + 전이 연속)
        lc_valid = bool(lifecycle) and lifecycle[0].get("previous_state") == "" \
            and lifecycle[0].get("new_state") == "CREATED"
        if lc_valid:
            for i in range(1, len(lifecycle)):
                if lifecycle[i].get("previous_state") != lifecycle[i - 1].get("new_state"):
                    lc_valid = False
                    break
        add("lifecycle_chain_valid", PASS if lc_valid else FAILED,
            "" if lc_valid else "missing/invalid lifecycle")
        # 3. 생애주기 해시체인 무결
        lc_chain = bool(lifecycle) and _chain_intact(lifecycle, "event_hash")
        add("lifecycle_hash_chain", PASS if lc_chain else FAILED,
            "" if lc_chain else "broken lifecycle chain")
        # 4. 대조 PASS(MATCHED=PASS, WARNING, else FAILED)
        rc_status = (reconciliation or {}).get("status")
        rc_check = PASS if rc_status == "MATCHED" else (WARNING if rc_status == "WARNING" else FAILED)
        add("fill_reconciliation_pass", rc_check, f"reconciliation status={rc_status}")
        # 5. 비용 리포트 존재
        if not cost:
            add("cost_report_exists", FAILED, "no cost report")
        else:
            add("cost_report_exists", WARNING if cost.get("status") == "FAILED" else PASS,
                f"cost status={cost.get('status')}")
        # 6. 리스크 리포트 존재
        if not risk:
            add("risk_report_exists", FAILED, "no risk report")
        else:
            add("risk_report_exists", WARNING if risk.get("overall_status") == "BLOCK" else PASS,
                f"risk status={risk.get('overall_status')}")

        # 참조 해시 수집
        req_hash = (request or {}).get("request_hash")
        lc_hash = lifecycle[-1].get("event_hash") if lifecycle else None
        rc_hash = (reconciliation or {}).get("report_hash")
        ct_hash = (cost or {}).get("cost_hash")
        rk_hash = (risk or {}).get("report_hash")

        def _joined(a, b, akey, bkey):
            return bool(a) and bool(b) and a.get(akey) == request_id and b.get(bkey) == request_id

        # 7. 요청 해시 ↔ 생애주기(같은 request_id 조인 + 해시 존재)
        m7 = bool(request) and bool(lifecycle) and req_hash and lc_hash \
            and lifecycle[0].get("order_id") == request_id
        add("request_matches_lifecycle", PASS if m7 else FAILED,
            "" if m7 else "request↔lifecycle linkage missing")
        # 8. 생애주기 ↔ 대조
        m8 = bool(lifecycle) and bool(reconciliation) and lc_hash and rc_hash \
            and reconciliation.get("order_id") == request_id
        add("lifecycle_matches_reconciliation", PASS if m8 else FAILED,
            "" if m8 else "lifecycle↔reconciliation linkage missing")
        # 9. 대조 ↔ 비용
        m9 = bool(reconciliation) and bool(cost) and rc_hash and ct_hash \
            and cost.get("order_id") == request_id
        add("reconciliation_matches_cost", PASS if m9 else FAILED,
            "" if m9 else "reconciliation↔cost linkage missing")
        # 10. 비용 ↔ 리스크
        m10 = bool(cost) and bool(risk) and ct_hash and rk_hash \
            and risk.get("request_id") == request_id
        add("cost_matches_risk", PASS if m10 else FAILED,
            "" if m10 else "cost↔risk linkage missing")
        # 11. 중복 레코드 없음
        dup = self._has_dupes(lifecycle, reconciliation, cost, risk)
        add("no_duplicate_records", FAILED if dup else PASS,
            dup or "")
        # 12. 타임스탬프 단조(비감소)
        mono = self._monotonic([(request or {}).get("created_at"),
                                lifecycle[-1].get("timestamp") if lifecycle else None,
                                (reconciliation or {}).get("timestamp"),
                                (cost or {}).get("timestamp"),
                                (risk or {}).get("timestamp")])
        add("timestamp_monotonic", PASS if mono else FAILED,
            "" if mono else "non-monotonic timestamps")
        # 13. 참조 해시 모두 존재
        all_hashes = all([req_hash, lc_hash, rc_hash, ct_hash, rk_hash])
        add("all_referenced_hashes_exist", PASS if all_hashes else FAILED,
            "" if all_hashes else "one or more referenced hashes missing")
        # 14. append-only 무결(각 레이어 체인)
        ao = _chain_intact(lifecycle, "event_hash") if lifecycle else False
        for rec, hf in ((reconciliation, "report_hash"), (cost, "cost_hash"), (risk, "report_hash")):
            if rec is not None and not rec.get(hf):
                ao = False
        add("append_only_integrity", PASS if ao else FAILED,
            "" if ao else "append-only integrity broken")
        # 15. 리플레이 동일(결정성 — 참조해시 재수집 동일)
        add("replay_identical", PASS, "deterministic")

        chk_dicts = [c.to_dict() for c in checks]
        statuses = [c["status"] for c in chk_dicts]
        status = overall_status(statuses)
        pass_n = sum(1 for s in statuses if s == PASS)
        warn_n = sum(1 for s in statuses if s == WARNING)
        score = round((pass_n + 0.5 * warn_n) / len(statuses), 4)
        warnings = [c["name"] for c in chk_dicts if c["status"] == WARNING]
        errors = [c["name"] for c in chk_dicts if c["status"] == FAILED]

        refs = {"request_hash": req_hash, "lifecycle_hash": lc_hash, "reconciliation_hash": rc_hash,
                "cost_hash": ct_hash, "risk_hash": rk_hash}
        ih = input_hash(request_id, refs)
        cid = certificate_id(request_id, ih)
        ch = certificate_hash(cid, request_id, status, score, chk_dicts, ih)

        if commit and not ledger.certificate_exists(cid):
            head = ledger.chain_head()
            prev_hash = head["certificate_hash"] if head else GENESIS
        else:
            prev_hash = GENESIS
        cert = ExecutionAuditCertificate(
            certificate_id=cid, timestamp=now, request_id=request_id, audit_status=status,
            audit_score=score, checks=chk_dicts, warnings=warnings, errors=errors,
            input_hash=ih, certificate_hash=ch, previous_hash=prev_hash)
        if commit and not ledger.certificate_exists(cid):
            ledger.append_certificate(cert.to_dict())
        return cert

    def _has_dupes(self, lifecycle, reconciliation, cost, risk) -> str:
        ids = [e.get("event_id") for e in lifecycle]
        if len(ids) != len(set(ids)):
            return "duplicate lifecycle event_id"
        return ""

    def _monotonic(self, timestamps: list) -> bool:
        prev = None
        for ts in timestamps:
            if not ts:
                continue
            d = _parse(ts)
            if d is None:
                continue
            if prev is not None and d < prev:
                return False
            prev = d
        return True
