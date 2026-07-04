"""DART 지분공시 → 국민연금공단 매수 이벤트 추출.

유료 없음. DART 공개 API (무료 키 필요, .env OPENDART_API_KEY).
- pblntf_ty=D: 지분공시 (대량보유상황보고서)
- 각 문서 본문에서 "국민연금" 신고자 + 취득 이벤트 파싱
- 캐시: data/institutional/dart_nps_*.json (연도별, 7일 TTL)

CLI: PYTHONPATH=. python3 research/data/dart_nps.py
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, timedelta

STORE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "institutional",
)
_BASE = "https://opendart.fss.or.kr/api"
_TIMEOUT = 20


def _key() -> str:
    k = os.environ.get("OPENDART_API_KEY", "").strip()
    if not k:
        env_path = os.path.join(
            os.path.dirname(os.path.dirname(STORE_DIR)), ".env"
        )
        if os.path.exists(env_path):
            for ln in open(env_path):
                if ln.startswith("OPENDART_API_KEY="):
                    k = ln.split("=", 1)[1].strip().strip('"')
    if not k:
        raise ValueError("OPENDART_API_KEY not set")
    return k


def _fetch_listing_page(key: str, bgn_de: str, end_de: str, page_no: int) -> dict:
    import requests
    r = requests.get(
        f"{_BASE}/list.json",
        params={
            "crtfc_key": key,
            "pblntf_ty": "D",       # 지분공시
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_no": page_no,
            "page_count": 100,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def _fetch_doc_xml(key: str, rcept_no: str) -> str:
    """DART 문서 XML 본문 다운로드."""
    import requests
    try:
        r = requests.get(
            f"{_BASE}/document.xml",
            params={"crtfc_key": key, "rcept_no": rcept_no},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return r.text
    except Exception:
        return ""


def _is_nps(text: str) -> bool:
    return "국민연금" in text


def _parse_nps_event(rcept_no: str, corp_name: str, rcept_dt: str, xml: str) -> dict | None:
    """XML에서 국민연금 취득/처분 파싱. 취득 이벤트만 반환."""
    if not _is_nps(xml):
        return None

    # 변동 유형: 취득/처분
    change_type = ""
    m = re.search(r"<변동유형[^>]*>(.*?)</변동유형>", xml)
    if m:
        change_type = m.group(1).strip()
    if not change_type:
        m = re.search(r"변동유형[^\n]{0,20}(취득|처분)", xml)
        if m:
            change_type = m.group(1)

    if "처분" in change_type:
        return None  # 매도 이벤트 제외

    # 주식 수 / 비율
    shares_m = re.search(r"<변동후주식수[^>]*>([\d,]+)</변동후주식수>", xml)
    ratio_m = re.search(r"<변동후지분율[^>]*>([\d.]+)</변동후지분율>", xml)

    return {
        "source": "dart_nps",
        "corp_name": corp_name,
        "rcept_no": rcept_no,
        "disclosure_date": f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}",
        "change_type": change_type or "취득",
        "shares_after": shares_m.group(1).replace(",", "") if shares_m else "",
        "ratio_after": ratio_m.group(1) if ratio_m else "",
    }


def _cache_path(year: int) -> str:
    os.makedirs(STORE_DIR, exist_ok=True)
    return os.path.join(STORE_DIR, f"dart_nps_{year}.json")


def pull_year(year: int, force: bool = False) -> list[dict]:
    """연도별 국민연금 지분 취득 이벤트. 7일 캐시."""
    cache = _cache_path(year)
    if not force and os.path.exists(cache):
        mtime = date.fromtimestamp(os.path.getmtime(cache))
        if mtime >= date.today() - timedelta(days=7):
            with open(cache) as f:
                return json.load(f)

    key = _key()
    bgn_de = f"{year}0101"
    end_de = f"{year}1231"

    print(f"  DART 지분공시 {year}: 목록 요청...")
    all_filings: list[dict] = []
    page = 1
    while True:
        data = _fetch_listing_page(key, bgn_de, end_de, page)
        if data.get("status") != "000":
            print(f"  DART API 오류: {data.get('status')} {data.get('message')}")
            break
        batch = data.get("list", [])
        if not batch:
            break
        all_filings.extend(batch)
        total = int(data.get("total_count", 0))
        print(f"  {year} page {page}: {len(all_filings)}/{total}")
        if len(all_filings) >= total:
            break
        page += 1
        time.sleep(0.3)

    print(f"  {year}: 총 {len(all_filings)}건 지분공시 → 국민연금 필터링")

    events: list[dict] = []
    for i, filing in enumerate(all_filings):
        rcept_no = filing.get("rcept_no", "")
        corp_name = filing.get("corp_name", "")
        rcept_dt = filing.get("rcept_dt", "")
        report_nm = filing.get("report_nm", "")

        # report_nm에 "국민연금" 없으면 빠르게 스킵 (문서 다운로드 절약)
        # 실제로는 report_nm이 "주식등의대량보유상황보고서"라 필터 불가 — 모두 다운로드
        xml = _fetch_doc_xml(key, rcept_no)
        ev = _parse_nps_event(rcept_no, corp_name, rcept_dt, xml)
        if ev:
            events.append(ev)

        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(all_filings)} 처리 (NPS 이벤트 {len(events)}건)")
        time.sleep(0.2)

    with open(cache, "w") as f:
        json.dump(events, f, ensure_ascii=False)
    print(f"  {year}: NPS 취득 이벤트 {len(events)}건 저장")
    return events


def load_events(min_date: str = "2020-01-01", years: list[int] | None = None) -> list[dict]:
    """DART 국민연금 취득 이벤트 로드. 종목코드는 kr_data에서 매핑 필요."""
    if years is None:
        start_year = int(min_date[:4])
        years = list(range(start_year, date.today().year + 1))
    all_events: list[dict] = []
    for year in years:
        try:
            all_events.extend(pull_year(year))
        except Exception as e:
            print(f"  {year} 로드 실패: {e}")
    filtered = [e for e in all_events if e.get("disclosure_date", "") >= min_date]
    filtered.sort(key=lambda x: x["disclosure_date"])
    return filtered


if __name__ == "__main__":
    print("DART 국민연금 취득 이벤트 수집 (2023~)")
    events = load_events(min_date="2023-01-01", years=[2023, 2024, 2025])
    print(f"\n총 {len(events)}건")
    for e in events[-10:]:
        print(f"  {e['disclosure_date']}  {e['corp_name']:20s}  {e['change_type']}  {e.get('ratio_after','')}%")
