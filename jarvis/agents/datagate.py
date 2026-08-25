"""Data Gate Agent — 백테스트 전에 무효 연구 차단(결정적).

PIT·survivorship·상폐포함·타임스탬프·표본 확인 → 상태 반환.
결과: DATA_GATE_PASS / BLOCKED_BY_DATA / SANITY_CHECK_ONLY / NEEDS_MANUAL_DATA_REVIEW.
registry 전이: draft→data_audit_passed | blocked_by_data | sanity_check_only.
"""
from __future__ import annotations

import argparse
import json

from jarvis.agents import DATAGATE_AGENT
from jarvis.permissions import require
from jarvis.registry import Status, StrategyRegistry

# 데이터 능력 맵(현 플랫폼 실제 상황). 결정적 규칙. 전 시장.
_CAPABILITY = {
    # ── KR (KRX PIT + OpenDART) ──
    "daily_ohlcv": True, "market_cap": True, "trading_value": True,
    "delisting_history": True,               # KRX PIT 스냅샷 = survivorship-free
    "sector": True,
    "disclosure_event_dates": True,          # OpenDART(buyback/CB 발행 등)
    "cb_bw_issuance": True,                   # DART cvbdIsDecsn/bdwtIsDecsn
    "cb_bw_release_linkage": False,          # 해소↔원발행 회차 linkage = 미구축
    "remaining_convertible_balance": False,  # 미상환 잔액 재구성 = 미구축
    "earnings_pit_disclosure_map": False,    # 재무 PIT 공시일 매핑 = 미완
    "consensus_revision": False,             # 무료 애널리스트 없음
    "institutional_flow": False,             # KRX 로그인 필요
    # ── US (IB / Alpaca / SEC EDGAR) ──
    "us_daily_ohlcv": True,                  # IB/Alpaca 일봉
    "us_intraday_15m": True,                 # IB 15분(제한적 히스토리)
    "us_delisting_history": False,           # 무료 PIT survivorship 유니버스 없음 → SANITY만
    "sec_filings_events": True,              # SEC EDGAR 8-K/13D 등
    "us_fundamentals_pit": False,            # 무료 PIT 재무 없음
    # ── Crypto (Hyperliquid public) ──
    "crypto_daily_ohlcv": True,              # HL candles
    "crypto_intraday": True,                 # HL 분/시간봉
    "crypto_funding": True,                  # HL 펀딩(단, 검증서 REJECT됨)
    "crypto_orderbook_hist": False,          # HL L2 스냅샷만, 히스토리 없음
    "crypto_open_interest": True,       # HL metaAndAssetCtxs 폴링(백필 불가, run_oi_collect.py로 축적)
    "crypto_liquidation": True,         # Binance 선물 WS(forceOrder), run_liquidation_collect.py로 축적
    "crypto_basis": True,               # HL perp markPx vs Binance spot, run_basis_collect.py로 축적
    "crypto_cross_venue_spread": True,  # 기존 cross_venue_skew.py 재사용(HL/Binance/OKX 오더북)
    # ── Insider/Convergence (KR DART + US EDGAR/FMP + Alpaca options) ──
    "kr_insider_disclosure": True,     # DART 임원·주요주주 소유보고(insider/dart_client.py), 백필 가능
    "us_congress_trades": True,        # FMP senate/house-latest, point-in-time만(백필 불가) — run_convergence_signal_collect.py로 축적
    "us_insider_form4": True,          # SEC EDGAR Form4 Archives, 백필 가능
    "options_uoa_signal": True,        # Alpaca 옵션체인 UOA, point-in-time만(백필 불가) — options_uoa/*.jsonl.gz로 축적
}

# soft-missing = 검증 가능하나 편향 경고(SANITY). hard-missing = 검증 불가(BLOCKED).
_SANITY_SOFT = {"us_delisting_history", "earnings_pit_disclosure_map", "us_fundamentals_pit"}


def check(strategy_id: str, required_data: list[str], commit: bool = True) -> dict:
    """required_data를 능력맵과 대조 → 상태. commit이면 registry 전이."""
    require(DATAGATE_AGENT, "run_data_gate", strategy_id)
    missing = [d for d in required_data if _CAPABILITY.get(d) is False]
    unknown = [d for d in required_data if d not in _CAPABILITY]
    hard = [d for d in missing if d not in _SANITY_SOFT]
    soft = [d for d in missing if d in _SANITY_SOFT]

    if hard:
        status, to, reason = "BLOCKED_BY_DATA", Status.BLOCKED_BY_DATA, f"필수 데이터 미구축: {hard}"
    elif unknown:
        status, to, reason = "NEEDS_MANUAL_DATA_REVIEW", None, f"미확인 데이터: {unknown}"
    elif soft:
        # 검증은 가능하나 편향 경고(US survivorship·PIT재무) → SANITY(paper 승격 불가)
        status, to, reason = "SANITY_CHECK_ONLY", Status.SANITY_CHECK_ONLY, f"편향 경고(검증가능·paper불가): {soft}"
    else:
        status, to, reason = "DATA_GATE_PASS", Status.DATA_AUDIT_PASSED, "데이터 게이트 통과"

    result = {"strategy_id": strategy_id, "status": status, "reason": reason,
              "blocked_features": hard, "sanity_flags": soft, "unknown": unknown}
    if commit and to is not None:
        reg = StrategyRegistry()
        if reg.state(strategy_id) is not None:
            reg.transition(strategy_id, to, f"data_gate: {status}", evidence=result)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.agents.datagate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--strategy", required=True)
    p.add_argument("--data", nargs="*", default=["daily_ohlcv", "market_cap", "delisting_history"])
    args = ap.parse_args(argv)
    if args.cmd == "check":
        print(json.dumps(check(args.strategy, args.data, commit=False), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
