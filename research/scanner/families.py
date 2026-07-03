"""KR 이벤트 family 카탈로그 — 생성기(경제논리). DART 키워드 + 방향 + 레드팀 spec.

buyback이 유일하게 산 곳(자본구조/공급/신뢰 이벤트) → 형제들 스캔.
일부는 B피드 밖(대량보유·최대주주변경 = 수시/D) → 커버리지 낮으면 스캐너가 정직히 underpowered.
"""
from __future__ import annotations

FAMILIES = {
    # 이미 데이터 있음(캐시) — 스캐너 검증용
    "buyback": {"keywords": ["자기주식취득"], "exclude": ["처분"], "direction": "bullish",
                "event_type": None, "thesis": "자사주 매입=공급감소·저평가 신호(검증된 엣지)"},
    "buyback_cancel": {"keywords": ["소각", "이익소각"], "exclude": [], "direction": "bullish", "pblntf_ty": "B",
                       "event_type": None, "thesis": "자사주 소각=공급 영구감소(buyback보다 강할수도)"},
    # 새 family — pull 필요
    "capital_reduction": {"keywords": ["감자"], "exclude": ["무상증자"], "direction": "research",
                          "event_type": None, "thesis": "감자=부실정리 재평가 vs distress(방향 불명 → research)"},
    "spinoff": {"keywords": ["회사분할", "인적분할"], "exclude": ["합병"], "direction": "bullish",
                "event_type": None, "thesis": "인적분할=가치 언락"},
    # 흑자전환은 report_nm에 없음(잠정실적 본문) → 손익구조 30%↑ 변동 공시(I피드)로 대체.
    # 양방향(흑전+적전 혼합) → direction=research.
    "turn_to_profit": {"keywords": ["손익구조"], "exclude": [], "direction": "research", "pblntf_ty": "I",
                       "event_type": None, "thesis": "손익구조 30%↑ 급변=실적 서프라이즈(흑전/적전 혼합, 방향 불명)"},
    "supply_contract": {"keywords": ["단일판매", "공급계약"], "exclude": ["해지"], "direction": "bullish", "pblntf_ty": "I",
                        "event_type": None, "thesis": "대형 공급계약=매출 가시성"},
    "treasury_trust": {"keywords": ["신탁계약체결"], "exclude": ["해지"], "direction": "bullish",
                       "event_type": None, "thesis": "자사주 신탁=간접 매입 신호"},
    # ── S1 확장(사전등록·동결) ──────────────────────────────
    "treasury_disposal": {"keywords": ["자기주식처분"], "exclude": ["취득"], "direction": "bearish", "pblntf_ty": "B",
                          "event_type": None, "thesis": "자사주 처분=공급↑(buyback 거울, 공급/수요 방향축 확증)"},
    "control_change": {"keywords": ["최대주주변경", "경영권"], "exclude": [], "direction": "bullish", "pblntf_ty": "B",
                       "event_type": None, "thesis": "최대주주 변경=인수/경영권 프리미엄 기대"},
    "asset_transfer": {"keywords": ["자산양수도", "영업양수도"], "exclude": [], "direction": "research", "pblntf_ty": "B",
                       "event_type": None, "thesis": "자산·영업 양수도=구조조정 재평가(방향 불명 → research)"},
    "rights_issue": {"keywords": ["유상증자"], "exclude": ["무상"], "direction": "bearish", "pblntf_ty": "B",
                     "event_type": None, "thesis": "유상증자=신주 희석 악재(회피신호 확증)"},
}


def redteam_spec(fam_id: str, fam: dict) -> dict:
    """family → 레드팀 spec 특성."""
    return {"market": "KR", "family": "event", "entry": "next_open",
            "event_type": fam.get("event_type") or ""}
