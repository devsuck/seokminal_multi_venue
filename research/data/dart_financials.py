"""DART 재무제표 수집 — corp_code 매핑 + fnlttSinglAcntAll 재무제표.

corp_code 매핑: opendart corpCode.xml 벌크 다운로드(대용량 3.5MB, requests로 스트리밍 시
서버가 느리게 흘려보내 timeout이 안 먹힘 → curl -m 필수). data/dart_corp_codes.parquet 캐시.

재무제표: fnlttSinglAcntAll.json 1콜에 당기/전기/전전기 금액 동시 반환 →
Piotroski F-Score 등 YoY 비교도 종목당 연 1콜로 해결.
종목당 연도별 parquet 저장(data/dart_financials/{stock_code}_{year}.parquet) → 재실행 시 스킵.
"""
from __future__ import annotations

import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CORP_CODE_PARQUET = os.path.join(ROOT, "data", "dart_corp_codes.parquet")
FIN_STORE = os.path.join(ROOT, "data", "dart_financials")
DART = "https://opendart.fss.or.kr/api"

# account_nm(한글) → canonical key. sj_div로 statement 구분해 동명 계정 충돌 방지.
ACCOUNT_MAP: dict[str, tuple[str, tuple[str, ...]]] = {
    "total_assets":    ("BS", ("자산총계",)),
    "total_liab":      ("BS", ("부채총계",)),
    "total_equity":    ("BS", ("자본총계",)),
    "current_assets":  ("BS", ("유동자산",)),
    "current_liab":    ("BS", ("유동부채",)),
    "cash":            ("BS", ("현금및현금성자산",)),
    "sale":            (None, ("매출액", "영업수익")),          # IS/CIS 겸용(금융업은 영업수익)
    "gross_profit":    (None, ("매출총이익", "매출총이익(손실)")),
    "op_profit":       (None, ("영업이익(손실)", "영업이익")),
    "net_profit":      (None, ("당기순이익(손실)", "당기순이익")),
    "op_cashflow":     ("CF", ("영업활동현금흐름",)),
}


def _key() -> str:
    k = os.environ.get("OPENDART_API_KEY", "")
    if not k:
        env = os.path.join(ROOT, ".env")
        if os.path.exists(env):
            for ln in open(env):
                if ln.startswith("OPENDART_API_KEY="):
                    k = ln.split("=", 1)[1].strip().strip('"')
    return k


def load_corp_codes(force: bool = False) -> pd.DataFrame:
    """상장사 corp_code↔stock_code 매핑. 캐시 없으면 벌크 다운로드(느림, curl 사용)."""
    if not force and os.path.exists(CORP_CODE_PARQUET):
        return pd.read_parquet(CORP_CODE_PARQUET)

    import subprocess
    import tempfile
    key = _key()
    if not key:
        raise ValueError("OPENDART_API_KEY 없음")
    with tempfile.TemporaryDirectory() as tmp:
        zpath = os.path.join(tmp, "corpCode.zip")
        subprocess.run(
            ["curl", "-sS", "-m", "400", "-G", f"{DART}/corpCode.xml",
             "--data-urlencode", f"crtfc_key={key}", "-o", zpath],
            check=True, timeout=420,
        )
        with zipfile.ZipFile(zpath) as z:
            xml_bytes = z.read(z.namelist()[0])

    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_bytes)
    rows = []
    for item in root.findall("list"):
        sc = (item.findtext("stock_code") or "").strip()
        if sc:
            rows.append({
                "corp_code": item.findtext("corp_code").strip(),
                "stock_code": sc,
                "corp_name": item.findtext("corp_name").strip(),
            })
    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(CORP_CODE_PARQUET), exist_ok=True)
    df.to_parquet(CORP_CODE_PARQUET)
    return df


def fetch_one(corp_code: str, year: str, reprt_code: str = "11011", fs_div: str = "CFS") -> list[dict]:
    """단일회사 전체 재무제표 원본 rows. reprt_code: 11011=사업보고서(연간)."""
    r = requests.get(
        f"{DART}/fnlttSinglAcntAll.json",
        params={"crtfc_key": _key(), "corp_code": corp_code, "bsns_year": year,
                "reprt_code": reprt_code, "fs_div": fs_div},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "000":
        return []
    return data.get("list", [])


def parse_financials(rows: list[dict]) -> dict:
    """원본 rows → canonical 지표 dict(당기/전기 금액 포함, YoY용)."""

    def _num(s: str | None) -> float | None:
        if not s:
            return None
        try:
            return float(str(s).replace(",", ""))
        except ValueError:
            return None

    out: dict = {}
    for key, (sj_filter, names) in ACCOUNT_MAP.items():
        for r in rows:
            if sj_filter and r.get("sj_div") != sj_filter:
                continue
            if r.get("account_nm") not in names:
                continue
            out[key] = _num(r.get("thstrm_amount"))
            out[f"{key}_prev"] = _num(r.get("frmtrm_amount"))
            out[f"{key}_prev2"] = _num(r.get("bfefrmtrm_amount"))
            break  # 첫 매치 채택(계정 우선순위 = names 튜플 순서)

    return out


def _cache_path(stock_code: str, year: str) -> str:
    return os.path.join(FIN_STORE, f"{stock_code}_{year}.parquet")


def pull_universe(
    stock_codes: list[str],
    year: str,
    reprt_code: str = "11011",
    max_workers: int = 5,
    pace_s: float = 0.15,
    log=print,
) -> dict[str, dict]:
    """종목 리스트 재무제표 병렬 수집. 캐시 있으면 스킵(재실행 안전)."""
    os.makedirs(FIN_STORE, exist_ok=True)
    corp_df = load_corp_codes()
    code_map = dict(zip(corp_df["stock_code"], corp_df["corp_code"]))

    todo = [sc for sc in stock_codes if sc in code_map and not os.path.exists(_cache_path(sc, year))]
    cached = [sc for sc in stock_codes if sc in code_map and os.path.exists(_cache_path(sc, year))]
    log(f"수집 대상 {len(todo)}건, 캐시 스킵 {len(cached)}건, corp_code 미매핑 {len(stock_codes) - len(todo) - len(cached)}건")

    def _work(sc: str) -> tuple[str, dict | None]:
        try:
            rows = fetch_one(code_map[sc], year, reprt_code)
            time.sleep(pace_s)
            if not rows:
                return sc, None
            parsed = parse_financials(rows)
            parsed["stock_code"] = sc
            parsed["year"] = year
            pd.DataFrame([parsed]).to_parquet(_cache_path(sc, year))
            return sc, parsed
        except Exception as e:
            log(f"  {sc} ERR {str(e)[:60]}")
            return sc, None

    results: dict[str, dict] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_work, sc): sc for sc in todo}
        for fut in as_completed(futures):
            sc, parsed = fut.result()
            if parsed:
                results[sc] = parsed
            done += 1
            if done % 100 == 0:
                log(f"  진행 {done}/{len(todo)}")

    for sc in cached:
        try:
            results[sc] = pd.read_parquet(_cache_path(sc, year)).iloc[0].to_dict()
        except Exception:
            pass

    log(f"완료: {len(results)}/{len(stock_codes)} 확보")
    return results


def load_cached(stock_code: str, year: str) -> dict | None:
    p = _cache_path(stock_code, year)
    if not os.path.exists(p):
        return None
    return pd.read_parquet(p).iloc[0].to_dict()
