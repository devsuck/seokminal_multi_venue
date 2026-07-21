#!/usr/bin/env python3
"""KIS(한국투자증권) 해외 클라우드 IP 연결 테스트 — 클라우드 이전의 최대 관문 검증.

목적: 오라클(또는 임의 해외) VM에서 이 스크립트를 돌려서, KIS OAuth 토큰
엔드포인트가 **해외 IP에서도 응답하는지**를 즉시 판정한다. 한국 broker API가
해외 IP를 막거나 다르게 굴 수 있는데(미검증 리스크), 그러면 dart_bot 같은
KIS 의존 봇이 클라우드에서 깨진다. 데이터/봇 전체를 옮기기 **전에** 이걸로
go/no-go를 먼저 가른다.

의존성: requests, (선택) python-dotenv. 레포 패키지 설치 전에도 단독 실행 가능.

실행:
    # .env가 같은 디렉토리나 상위(레포 루트)에 있으면 자동 로드
    python3 scripts/deploy/test_kis_connectivity.py
    # 또는 환경변수 직접 주입
    KIS_MOCK_APP_KEY=... KIS_MOCK_APP_SECRET=... python3 scripts/deploy/test_kis_connectivity.py

읽는 환경변수(있는 것만 테스트):
    모의(mock):  KIS_MOCK_APP_KEY, KIS_MOCK_APP_SECRET   -> https://openapivts.koreainvestment.com:29443
    실전(live):  KIS_APP_KEY,      KIS_APP_SECRET        -> https://openapi.koreainvestment.com:9443

판정:
    PASS  = 토큰 정상 수신(해외 IP OK)
    FAIL  = 타임아웃/연결거부(방화벽·IP차단 의심) 또는 KIS 에러코드 응답
    SKIP  = 해당 자격증명이 .env에 없음
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

MOCK_URL = "https://openapivts.koreainvestment.com:29443"
LIVE_URL = "https://openapi.koreainvestment.com:9443"
TIMEOUT_S = 20


def _load_dotenv() -> None:
    """레포 루트/현재 디렉토리의 .env를 best-effort 로드. python-dotenv 없으면 수동 파싱."""
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]
    env_path = next((p for p in candidates if p.exists()), None)
    if env_path is None:
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        print(f"[info] .env 로드: {env_path}")
        return
    except ImportError:
        pass
    # python-dotenv 미설치 시 최소 파싱
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    print(f"[info] .env 수동 파싱 로드: {env_path}")


def _fetch_token(label: str, base_url: str, app_key: str, app_secret: str) -> bool:
    """KIS /oauth2/tokenP 호출. 성공하면 True. 결과/진단을 사람이 읽게 출력."""
    print(f"\n=== [{label}] {base_url} ===")
    try:
        resp = requests.post(
            f"{base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": app_key,
                "appsecret": app_secret,
            },
            timeout=TIMEOUT_S,
        )
    except requests.exceptions.Timeout:
        print(f"  ❌ FAIL — {TIMEOUT_S}s 타임아웃. 해외 IP 차단/방화벽 의심(=이전 시 dart_bot 깨짐).")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"  ❌ FAIL — 연결 실패({type(e).__name__}). 해외 IP 차단/네트워크 의심.")
        print(f"     detail: {str(e)[:200]}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ FAIL — 예상외 예외 {type(e).__name__}: {str(e)[:200]}")
        return False

    if resp.status_code == 200:
        try:
            payload = resp.json()
        except ValueError:
            print(f"  ⚠️  HTTP 200인데 JSON 아님(프록시/차단 페이지 의심): {resp.text[:200]}")
            return False
        if payload.get("access_token"):
            exp = payload.get("expires_in")
            print(f"  ✅ PASS — 토큰 정상 수신(해외 IP OK). expires_in={exp}s")
            return True
        # 200이지만 KIS 에러 바디(rt_cd/msg_cd/msg1)
        print(f"  ❌ FAIL — HTTP 200이나 토큰 없음. KIS 응답: {payload}")
        return False

    # 비200 — IP 차단은 종종 403/기타로도 나타남
    print(f"  ❌ FAIL — HTTP {resp.status_code}")
    print(f"     body: {resp.text[:300]}")
    if resp.status_code in (401, 403):
        print("     힌트: 401/403은 (a)자격증명 오류 (b)해외 IP 차단 둘 다 가능 — "
              "로컬(맥)에서 같은 키로 이 스크립트 돌려 PASS면 IP 차단 확정.")
    return False


def main() -> int:
    _load_dotenv()
    print("\nKIS 해외 IP 연결 테스트 — 목적: 이 VM의 IP에서 KIS가 응답하는지 판정")
    print("(로컬 맥에서도 한 번 돌려 비교하면 'IP 차단'인지 '자격증명 문제'인지 확정됨)")

    results: list[tuple[str, str]] = []

    mock_key = os.environ.get("KIS_MOCK_APP_KEY", "")
    mock_secret = os.environ.get("KIS_MOCK_APP_SECRET", "")
    if mock_key and mock_secret:
        ok = _fetch_token("모의(dart_bot이 실제 쓰는 것)", MOCK_URL, mock_key, mock_secret)
        results.append(("모의", "PASS" if ok else "FAIL"))
    else:
        print("\n=== [모의] SKIP — KIS_MOCK_APP_KEY/SECRET 없음 ===")
        results.append(("모의", "SKIP"))

    live_key = os.environ.get("KIS_APP_KEY", "")
    live_secret = os.environ.get("KIS_APP_SECRET", "")
    if live_key and live_secret:
        ok = _fetch_token("실전", LIVE_URL, live_key, live_secret)
        results.append(("실전", "PASS" if ok else "FAIL"))
    else:
        print("\n=== [실전] SKIP — KIS_APP_KEY/SECRET 없음 ===")
        results.append(("실전", "SKIP"))

    print("\n" + "=" * 50)
    print("판정 요약:")
    for label, verdict in results:
        print(f"  {label:6} -> {verdict}")

    tested = [v for _, v in results if v != "SKIP"]
    if not tested:
        print("\n⚠️  테스트할 자격증명이 하나도 없음. .env에 KIS_MOCK_APP_KEY 등을 넣고 다시 실행.")
        return 2
    if all(v == "PASS" for v in tested):
        print("\n✅ 전체 PASS — KIS가 이 VM의 해외 IP에서 정상. 클라우드 이전 KIS 관문 통과.")
        return 0
    print("\n❌ 일부/전체 FAIL — 위 진단 참고. 로컬 맥에서 같은 키로 돌려 비교 후 IP차단 여부 확정할 것.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
