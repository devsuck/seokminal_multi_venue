"""Research Feed Scheduler (P117) — 가용 정보를 주기적으로 수집하는 파이프라인. **자동 투자 없음.**

Flow: Data Source → Event → Research Trigger → Opportunity Queue. 요구사항: configurable interval·
retry handling·source health check·duplicate prevention. **재사용**: providers(P112)·각 pipeline(P113-116)·
research_trigger.dispatch(P101)·opportunity_discovery(P88). 새 저장소/원장 없음.

주의: 실제 주기 실행(백그라운드 루프)은 없다 — 결정적 단일 패스 수집기이며, 주기는 외부(cron/사람)가 호출.
**자동 투자 행위 없음.** 원칙(문서 §Constitution, §P117): 통합·조율만. 결정적. 거래·집행 없음.
"""
from __future__ import annotations

from jarvis.research_workflow import models as M

# 카테고리 → 파이프라인 run + 이벤트 추출기
_PIPELINES = {
    "market": ("jarvis.research_workflow.market_pipeline", "market_events"),
    "news": ("jarvis.research_workflow.news_pipeline", "news_events"),
    "fundamental": ("jarvis.research_workflow.fundamental_pipeline", "fundamental_candidates"),
    "ownership": ("jarvis.research_workflow.ownership_pipeline", "ownership_events"),
}


def _retry(fn, *, max_retries: int = 2):
    """결정적 retry 래퍼 — 예외 시 재시도(최대 max_retries). 마지막 실패면 None + error."""
    last = None
    for _ in range(max(1, max_retries + 1)):
        try:
            return fn(), None
        except Exception as e:  # noqa: BLE001
            last = str(e)
    return None, last


class ResearchFeedPipeline:
    """연구 피드 수집기 — health·retry·dedup 후 이벤트→트리거→기회큐. 실행하지 않는다, 관찰만."""

    def __init__(self, *, interval_seconds: int = 900, max_retries: int = 2) -> None:
        self.interval_seconds = int(interval_seconds)
        self.max_retries = int(max_retries)

    def schedule(self) -> dict:
        """수집 스케줄 메타(읽기전용) — 주기·재시도. 실제 실행은 외부(cron/사람)."""
        return {"interval_seconds": self.interval_seconds, "max_retries": self.max_retries,
                "categories": list(_PIPELINES), "auto_execution": False,
                "note": "주기는 메타데이터 — 자동 투자 행위 없음, 외부에서 호출."}

    def collect(self, sources: dict | None = None, *, seen: set | None = None, assistant=None) -> dict:
        """{category: raw_list} → health·retry·dedup → 이벤트 → research_trigger → 기회큐. 결정적."""
        src = sources or {}
        seen_hashes = set(seen or set())
        from jarvis.research_workflow.providers import provider_for
        collected, health, dropped_dupes, errors = [], [], 0, []

        for category, raw_list in src.items():
            prov = provider_for(category)
            health.append(prov.health_check())
            mod_name, _ = _PIPELINES.get(category, (None, None))
            if not mod_name:
                errors.append({"category": category, "error": "unknown category"})
                continue
            run = getattr(__import__(mod_name, fromlist=["run"]), "run")
            out, err = _retry(lambda: run(list(raw_list or []), assistant=assistant),
                              max_retries=self.max_retries)
            if err or out is None:
                errors.append({"category": category, "error": err or "no output"})
                continue
            # 이벤트 추출 + 중복 방지(콘텐츠 해시)
            for ev in _extract_events(category, out):
                h = M.input_digest("feed", category, ev.get("origin") or ev.get("company")
                                   or ev.get("asset") or ev.get("headline"), ev.get("event_type")
                                   or ev.get("transaction") or ev.get("overall_surprise"))
                if h in seen_hashes:
                    dropped_dupes += 1
                    continue
                seen_hashes.add(h)
                collected.append({"category": category, "event_hash": h, "event": ev})

        # 이벤트 → Research Trigger → Opportunity Queue
        opportunities = []
        if assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            assistant = ResearchAssistantEngine()
        from jarvis.research_workflow.research_trigger import dispatch
        for c in collected[:50]:
            ev = c["event"]
            trig_event = {"kind": _kind_for(c["category"]),
                          "entity": ev.get("origin") or ev.get("company") or ev.get("asset") or "",
                          "text": ev.get("headline") or ev.get("event_type") or c["category"]}
            d = dispatch(trig_event, assistant=assistant, limit=2)
            opportunities.extend(d.get("opportunity_candidates", []))

        return {"collected": collected, "collected_count": len(collected),
                "dropped_duplicates": dropped_dupes, "provider_health": health, "errors": errors,
                "opportunity_queue": opportunities, "opportunity_count": len(opportunities),
                "schedule": self.schedule(),
                "requires_human_review": True, "is_advisory": True, "is_decision": False,
                "note": ("연구 피드(읽기전용) — Source→Event→Trigger→Opportunity Queue. 중복 방지·retry·health. "
                         "자동 투자 행위 없음, 새 저장소 없음.")}


def _kind_for(category: str) -> str:
    return {"market": "market", "news": "news", "fundamental": "earnings",
            "ownership": "insider"}.get(category, "news")


def _extract_events(category: str, out: dict) -> list:
    """파이프라인 산출 → 개별 이벤트 리스트(카테고리별 키). 결정적."""
    if category == "market":
        return out.get("market_events", []) or []
    if category == "news":
        return out.get("events", []) or []
    if category == "fundamental":
        return out.get("research_candidates", []) or []
    if category == "ownership":
        return out.get("ownership_events", []) or []
    return []


def collect(sources: dict | None = None, *, interval_seconds: int = 900, max_retries: int = 2,
            seen: set | None = None, assistant=None) -> dict:
    """모듈 진입점 — ResearchFeedPipeline.collect 래퍼."""
    return ResearchFeedPipeline(interval_seconds=interval_seconds,
                                max_retries=max_retries).collect(sources, seen=seen, assistant=assistant)
