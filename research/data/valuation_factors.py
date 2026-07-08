"""KR 밸류에이션/퀄리티 팩터 — krx marcap(research/data/krx_api.py) × DART 재무제표(dart_financials.py) 조인.

PER/PBR/PSR: marcap 직접 사용(프록시 아님).
EV/EBIT: EBITDA 아님 — 감가상각비가 DART 요약 재무제표에 종목별로 일관 노출 안 돼서
         영업이익(EBIT) 기준으로 근사. net_debt = 부채총계 - 현금(이자부채 세분류 없음, 근사).
ROIC: NOPAT/(총자산-유동부채-현금) 근사. 세율 22% 고정 가정.
F-Score: Piotroski 9개 중 8개(신주발행 신호는 별도 시계열 필요해 제외) — thstrm/frmtrm
         한 콜에 다 들어있어 종목당 API 1콜로 완결.
"""
from __future__ import annotations

import glob
import os

import pandas as pd

from research.data.dart_financials import load_cached

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
KRX_STORE = os.path.join(ROOT, "data", "krx")
TAX_RATE = 0.22


def latest_marcap(market: str = "KOSPI") -> pd.DataFrame:
    """가장 최근 스냅샷의 종목별 시총/상장주수/종가."""
    d = os.path.join(KRX_STORE, market.lower())
    files = sorted(glob.glob(os.path.join(d, "*.parquet")))
    if not files:
        return pd.DataFrame()
    df = pd.read_parquet(files[-1])
    df = df.rename(columns={"ISU_CD": "stock_code", "ISU_NM": "name", "TDD_CLSPRC": "close"})
    return df[["stock_code", "name", "close", "MKTCAP", "LIST_SHRS"]].rename(columns={"MKTCAP": "marcap"})


def compute_factors(fin: dict, marcap: float) -> dict:
    """fin = dart_financials.parse_financials() 결과. marcap = 시가총액(원)."""
    g = fin.get

    net_profit, total_equity, sale = g("net_profit"), g("total_equity"), g("sale")
    total_assets, total_liab = g("total_assets"), g("total_liab")
    current_assets, current_liab = g("current_assets"), g("current_liab")
    cash, op_profit, op_cf = g("cash"), g("op_profit"), g("op_cashflow")
    gross_profit = g("gross_profit")

    out: dict = {
        "per": (marcap / net_profit) if net_profit and net_profit > 0 else None,
        "pbr": (marcap / total_equity) if total_equity else None,
        "psr": (marcap / sale) if sale else None,
        "roe_pct": (net_profit / total_equity * 100) if net_profit is not None and total_equity else None,
        "debt_ratio_pct": (total_liab / total_equity * 100) if total_liab is not None and total_equity else None,
        "current_ratio_pct": (current_assets / current_liab * 100) if current_assets is not None and current_liab else None,
        "op_margin_pct": (op_profit / sale * 100) if op_profit is not None and sale else None,
        "gross_margin_pct": (gross_profit / sale * 100) if sale and gross_profit is not None else None,
    }

    if op_profit is not None and total_assets is not None and current_liab is not None and cash is not None:
        nopat = op_profit * (1 - TAX_RATE)
        invested_capital = total_assets - current_liab - cash
        out["roic_pct"] = (nopat / invested_capital * 100) if invested_capital and invested_capital > 0 else None
    else:
        out["roic_pct"] = None

    if op_profit is not None and total_liab is not None and cash is not None:
        net_debt = total_liab - cash
        ev = marcap + net_debt
        out["ev_ebit"] = (ev / op_profit) if op_profit and op_profit > 0 else None
    else:
        out["ev_ebit"] = None

    # Piotroski F-Score(8/9 — 신주발행 신호 제외)
    signals = []
    roa = (net_profit / total_assets) if net_profit is not None and total_assets else None
    net_profit_prev, total_assets_prev = g("net_profit_prev"), g("total_assets_prev")
    roa_prev = (net_profit_prev / total_assets_prev) if net_profit_prev is not None and total_assets_prev else None

    if roa is not None:
        signals.append(1 if roa > 0 else 0)
    if op_cf is not None:
        signals.append(1 if op_cf > 0 else 0)
    if roa is not None and roa_prev is not None:
        signals.append(1 if roa > roa_prev else 0)
    if op_cf is not None and net_profit is not None:
        signals.append(1 if op_cf > net_profit else 0)

    total_liab_prev, total_equity_prev = g("total_liab_prev"), g("total_equity_prev")
    if total_liab is not None and total_equity and total_liab_prev is not None and total_equity_prev:
        lev_now, lev_prev = total_liab / total_equity, total_liab_prev / total_equity_prev
        signals.append(1 if lev_now < lev_prev else 0)

    current_assets_prev, current_liab_prev = g("current_assets_prev"), g("current_liab_prev")
    if current_liab and current_liab_prev and current_assets is not None and current_assets_prev is not None:
        cr_now, cr_prev = current_assets / current_liab, current_assets_prev / current_liab_prev
        signals.append(1 if cr_now > cr_prev else 0)

    gross_profit_prev, sale_prev = g("gross_profit_prev"), g("sale_prev")
    if sale and sale_prev and gross_profit is not None and gross_profit_prev is not None:
        gm_now, gm_prev = gross_profit / sale, gross_profit_prev / sale_prev
        signals.append(1 if gm_now > gm_prev else 0)

    if sale and sale_prev and total_assets and total_assets_prev:
        at_now, at_prev = sale / total_assets, sale_prev / total_assets_prev
        signals.append(1 if at_now > at_prev else 0)

    out["f_score"] = sum(signals) if signals else None
    out["f_score_n"] = len(signals)

    return out


def build_universe_factors(market: str, year: str) -> pd.DataFrame:
    """krx marcap 유니버스 × DART 캐시 조인 → 종목별 팩터 테이블(캐시 없는 종목은 스킵)."""
    mc = latest_marcap(market)
    rows = []
    for _, r in mc.iterrows():
        fin = load_cached(r["stock_code"], year)
        if fin is None:
            continue
        factors = compute_factors(fin, r["marcap"])
        factors["stock_code"] = r["stock_code"]
        factors["name"] = r["name"]
        factors["marcap"] = r["marcap"]
        rows.append(factors)
    return pd.DataFrame(rows)
