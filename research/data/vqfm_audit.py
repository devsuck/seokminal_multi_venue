"""VQFM (Value/Quality/Flow/Momentum) 데이터 게이트 audit — KR.

프로브 확인 반영: KRX(가격·시총·섹터, PIT survivorship-free) + DART 재무(PIT via 공시일) +
FDR 상장폐지. revision/기관수급 = BLOCKED. US는 PIT 재무 없어 SANITY만.
실행: PYTHONPATH=. python3 research/data/vqfm_audit.py
"""
from __future__ import annotations

import json


def audit() -> dict:
    return {
        "market": "KR",
        "has_daily_ohlcv": True,            # KRX 날짜별 스냅샷
        "has_adjusted_prices": False,       # KRX 실종가(무수정) → 분할일 주의(드묾)
        "has_volume": True,
        "has_market_cap": True,             # KRX MKTCAP (PIT)
        "has_sector_classification": True,  # KRX SECT_TP_NM(부서, GICS 아님, 러프)
        "has_delisting": True,              # KRX 스냅샷 = survivorship-free by construction
        "has_fundamentals": True,           # DART fnlttSinglAcnt (당기순이익·자본·매출·영업이익)
        "fundamentals_pit": True,           # 공시일(rcept_dt) 기준 사용 → PIT 가능
        "has_valuation_direct": False,      # PER/PBR 직접 API: pykrx=KRX로그인 필요(막힘)
        "valuation_computable": True,       # DART 순이익·자본 + KRX 가격 → PER/PBR 계산(PIT)
        "has_eps_revisions": False,         # 무료 애널리스트 없음 → QoQ/YoY 성장으로 대체
        "has_institutional_flow": False,    # KRX 로그인 필요 (BLOCKED)
        "has_insider": True,                # DART 임원·주요주주 (기존)
        "available_universe": 2766,         # KOSPI 945 + KOSDAQ 1821
        "blocked_features": ["eps_revision(애널리스트)", "institutional_flow(KRX로그인)", "adjusted_price(KRX 무수정)"],
        "data_quality_momentum": "PIT + survivorship-free (KRX 스냅샷만 필요) = 검증 가능",
        "data_quality_value": "DART 재무 PIT 파이프라인 구축 시 검증 가능(현재 미구축)",
        "us_note": "US는 무료 PIT 재무 없음 → VQFM = RESEARCH_SANITY_CHECK_ONLY, 검증 안 함",
        "recommendation": "1) pure momentum(KRX만, 지금 가능) 2) pure value(DART 재무 파이프 후) 3) 하나라도 random 이기면 composite",
    }


def main():
    print(json.dumps(audit(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
