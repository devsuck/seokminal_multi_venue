"""US federal contract awards via USASpending.gov (free, no key).

최근 대형 연방계약 낙찰 = 상장사(방산·테크 등) 주가 시그널. 트럼프 행정부
정부지출 흐름을 기업 단위로 추적.
"""
import datetime as _dt

import requests

_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
_TIMEOUT = 20


def get_recent_contracts(days: int = 30, limit: int = 40) -> list[dict]:
    """최근 연방계약 낙찰(금액순). 계약(A~D 유형)만."""
    end = _dt.date.today()
    start = end - _dt.timedelta(days=days)
    body = {
        "filters": {
            "award_type_codes": ["A", "B", "C", "D"],  # contracts
            "time_period": [{"start_date": start.isoformat(), "end_date": end.isoformat()}],
        },
        "fields": ["Award ID", "Recipient Name", "Award Amount",
                   "Awarding Agency", "Description", "Start Date"],
        "sort": "Award Amount",
        "order": "desc",
        "limit": limit,
    }
    resp = requests.post(_URL, json=body, timeout=_TIMEOUT)
    resp.raise_for_status()
    out = []
    for x in resp.json().get("results", []):
        out.append({
            "recipient": x.get("Recipient Name", ""),
            "amount": float(x.get("Award Amount", 0) or 0),
            "agency": x.get("Awarding Agency", ""),
            "description": (x.get("Description") or "")[:160],
            "start_date": x.get("Start Date", ""),
            "award_id": x.get("Award ID", ""),
        })
    return out
