"""가설 포트폴리오 레지스트리 — 엣지 메타-대시보드의 단일 소스.

플랫폼의 모든 엣지 가설을 한 곳에 나열해 대시보드가 "내 엣지들 중 지금 뭐가
살아있나"를 통째로 보게 한다. `warmable=True`는 라이브 데이터 없이(또는 저장된
수집데이터로) `load_and_report()`가 서버에서 바로 돌아가는 것(현재 폴리마켓 2종).
나머지는 맥에서 데이터 조립/백테스트가 필요해 대시보드엔 등록만 되고 상태는
'pending'으로 표시된다(수집기가 돌며 데이터가 쌓이면 warmable로 승격).

순수 메타데이터만 — import·실행 부작용 없음.
"""
from __future__ import annotations

# key → 메타. validator=load_and_report 보유 모듈(warmable) 또는 None.
HYPOTHESES: dict[str, dict] = {
    "polymarket_sharp_wallet": {
        "title": "샤프월렛 컨버전스",
        "category": "polymarket",
        "data_source": "Data-API /trades (공식 리더보드 top50)",
        "validator": "research.run_polymarket_sharp_wallet_validate",
        "warmable": True,
    },
    "polymarket_whale": {
        "title": "Whale 트래킹",
        "category": "polymarket",
        "data_source": "Data-API /trades (대형 체결)",
        "validator": "research.run_polymarket_whale_validate",
        "warmable": True,
    },
    "mlb_specialist_consensus": {
        "title": "MLB 스페셜리스트 컨센서스",
        "category": "sports",
        "data_source": "Data-API MLB 마켓 체결/정산",
        "validator": "research.run_mlb_specialist_validate",
        "warmable": True,   # load_and_report() 완성 + 수집기 상시구동 중(맥 작업 완료)
    },
    "cross_venue_skew": {
        "title": "크로스벤뉴 스큐",
        "category": "orderflow",
        "data_source": "HL/Binance/OKX 오더북 임밸런스",
        "validator": "research.run_cross_venue_skew_validate",
        "warmable": False,
    },
    "orderflow_futures": {
        "title": "선물 오더플로우 6종",
        "category": "orderflow",
        "data_source": "NQ/MNQ footprint/absorption/CVD",
        "validator": None,
        "warmable": False,
    },
    "gold_haven": {
        "title": "금 안전자산(실질금리 게이트)",
        "category": "macro",
        "data_source": "GC 인트라데이 + 실질금리 레짐",
        "validator": None,
        "warmable": False,
    },
    "tsmom": {
        "title": "멀티에셋 TSMOM",
        "category": "factor",
        "data_source": "멀티에셋 인트라데이",
        "validator": None,
        "warmable": False,
    },
    "funding_strategies": {
        "title": "펀딩 전략",
        "category": "crypto",
        "data_source": "perp 펀딩 시계열",
        "validator": None,
        "warmable": False,
    },
}


def warmable_runners() -> dict[str, str]:
    """warmable 가설의 key → validator 모듈 경로(서버 워밍 대상)."""
    return {k: v["validator"] for k, v in HYPOTHESES.items()
            if v["warmable"] and v["validator"]}


def registry_list() -> list[dict]:
    """대시보드용 정렬 리스트(warmable 먼저, 그다음 key)."""
    return [{"key": k, **v} for k, v in sorted(
        HYPOTHESES.items(), key=lambda kv: (not kv[1]["warmable"], kv[0]))]
