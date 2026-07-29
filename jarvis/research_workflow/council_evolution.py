"""Research Council Evolution (P90) — 기존 협의체를 **7개 관점**으로 확장한다. **논거만, 결정 없음.**

기존 6렌즈(Quant/Risk/Macro/Supply/News/Critic)를 재사용하고, 누락 관점(Industry/Behavioral/Contrarian/
Portfolio)을 결정적 신호로 주입해 7관점(Quant/Macro/Industry/Behavioral/Risk/Contrarian/Portfolio)을 만든다.
**에이전트는 결정하지 않는다 — 논거를 낸다.** 새 에이전트를 만들지 않고 기존 council 을 확장한다.

원칙(문서 §Constitution, §P90): 통합·재사용. 결정적. 거래·집행 없음 — 사람 검토 필수.
"""
from __future__ import annotations

_EXPANDED = ("Quant", "Macro", "Industry", "Behavioral", "Risk", "Contrarian", "Portfolio")


def _derive_lenses(assistant, topic) -> dict:
    """누락 관점(Industry/Behavioral/Contrarian/Portfolio)을 기존 데이터에서 결정적으로 도출."""
    signals: dict = {}
    try:
        rc = assistant.recall(topic)
        hits = rc.total_hits
        mc = assistant.mistake_check(topic)
        fails = mc.get("failure_count", 0)
    except Exception:  # noqa: BLE001
        hits, fails = 0, 0
    # Industry — 관련 축적 기록 기반
    signals["Industry"] = {"stance": "INFO" if hits else "NEUTRAL",
                           "rationale": f"산업/섹터 관련 축적 기록 {hits}건"}
    # Behavioral — 과거 실패(행동 편향 위험)
    signals["Behavioral"] = {"stance": "CAUTION" if fails else "NEUTRAL",
                             "rationale": (f"과거 실패 {fails}건 — 확증편향·군집 위험" if fails
                                           else "행동 편향 신호 없음(신규 검증 필요)")}
    # Contrarian — 합의가 강할수록 역발상 경계
    signals["Contrarian"] = {"stance": "CAUTION" if hits >= 3 else "INFO",
                             "rationale": (f"관련 기록 {hits}건 — 붐빔/합의 위험, 역발상 점검" if hits >= 3
                                           else "합의 약함 — 역발상 근거 부족")}
    # Portfolio — 분산/집중 관점(기본 정보)
    signals["Portfolio"] = {"stance": "INFO",
                            "rationale": "포트폴리오 상관·집중 영향은 시뮬레이터(P92)로 확인 필요"}
    return signals


def deliberate(question, *, assistant=None, reader=None, extra_signals=None) -> dict:
    """7관점 협의체 심의(결정적). 기존 council.deliberate + 누락 관점 주입. 사람 결정 필요."""
    from jarvis.research_assistant.council import ResearchCouncilEngine
    from jarvis.research_assistant.models import extract_topic
    if assistant is None:
        from jarvis.research_assistant.engine import ResearchAssistantEngine
        assistant = ResearchAssistantEngine(reader)
    topic = extract_topic(question) or question
    signals = _derive_lenses(assistant, topic)
    if extra_signals:
        signals.update(extra_signals)
    memo = ResearchCouncilEngine(assistant=assistant).deliberate(question, signals=signals)
    d = memo.to_dict()
    d["expanded_perspectives"] = list(_EXPANDED)
    d["note"] = "7관점 협의체 — 에이전트는 논거만 생산, 결정은 사람. 기존 council 확장(새 에이전트 없음)."
    return d
