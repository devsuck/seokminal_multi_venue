"""Korea 시장 데이터 접근 (FinanceDataReader). 공개 KRX/네이버 데이터, 로컬 리서치용.

⚠️ SSL: 맥 Python.framework cert 미설정 → 공개 KRX listing 조회용으로만 로컬 우회.
   외부 서비스에 데이터 전송 아님(읽기전용 공개데이터 수집).
⚠️ 한계: 현재 상장 스냅샷만(PIT universe 아님), 상장폐지 이력 없음 → survivorship 미제어.
   → 결과는 RESEARCH_SANITY_CHECK_ONLY.
"""
from __future__ import annotations

import os
import ssl

import pandas as pd

# 로컬 cert 우회 (공개데이터 조회 한정)
ssl._create_default_https_context = ssl._create_unverified_context

STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "kr")


def list_universe(market: str = "KOSDAQ") -> pd.DataFrame:
    """현재 상장 종목 스냅샷 (Code/Name/Marcap/Amount/Close/Dept). PIT 아님."""
    import FinanceDataReader as fdr
    df = fdr.StockListing(market)
    return df


def filter_universe(
    df: pd.DataFrame,
    min_marcap: float = 5e10,        # 시총 >= 500억
    min_amount: float = 3e9,         # 거래대금 >= 30억
    min_price: float = 1000.0,
    exclude_admin: bool = True,
) -> list[dict]:
    """유동성/시총/가격 sanity 필터 + 관리종목/투자주의 제외(Dept 기반). 튜닝 아님."""
    out = []
    for _, r in df.iterrows():
        try:
            mc = float(r.get("Marcap", 0) or 0)
            amt = float(r.get("Amount", 0) or 0)
            px = float(r.get("Close", 0) or 0)
        except (TypeError, ValueError):
            continue
        dept = str(r.get("Dept", "") or "")
        if exclude_admin and ("관리" in dept or "투자주의" in dept or "정리매매" in dept):
            continue
        if mc >= min_marcap and amt >= min_amount and px >= min_price:
            out.append({"code": str(r["Code"]), "name": str(r.get("Name", "")),
                        "marcap": mc, "amount": amt, "close": px, "dept": dept})
    return out


def load_ohlcv(code: str, start: str, end: str) -> pd.DataFrame:
    """티커 일봉 (FDR.DataReader). Open/High/Low/Close/Volume. 거래대금=Close*Volume 프록시."""
    import FinanceDataReader as fdr
    df = fdr.DataReader(code, start, end)
    if len(df):
        df = df.copy()
        df["trading_value"] = df["Close"] * df["Volume"]  # 프록시 (실 거래대금 아님)
    return df


def save_ohlcv(code: str, df: pd.DataFrame) -> str:
    os.makedirs(STORE_DIR, exist_ok=True)
    p = os.path.join(STORE_DIR, f"{code}.parquet")
    df.to_parquet(p)
    return p


def load_stored(code: str) -> pd.DataFrame:
    p = os.path.join(STORE_DIR, f"{code}.parquet")
    return pd.read_parquet(p) if os.path.exists(p) else pd.DataFrame()
