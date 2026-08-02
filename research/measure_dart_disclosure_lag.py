"""KR 임원·주요주주 소유상황보고 실제 공시지연(변동일→접수일) 실측.

elestock.json 요약 API엔 실제 거래일이 없어(rcept_dt=접수일만) 원문 document.xml을
직접 파싱(insider.dart_client.get_report_lag_days)해야 진짜 지연일수가 나옴. 최근 N건
샘플링해서 분포(평균/중앙값/최대, 법정기한 5영업일 초과 비율) 출력.

사용: PYTHONPATH=. python3 research/measure_dart_disclosure_lag.py [샘플수=20]
"""
from __future__ import annotations

import datetime as _dt
import statistics
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

from insider.dart_client import DART_BASE, _TIMEOUT, _key, get_report_lag_days


def _recent_disclosures(n: int) -> list[dict]:
    end_de = _dt.date.today().strftime("%Y%m%d")
    bgn_de = (_dt.date.today() - _dt.timedelta(days=14)).strftime("%Y%m%d")
    r = requests.get(
        f"{DART_BASE}/list.json",
        params={
            "crtfc_key": _key(), "bgn_de": bgn_de, "end_de": end_de,
            # D002 = 임원ㆍ주요주주특정증권등소유상황보고서 (B001은 주요사항보고서라 완전 다른 공시)
            "pblntf_ty": "D", "pblntf_detail_ty": "D002",
            "sort": "date", "sort_mth": "desc", "page_no": 1, "page_count": n,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "000":
        return []
    return data.get("list", [])[:n]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    disclosures = _recent_disclosures(n)
    print(f"샘플 {len(disclosures)}건 리포트 원문 파싱 중...")

    all_lags: list[int] = []
    for d in disclosures:
        lags = get_report_lag_days(d["rcept_no"], d["rcept_dt"])
        if lags:
            print(f"  {d['rcept_dt']} {d.get('corp_name', ''):10s} lag={lags}")
        all_lags.extend(lags)

    if not all_lags:
        print("파싱된 지연일수 없음 (샘플 내 세부변동내역 있는 리포트가 없었을 수 있음)")
        return

    # 음수 lag은 원본 문서 자체의 오기(예: 2030년 타이핑) — 통계에서 제외하고 건수만 표시
    bad = [x for x in all_lags if x < 0]
    lags = [x for x in all_lags if x >= 0]
    if bad:
        print(f"(원문 오기로 보이는 음수 lag {len(bad)}건 제외: {bad})")
    if not lags:
        print("유효한 지연일수 없음")
        return

    over_5 = sum(1 for x in lags if x > 5)
    print(f"\nn={len(lags)}  평균={statistics.mean(lags):.1f}일  "
          f"중앙값={statistics.median(lags):.1f}일  최대={max(lags)}일  "
          f"법정기한(5영업일) 초과={over_5}건 ({over_5 / len(lags):.0%})")


if __name__ == "__main__":
    main()
