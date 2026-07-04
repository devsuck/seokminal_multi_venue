"""KR 권리락 수정주가 인프라 — 무상증자 배정비율(DART)로 back-adjust.

무상증자·분할은 권리락일에 주가 기계적 하락(대신 주식수↑). KRX 무수정 실종가는
이걸 가짜 손실로 찍음. DART pifricDecsn에서 배정비율·기준일 받아 조정계수 계산:
  factor = 전주식 / (전주식 + 신주) = 1/(1+배정비율)   (권리락일 하락폭)
back-adjust = 권리락일 이전 가격을 factor로 축소 → 시계열 연속. hold가 권리락 넘어도 실수익.
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

from research.data.kr_dart_events import _key, load_events

STORE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "kr")
_PIFRIC = "https://opendart.fss.or.kr/api/pifricDecsn.json"


def _num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _kdate(s: str) -> str | None:
    """'2020년 06월 08일' → '2020-06-08'."""
    m = re.findall(r"\d+", str(s or ""))
    if len(m) >= 3:
        return f"{m[0]}-{int(m[1]):02d}-{int(m[2]):02d}"
    return None


def pull_bonus_ratios(pace_s: float = 0.12, log=print) -> list[dict]:
    """무상증자 이벤트 corp별 pifricDecsn → {stock_code, ex_record_date, factor, ratio}."""
    key = _key()
    ev = load_events("bonus_issue")
    corp2stock, years = {}, {}
    for e in ev:
        corp2stock[e["corp_code"]] = e["stock_code"]
        years.setdefault(e["corp_code"], set()).add(e["date"][:4])
    out, seen = [], set()
    for i, (cc, sc) in enumerate(corp2stock.items(), 1):
        yy = sorted(years[cc])
        bgn, end = f"{yy[0]}0101", f"{yy[-1]}1231"
        try:
            r = requests.get(_PIFRIC, params={"crtfc_key": key, "corp_code": cc, "bgn_de": bgn, "end_de": end}, timeout=20).json()
        except Exception:
            time.sleep(1.0); continue
        if r.get("status") == "000":
            for d in r.get("list", []):
                new = _num(d.get("fric_nstk_ostk_cnt"))
                bef = _num(d.get("fric_bfic_tisstk_ostk"))
                ratio = _num(d.get("fric_nstk_ascnt_ps_ostk"))
                rec = _kdate(d.get("fric_nstk_asstd"))
                if not rec or not new or new <= 0:
                    continue
                if bef and bef > 0:
                    factor = bef / (bef + new)
                elif ratio and ratio > 0:
                    factor = 1.0 / (1.0 + ratio)
                else:
                    continue
                kid = (sc, rec)
                if kid in seen:
                    continue
                seen.add(kid)
                out.append({"stock_code": sc, "ex_record_date": rec, "factor": round(factor, 6),
                            "ratio": ratio, "new_shares": new})
        time.sleep(pace_s)
        if i % 100 == 0:
            log(f"  ratio {i}/{len(corp2stock)} (수집 {len(out)})")
    return out


def save_ratios(rows: list[dict]) -> str:
    os.makedirs(STORE, exist_ok=True)
    p = os.path.join(STORE, "bonus_ratios.jsonl")
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def load_factors() -> dict:
    """{stock_code: [(ex_record_date, factor)] 정렬}."""
    p = os.path.join(STORE, "bonus_ratios.jsonl")
    if not os.path.exists(p):
        return {}
    fac: dict = {}
    for ln in open(p):
        if ln.strip():
            d = json.loads(ln)
            fac.setdefault(d["stock_code"], []).append((d["ex_record_date"], d["factor"]))
    for k in fac:
        fac[k].sort()
    return fac


def adjust_bars(bars: dict, ex_list: list[tuple[str, float]]) -> dict:
    """back-adjust: 각 가격에 이후 권리락 factor들의 곱을 적용(권리락 이전만 축소)."""
    if not ex_list:
        return bars
    dates = bars["dates"]
    out = {**bars}
    for field in ("open", "high", "low", "close"):
        if field not in bars:
            continue
        adj = []
        for i, d in enumerate(dates):
            mult = 1.0
            for ex_d, f in ex_list:
                if d < ex_d:      # 권리락일 이전 가격 축소
                    mult *= f
            adj.append(bars[field][i] * mult)
        out[field] = adj
    return out
