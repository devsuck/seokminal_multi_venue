"""국민연금(NPS) 및 기관 매수 데이터.

## 데이터 현황

### NPS 특정 (DART 지분공시, pblntf_ty=D)
- NPS가 5% 이상 보유 종목에서 1% 이상 변동 시 지분공시 제출
- 제약: DART list.json 메타데이터에는 신고 회사명(corp_name)만 있음
  — NPS가 신고자인지 여부는 문서 본문 파싱 필요 (미구현)
- TODO: DART archive XML 파싱으로 "국민연금공단" 신고자 필터링

### KRX 기관 순매수 (현재 구현)
- KRX 투자자별 매매동향 (aggregated): 기관 전체 순매수
- 일별, 종목별, 무료
- NPS 단독보다 signal이 넓지만 접근 가능한 데이터

### 사용법
```
from research.data.nps_holdings import load_institutional_buys
events = load_institutional_buys(["005930", "000660"])  # 삼성전자, SK하이닉스
```
"""
from __future__ import annotations

import os
import time

STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "institutional")


def _fetch_krx_investor_flow(code: str, start: str = "20200101", end: str | None = None) -> list[dict]:
    """KRX 투자자별 매매동향 (기관 순매수). data.krx.co.kr OTP 방식."""
    import requests
    from datetime import date
    if end is None:
        end = date.today().strftime("%Y%m%d")

    # KRX OTP 취득 → 데이터 요청 (2단계)
    otp_url = "http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd"
    data_url = "http://data.krx.co.kr/comm/fileDn/downloadExcel/download.cmd"
    headers = {"Referer": "http://data.krx.co.kr/"}

    otp_params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT02301",
        "name": "fileDown",
        "filetype": "json",
        "isuCd": f"KR7{code}003",  # ISIN 근사값 (정확한 ISIN은 ksd/client 사용)
        "strtDd": start,
        "endDd": end,
        "money": "1",
    }
    try:
        otp = requests.post(otp_url, data=otp_params, headers=headers, timeout=15).text.strip()
        if not otp:
            return []
        resp = requests.post(data_url, data={"code": otp}, headers=headers, timeout=15)
        rows = resp.json().get("output", [])
        result = []
        for row in rows:
            # 기관 순매수 양수 = 매수 우세
            inst_net = _parse_num(row.get("INST_NETBID_TRDVOL", "0"))
            if inst_net > 0:
                result.append({
                    "stock_code": code,
                    "date": row.get("TRD_DD", "").replace("/", "-"),
                    "inst_net_volume": inst_net,
                    "inst_net_value": _parse_num(row.get("INST_NETBID_TRDVAL", "0")),
                })
        return result
    except Exception:
        return []


def _parse_num(s: str) -> float:
    try:
        return float(str(s).replace(",", ""))
    except Exception:
        return 0.0


def load_institutional_buys(codes: list[str], min_date: str = "2020-01-01") -> list[dict]:
    """종목 리스트의 기관 순매수 이벤트 (순매수 > 0인 날 = 이벤트)."""
    os.makedirs(STORE_DIR, exist_ok=True)
    events: list[dict] = []
    for code in codes:
        rows = _fetch_krx_investor_flow(code, start=min_date.replace("-", ""))
        for r in rows:
            if r["date"] >= min_date:
                events.append({
                    "stock_code": code,
                    "date": r["date"],
                    "signal": "inst_net_buy",
                    "magnitude": r["inst_net_volume"],
                })
        time.sleep(0.3)
    events.sort(key=lambda x: x["date"])
    return events
