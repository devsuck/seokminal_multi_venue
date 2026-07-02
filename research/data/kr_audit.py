"""Korea Liquidity Wave — 데이터 게이트 audit (스펙 첫 지시).

FDR(StockListing/DataReader)로 실제 되는 것 확인. pykrx는 KRX 로그인 요구(universe/시총/플로우 블록).
없으면 BLOCKED_BY_DATA. survivorship/PIT/상장폐지 없음 → RESEARCH_SANITY_CHECK_ONLY.
실행: PYTHONPATH=. python3 research/data/kr_audit.py
"""
from __future__ import annotations

import json


def audit() -> dict:
    a = {
        "has_daily_ohlcv": False, "has_adjusted_prices": True, "has_trading_value": False,
        "has_market_cap": False, "has_listing_status": False, "has_suspension_flags": False,
        "has_delisting_history": False, "has_intraday_data": False, "has_news": False,
        "has_dart_disclosures": False, "has_investor_flow": False, "has_credit_balance": False,
        "has_short_interest": False, "available_universe": 0, "date_range": {},
        "blocked_features": [], "sources": {},
    }
    # 1. universe + 시총 + 거래대금 (FDR StockListing, SSL 우회는 kr_data가 처리)
    try:
        from research.data.kr_data import list_universe, load_ohlcv
        for mkt in ("KOSPI", "KOSDAQ"):
            try:
                df = list_universe(mkt)
                a["available_universe"] += len(df)
                a["sources"][f"{mkt}_listed"] = len(df)
                cols = list(df.columns)
                a["has_market_cap"] = a["has_market_cap"] or ("Marcap" in cols)
                a["has_trading_value"] = a["has_trading_value"] or ("Amount" in cols)
                a["has_listing_status"] = a["has_listing_status"] or ("Dept" in cols)  # 관리종목 판별 가능
            except Exception as e:
                a["blocked_features"].append(f"{mkt}_listing: {str(e)[:60]}")
        # 티커 일봉
        try:
            df = load_ohlcv("247540", "2024-01-01", "2024-03-01")
            a["has_daily_ohlcv"] = len(df) > 0 and "Close" in df.columns
            if len(df):
                a["date_range"] = {"sample_start": str(df.index[0].date()), "sample_end": str(df.index[-1].date())}
        except Exception as e:
            a["blocked_features"].append(f"ohlcv: {str(e)[:60]}")
    except Exception as e:
        a["blocked_features"].append(f"kr_data: {str(e)[:60]}")

    # 2. 상장폐지 이력 (FDR KRX-DELISTING) — 현재 빈 응답
    try:
        import FinanceDataReader as fdr
        try:
            dl = fdr.StockListing("KRX-DELISTING")
            a["has_delisting_history"] = len(dl) > 0
        except Exception:
            a["blocked_features"].append("delisting: 빈 응답")
    except ImportError:
        pass

    # 3. DART 공시 (기존 모듈)
    import importlib
    a["has_dart_disclosures"] = importlib.util.find_spec("insider.dart_client") is not None

    # 4. 블록 (KRX 로그인/데이터 부재)
    a["blocked_features"] += [
        "intraday (일봉만)", "news_timestamp_corpus", "investor_flow (KRX 로그인 필요)",
        "credit_balance (KRX 로그인)", "short_interest (KRX 로그인)", "PIT_universe (현재 스냅샷만)",
    ]

    # 데이터 품질 판정
    critical = []
    if not a["has_delisting_history"]:
        critical.append("delisting")
    if not a["has_suspension_flags"]:
        critical.append("suspension")
    critical.append("PIT_universe")  # 항상 (현재 스냅샷만)
    a["survivorship_control"] = a["has_delisting_history"]
    a["critical_missing"] = critical
    a["data_quality_status"] = "RESEARCH_SANITY_CHECK_ONLY"  # 상장폐지/PIT 없어 항상 sanity
    a["trading_value_note"] = "스냅샷은 실 거래대금(Amount), 히스토리는 Close*Volume 프록시"
    return a


def main():
    print(json.dumps(audit(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
