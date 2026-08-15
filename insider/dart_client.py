"""OpenDART API client for Korean insider trading disclosures."""
from __future__ import annotations

import datetime as _dt
import io
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

DART_BASE = "https://opendart.fss.or.kr/api"
_TIMEOUT = 12
_MDF_DM_RE = re.compile(rb'AUNIT="MDF_DM"\s+AUNITVALUE="(\d{8})"')

_CORP_LIST_TTL_SECONDS = 86400  # 24h, kr_universe.client와 동일 컨벤션
_corp_list_cache: list[dict] = []
_corp_list_cache_ts: float = 0.0
_corp_list_lock = threading.Lock()


def _key() -> str:
    key = os.environ.get("OPENDART_API_KEY", "")
    if not key:
        raise ValueError("OPENDART_API_KEY not set")
    return key


def _get_corp_list() -> list[dict]:
    """전체 상장사 corp_code/corp_name/stock_code 목록, 24h 메모리 캐시.

    DART company.json은 corp_code 단건조회 전용이라 이름검색을 지원하지 않음 —
    공식 이름검색 방법은 corpCode.xml(전체 회사코드 zip) 받아서 로컬 필터링뿐.
    """
    global _corp_list_cache, _corp_list_cache_ts
    if _corp_list_cache and time.time() - _corp_list_cache_ts < _CORP_LIST_TTL_SECONDS:
        return _corp_list_cache
    with _corp_list_lock:
        if _corp_list_cache and time.time() - _corp_list_cache_ts < _CORP_LIST_TTL_SECONDS:
            return _corp_list_cache
        r = requests.get(
            f"{DART_BASE}/corpCode.xml",
            params={"crtfc_key": _key()},
            timeout=60,
        )
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            xml_bytes = zf.read(zf.namelist()[0])
        root = ET.fromstring(xml_bytes)
        _corp_list_cache = [
            {
                "corp_code": el.findtext("corp_code", ""),
                "corp_name": el.findtext("corp_name", ""),
                "stock_code": (el.findtext("stock_code") or "").strip(),
            }
            for el in root.iter("list")
        ]
        _corp_list_cache_ts = time.time()
        return _corp_list_cache


def search_company(name: str) -> list[dict]:
    """Company name → list of {corp_code, corp_name, stock_code} (상장사만)."""
    q = name.strip()
    if not q:
        return []
    return [
        c for c in _get_corp_list()
        if q in c["corp_name"] and c["stock_code"]
    ][:20]


def get_executive_stock_changes(
    corp_code: str,
    bgn_de: str,
    end_de: str,
    page_count: int = 40,
) -> list[dict]:
    """
    임원·주요주주 특정증권등 소유상황보고 변동 내역.
    bgn_de / end_de: YYYYMMDD
    Returns list of trade dicts.
    """
    r = requests.get(
        f"{DART_BASE}/elestock.json",
        params={
            "crtfc_key": _key(),
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_no": 1,
            "page_count": page_count,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") not in ("000",):
        return []

    rows = []
    for item in data.get("list", []):
        # DART가 bgn_de/end_de/page_no/page_count를 이 엔드포인트에서 무시하고
        # 항상 전체 이력을 돌려줘서 여기서 직접 걸러야 함(post-filter).
        rcept_dt = item.get("rcept_dt", "").replace("-", "")
        if rcept_dt and not (bgn_de <= rcept_dt <= end_de):
            continue

        irds_raw = item.get("stkqy_irds", "0").replace(",", "") or "0"
        try:
            irds = int(irds_raw)
        except ValueError:
            irds = 0

        cause = (item.get("irds_cause_nm") or item.get("stkqy_irds_incls_nmis_nm") or "").strip()
        role  = (item.get("rl_nm") or "").strip()

        # Classify by cause text first, fall back to shares_change sign
        cause_lower = cause.lower()
        if any(k in cause_lower for k in ("무상증자", "주식배당", "분할")):
            trade_type = "RIGHTS_ISSUE"
        elif any(k in cause_lower for k in ("유상증자", "신주인수")):
            trade_type = "PAID_IN"
        elif any(k in cause_lower for k in ("소각", "자사주소각")):
            trade_type = "CANCELLATION"
        elif irds > 0:
            trade_type = "BUY"
        elif irds < 0:
            trade_type = "SELL"
        else:
            trade_type = "HOLD_REPORT"  # 변동없이 보고의무만 발생

        rcept_no = item.get("rcept_no", "")
        rows.append({
            "rcept_dt":      item.get("rcept_dt", ""),
            "rcept_no":      rcept_no,
            "dart_url":      f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else None,
            "reporter":      item.get("reprer_nm", ""),
            "role":          role,
            "report_type":   item.get("rcept_type", ""),
            "event_cause":   cause,
            "shares_change": irds,
            "shares_total":  _parse_int(item.get("stkqy", "0")),
            "ownership_pct": _parse_float(item.get("ctr_rate", "0")),
            "corp_name":     item.get("corp_name", ""),
            "trade_type":    trade_type,
        })
    return rows


def get_report_lag_days(rcept_no: str, rcept_dt: str) -> list[int]:
    """공시 원문(document.xml)의 '세부변동내역' 표에서 변동일(MDF_DM, 증권시장 결제일 기준)을
    추출해 공시접수일(rcept_dt) 대비 지연일수 리스트로 반환.

    elestock.json 요약 API엔 실제 거래일 필드가 없어(rcept_dt=접수일만 있음) 원문 XML을
    직접 파싱해야 함. 리포트 하나에 여러 건의 세부변동(장내매수/매도 등)이 있으면 각각의
    지연일수를 전부 반환 — 요약 API의 shares_change 한 줄과 1:1 대응 안 됨을 유의.
    파싱 실패(권리변동보고 등 세부변동표 없는 양식 등) 시 빈 리스트.
    """
    try:
        r = requests.get(
            f"{DART_BASE}/document.xml",
            params={"crtfc_key": _key(), "rcept_no": rcept_no},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            xml_bytes = zf.read(zf.namelist()[0])
    except Exception:
        return []

    try:
        rcept_date = _dt.datetime.strptime(rcept_dt.replace("-", ""), "%Y%m%d").date()
    except ValueError:
        return []

    lags = []
    for m in _MDF_DM_RE.finditer(xml_bytes):
        try:
            change_dt = _dt.datetime.strptime(m.group(1).decode(), "%Y%m%d").date()
        except ValueError:
            continue
        lags.append((rcept_date - change_dt).days)
    return lags


def _parse_int(s: str) -> int:
    try:
        return int(s.replace(",", ""))
    except (ValueError, AttributeError):
        return 0


def _parse_float(s: str) -> float:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


# ── Recent feed (all companies) ────────────────────────────────────────────────

def get_recent_kr_insider_feed(
    days: int = 30, max_corps: int = 20, bgn_de: str | None = None, end_de: str | None = None,
) -> list[dict]:
    """
    Recent KR insider disclosures across all KOSPI/KOSDAQ companies.
    Step 1: OpenDART /list.json for recent 임원·주요주주 소유보고서
    Step 2: Parallel elestock fetch per unique corp

    bgn_de/end_de (YYYYMMDD): explicit window override for historical backfill —
    omit to keep the default "today minus `days`" live-feed behavior.
    """
    import datetime as _dt
    if end_de is None:
        end_de = _dt.date.today().strftime("%Y%m%d")
    if bgn_de is None:
        bgn_de = (_dt.date.today() - _dt.timedelta(days=days)).strftime("%Y%m%d")

    list_r = requests.get(
        f"{DART_BASE}/list.json",
        params={
            "crtfc_key": _key(),
            "bgn_de": bgn_de,
            "end_de": end_de,
            # D002 = 임원ㆍ주요주주특정증권등소유상황보고서 (B001은 주요사항보고서라 완전 다른 공시)
            "pblntf_ty": "D",
            "pblntf_detail_ty": "D002",
            "sort": "date",
            "sort_mth": "desc",
            "page_no": 1,
            "page_count": 60,
        },
        timeout=_TIMEOUT,
    )
    list_r.raise_for_status()
    data = list_r.json()
    if data.get("status") != "000":
        return []

    # Deduplicate by corp_code, keep first (most recent) occurrence
    seen: dict[str, dict] = {}
    for disc in data.get("list", []):
        code = disc.get("corp_code", "")
        if code and code not in seen:
            seen[code] = {
                "corp_code": code,
                "corp_name": disc.get("corp_name", ""),
                "stock_code": disc.get("stock_code", ""),
            }
        if len(seen) >= max_corps:
            break

    def _fetch(corp: dict) -> list[dict]:
        rows = get_executive_stock_changes(corp["corp_code"], bgn_de, end_de)
        for r in rows:
            r["stock_code"] = corp["stock_code"]
        return rows

    results: list[dict] = []
    pool = ThreadPoolExecutor(max_workers=5)
    try:
        futures = {pool.submit(_fetch, corp): corp for corp in seen.values()}
        for fut in as_completed(futures, timeout=45):
            try:
                results.extend(fut.result())
            except Exception:
                pass
    except TimeoutError:
        pass
    finally:
        # bare `with` here would block __exit__ on shutdown(wait=True) until every
        # straggler finishes, silently defeating the 45s timeout above (observed 162s
        # wall time in production). cancel_futures drops unstarted work immediately;
        # already-running fetches finish on their own without blocking this response.
        pool.shutdown(wait=False, cancel_futures=True)

    return sorted(results, key=lambda x: x.get("rcept_dt", ""), reverse=True)


def action_weight(trade_type: str, report_nm: str = "") -> float:
    """매수 비중 배율 — 시그널 강도 기반.
    소각(주식수 영구 감소)=최강, 직접취득=기본, 신탁계약(실매입 불확실)=약함."""
    if trade_type == "CANCELLATION":
        return 1.5
    if trade_type == "BUYBACK":
        return 0.6 if "신탁" in report_nm else 1.0
    return 1.0


def get_recent_kr_corporate_actions(
    days: int = 30, max_items: int = 40, bgn_de: str | None = None, end_de: str | None = None,
) -> list[dict]:
    """매매 판단에 영향 주는 기업행위만: 유상/무상증자, 자기주식 취득/소각.
    소유상황보고(보유자 보고)는 제외. DART list.json을 report_nm으로 필터.

    bgn_de/end_de (YYYYMMDD): explicit window override for historical backfill —
    omit to keep the default "today minus `days`" live-feed behavior.
    """
    import datetime as _dt
    if end_de is None:
        end_de = _dt.date.today().strftime("%Y%m%d")
    if bgn_de is None:
        bgn_de = (_dt.date.today() - _dt.timedelta(days=days)).strftime("%Y%m%d")

    def _classify(nm: str) -> str | None:
        if "무상증자" in nm:
            return "RIGHTS_ISSUE"
        if "유상증자" in nm:
            return "PAID_IN"
        if "자기주식" in nm or "자사주" in nm:
            if "소각" in nm:
                return "CANCELLATION"
            if "처분" in nm or "해지" in nm:  # 버프백 종료/매도성 — 호재 아님
                return "DISPOSAL"
            return "BUYBACK"
        return None

    out: list[dict] = []
    seen: set[str] = set()
    for page in (1, 2, 3):
        try:
            r = requests.get(
                f"{DART_BASE}/list.json",
                params={"crtfc_key": _key(), "bgn_de": bgn_de, "end_de": end_de,
                        "sort": "date", "sort_mth": "desc", "page_no": page, "page_count": 100},
                timeout=_TIMEOUT,
            )
            data = r.json()
        except Exception:
            break
        if data.get("status") != "000":
            break
        rows = data.get("list", [])
        for d in rows:
            nm = d.get("report_nm", "")
            ttype = _classify(nm)
            if not ttype:
                continue
            rcept = d.get("rcept_no", "")
            if rcept in seen:
                continue
            seen.add(rcept)
            out.append({
                "trade_date": d.get("rcept_dt", ""),
                "reporter": d.get("corp_name", ""),
                "corp_name": d.get("corp_name", ""),
                "ticker": d.get("stock_code", "") or None,
                "trade_type": ttype,
                "report_type": nm,
                "event_cause": nm,
                "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept}" if rcept else None,
            })
            if len(out) >= max_items:
                return out
        if len(rows) < 100:
            break
    return out
