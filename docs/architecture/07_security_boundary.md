# Security Boundary Document

Invariants enforced across every layer (verified by P35 safety scans):

- 실행 권한 없음 (no execute/deploy/trade/allocate/approve)
- 브로커 연결 없음 (no broker/live_trading imports)
- 라이브 배포 없음 (no live deployment)
- 자율 거래 없음 (no autonomous trading)
- append-only 원장 (no update/delete API)
- SHA256 해시체인 무결성 (tamper detectable)
- 상위 계층 READ ONLY (no cross-ownership mutation)
- 결정적 재현 (deterministic replay)

**Forbidden everywhere:** execute_trade, place_order, allocate_capital,
deploy_strategy, activate_live, approve_for_trading; imports of
execution/broker/live_trading/portfolio_execution.
