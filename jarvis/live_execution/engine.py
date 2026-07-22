"""Live Execution Engine (P8.1) — 첫 라이브 집행 경계. **사람 게이트 전용.**

승인된 단 하나의 지시를 브로커 어댑터로 전달한다(오직 안전 게이트 통과 후).
소유권 경계:
  Execution Control(P7.4)   의도 유효성 판단.
  Readiness(P7.7)           시스템 상태 인증.
  ARM                       사람 권한.
  Live Execution Adapter    승인된 지시 하나를 브로커로 전송.  ← 본 레이어

**제출 전 안전 게이트(하나라도 실패 → REJECTED, 브로커 미호출):**
  ① readiness == READY  ② 사람 ARM 존재  ③ quantity > 0
  ④ 유효 심볼          ⑤ 시장데이터 신선  (⑥ 어댑터 활성 — 어댑터가 자체 판정)

**MUST NOT: 자율 집행·전략 트리거 주문·무인 트레이딩·자동 자본 배치.**
명시적 호출로만. 결정적·append-only. 실브로커 어댑터는 기본 비활성.
"""
from __future__ import annotations

from jarvis.live_execution import ledger
from jarvis.live_execution.models import (
    ACCEPTED,
    LiveExecutionRequest,
    LiveExecutionResponse,
    REJECTED,
    request_hash,
    request_id,
    response_hash,
)

_ARM_LEDGER = "execution_control_arm.jsonl"
_EPS = 1e-9
_READY = "READY"


def human_arm(intent_id: str) -> dict | None:
    """사람 ARM 레코드(execution_control_arm.jsonl, armed=True) 조회. 엔진은 기록 안 함."""
    from jarvis.config import state_path
    import json
    import os
    p = state_path(_ARM_LEDGER)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        rows = [json.loads(ln) for ln in f if ln.strip()]
    cur = None
    for r in rows:
        if r.get("intent_id") == intent_id:
            cur = r
    return cur if (cur and cur.get("armed") is True) else None


def build_request(intent, arm_id: str, broker: str, now: str,
                  limit_price: float | None = None) -> LiveExecutionRequest:
    """의도 + 사람 ARM → LiveExecutionRequest. 수량은 의도 값(사이징 없음)."""
    iid = getattr(intent, "intent_id", "")
    rid = request_id(iid, arm_id, now)
    return LiveExecutionRequest(
        request_id=rid, intent_id=iid, broker=broker,
        symbol=getattr(intent, "symbol", ""), side=getattr(intent, "side", ""),
        quantity=float(getattr(intent, "quantity", 0.0)), limit_price=limit_price,
        created_at=now, arm_id=arm_id)


class LiveExecutionEngine:
    """사람 게이트 라이브 집행. 자율 트리거 없음 — 명시적 호출로만."""

    def submit(self, request: LiveExecutionRequest, certificate, adapter, now: str, *,
               arm_present: bool | None = None, market_fresh: bool | None = None,
               live_provider=None, commit: bool = False) -> LiveExecutionResponse | None:
        cert = certificate.to_dict() if hasattr(certificate, "to_dict") else (certificate or {})

        # 중복 방지: 동일 request_id 커밋 재시도 → None
        if commit and ledger.request_exists(request.request_id):
            return None

        # ── 안전 게이트(모두 통과해야 브로커 호출) ──
        blockers: list[str] = []
        # ① readiness == READY
        if cert.get("status") != _READY:
            blockers.append("readiness_not_ready")
        # 인증서-요청 의도 일치(방어)
        if cert.get("intent_id") and cert.get("intent_id") != request.intent_id:
            blockers.append("certificate_intent_mismatch")
        # ② 사람 ARM 존재
        armed = arm_present if arm_present is not None else (human_arm(request.intent_id) is not None)
        if not armed:
            blockers.append("no_human_arm")
        # ③ quantity > 0
        if request.quantity <= _EPS:
            blockers.append("invalid_quantity")
        # ④ 유효 심볼
        if not request.symbol:
            blockers.append("invalid_symbol")
        # ⑤ 시장데이터 신선
        fresh = market_fresh if market_fresh is not None else self._market_fresh(live_provider)
        if not fresh:
            blockers.append("stale_market_data")

        if blockers:
            return self._respond(request, REJECTED, "", "; ".join(blockers), now, commit,
                                 gated=True)

        # ── 게이트 통과 → 브로커 어댑터로 단 하나의 지시 전송 ──
        result = adapter.submit_order(request.to_dict())
        status = ACCEPTED if result.get("accepted") else REJECTED
        boid = result.get("broker_order_id", "")
        return self._respond(request, status, boid, result.get("reason", ""), now, commit,
                             gated=False)

    def _market_fresh(self, live_provider) -> bool:
        if live_provider is None:
            return False   # 라이브 데이터 미구성 → 정직한 CLOSED
        h = live_provider.health_check() if hasattr(live_provider, "health_check") else {}
        d = h.to_dict() if hasattr(h, "to_dict") else h
        return bool(d.get("connected")) and not d.get("stale", False)

    def _respond(self, request: LiveExecutionRequest, status: str, broker_order_id: str,
                 reason: str, now: str, commit: bool, gated: bool) -> LiveExecutionResponse:
        rh = response_hash(request.request_id, broker_order_id, status, reason, now)
        resp = LiveExecutionResponse(request_id=request.request_id, broker_order_id=broker_order_id,
                                     status=status, reason=reason, timestamp=now, response_hash=rh)
        if commit and not ledger.request_exists(request.request_id):
            req_row = {**request.to_dict(), "request_hash": request_hash(request.to_dict())}
            ledger.append_request(req_row)
            ledger.append_response(resp.to_dict())
            ledger.append_event({"event": "live_execution_submit", "request_id": request.request_id,
                                 "intent_id": request.intent_id, "broker": request.broker,
                                 "status": status, "gated_reject": gated, "reason": reason,
                                 "timestamp": now})
        return resp
