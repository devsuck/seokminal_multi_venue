"""Market Memory — 거부전략·편향함정·시장/패밀리 교훈. append-only.

Research Agent는 새 가설 제안 전 consult()로 유사 거부사례를 확인해야 한다.
유사하면 '왜 다른가'를 명시하도록 강제(에이전트 로직에서).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from jarvis.config import state_path

_MEM = "market_memory.jsonl"


# 실제 검증에서 나온 교훈(시드).
_SEED = [
    {"lesson_id": "KR_LIQUIDITY_WAVE_SURVIVORSHIP", "category": "bias_control",
     "summary": "KR 유동성 웨이브 = survivor-only에선 약양(+2.28%), KRX PIT(상폐 포함)에선 net -1.66%, random 0.2pct. 생존편향 산물.",
     "implication": "KR 소형주 이벤트 전략은 상폐/정지 포함 필수 or sanity_check_only.",
     "related_strategies": ["KR_LIQUIDITY_WAVE_V1"]},
    {"lesson_id": "KR_PURE_MOMENTUM_REJECT", "category": "family_lesson",
     "summary": "KOSDAQ 순수 12-1 모멘텀 = 랜덤 3pct(랜덤보다 나쁨). 소형주 반전 강함.",
     "implication": "KR 가격패턴 모멘텀 트랙 폐기. 엣지는 공시/공급 이벤트에.",
     "related_strategies": ["kr_pure_momentum_v1"]},
    {"lesson_id": "US_INTRADAY_TECH_REJECT", "category": "family_lesson",
     "summary": "US 인트라데이 기술패턴(ORB/VWAP-MR/gap/ATR/sector) 6가설 전부 REJECT — wrong-frequency.",
     "implication": "US 인트라데이 재량패턴 = TradingView. 검증 트랙 아님.",
     "related_strategies": ["orb_rvol_vwap", "vwap_mean_reversion", "gap_continuation"]},
    {"lesson_id": "HL_FUNDING_REJECT", "category": "family_lesson",
     "summary": "HL 펀딩 하베스트 = 펀딩 실재하나 HL 비용/빈도가 엣지 죽임. delta-neutral BLOCKED.",
     "implication": "펀딩 트랙 폐기.",
     "related_strategies": ["cross_sectional_funding", "funding_extreme_reversal"]},
    {"lesson_id": "BUYBACK_RIGHT_TAIL", "category": "execution_lesson",
     "summary": "KR buyback = net +1.73% random 97pct(p=0.032) 통과. 근데 right-tail 의존, median 근0, next_open 타이밍 민감.",
     "implication": "size/purpose 필터 금지(clean gradient 없음). v2는 execution/risk만.",
     "related_strategies": ["KR_BUYBACK_V1"]},
    {"lesson_id": "TSMOM_FIRST_EDGE", "category": "family_lesson",
     "summary": "선물 TSMOM 13→32시장 = 첫 엣지 후보(Sharpe 0.56, random 95.5pct, WF 안정, cost-robust).",
     "implication": "v1 동결. v2 = breadth 40~60 + 장기데이터. 레짐은 forward 후.",
     "related_strategies": ["futures_tsmom_32mkt"]},
]


class MarketMemory:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or state_path(_MEM)

    def all(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def add_lesson(self, lesson: dict) -> dict:
        row = {"added_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **lesson}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return row

    def consult(self, keywords: list[str]) -> list[dict]:
        """키워드로 유사 교훈 검색(제안 전 조회용)."""
        kws = [k.lower() for k in keywords if k]
        out = []
        for m in self.all():
            blob = json.dumps(m, ensure_ascii=False).lower()
            if any(k in blob for k in kws):
                out.append(m)
        return out


def seed_lessons(mem: MarketMemory | None = None) -> int:
    """시드 교훈 주입(idempotent, lesson_id 중복 방지)."""
    mem = mem or MarketMemory()
    have = {m.get("lesson_id") for m in mem.all()}
    added = 0
    for l in _SEED:
        if l["lesson_id"] not in have:
            mem.add_lesson(l); added += 1
    return added
