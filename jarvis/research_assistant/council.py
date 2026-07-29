"""Agent Research Council (P59-60) — 기존 perspectives 를 **연구 협의체**로 승격. **분석·자문만, 결정·집행 없음.**

연구 질문 → 다관점(Quant/Risk/Macro/Supply/News/Critic) → 합의/상충 탐지 → 균형 잡힌 연구 메모.
**기존 에이전트(perspectives 렌즈)를 재사용** — 새 에이전트 중복 생성 없음. 선택적으로 외부 결정적 신호
(예: event_intelligence 공급망 리스크)를 렌즈에 주입해 근거를 보강할 수 있다.

원칙(문서 §Constitution, §P59-60):
  · **새 에이전트/DB 없음.** ResearchAssistantEngine.perspectives(6 렌즈) 재사용.
  · 결정적 합의/상충 탐지. 출력은 균형 메모(자문) — 사람 판단 필요.
  · 거래·집행·배포·자본배분 없음.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

_SUPPORTIVE = {"SUPPORT", "INFO"}
_CAUTIONARY = {"CAUTION", "OPPOSE"}

REC_CONFLICT = "CONFLICT — HUMAN REVIEW REQUIRED"
REC_CAUTION = "CAUTION — prior failures; human review before proceeding"
REC_PROCEED = "PROCEED TO VALIDATION (human-gated)"
REC_INSUFFICIENT = "INSUFFICIENT BASIS — form hypothesis / run experiment first"


@dataclass(frozen=True)
class CouncilMemo:
    question: str
    topic: str
    lenses: list                       # perspectives 렌즈(+주입 신호)
    supportive: list                   # 지지 렌즈 이름
    cautionary: list                   # 경계 렌즈 이름
    conflicts: list                    # {support, caution} 쌍
    consensus: bool
    recommendation: str
    memo: str                          # 사람이 읽는 균형 메모
    requires_human_judgment: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class ResearchCouncilEngine:
    """연구 협의체 — perspectives 재사용 + 합의/상충 종합 + 균형 메모. 실행 권한 없음."""

    def __init__(self, assistant=None, reader=None) -> None:
        if assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            assistant = ResearchAssistantEngine(reader)
        self._asst = assistant

    def _merge_signals(self, lenses: list, signals) -> list:
        """외부 결정적 신호로 렌즈 보강/추가(예: Supply=공급망 리스크). 값이 있으면 해당 렌즈 갱신."""
        if not signals:
            return lenses
        by_name = {ln["lens"]: dict(ln) for ln in lenses}
        for name, sig in (signals or {}).items():
            stance = str(sig.get("stance", "INFO")).upper() if isinstance(sig, dict) else "INFO"
            rationale = sig.get("rationale", "") if isinstance(sig, dict) else str(sig)
            entry = by_name.get(name, {"lens": name, "evidence": 0})
            entry.update({"lens": name, "stance": stance, "rationale": rationale})
            by_name[name] = entry
        # 원래 순서 유지 + 신규 추가
        order = [ln["lens"] for ln in lenses] + [n for n in by_name if n not in
                                                 {ln["lens"] for ln in lenses}]
        return [by_name[n] for n in order]

    def deliberate(self, question, *, signals=None) -> CouncilMemo:
        """질문 → 다관점 협의 → 합의/상충 → 균형 연구 메모. 결정적. 사람 판단 필요.

        signals(선택): {lens_name: {stance, rationale}} — event_intelligence 등 결정적 모듈의 근거 주입.
        """
        from jarvis.research_assistant import models as M
        topic = M.extract_topic(question) or (question or "").strip()
        persp = self._asst.perspectives(topic)
        lenses = self._merge_signals(list(persp["lenses"]), signals)

        supportive = [ln["lens"] for ln in lenses if ln.get("stance") in _SUPPORTIVE]
        cautionary = [ln["lens"] for ln in lenses if ln.get("stance") in _CAUTIONARY]
        support_strong = [ln["lens"] for ln in lenses if ln.get("stance") == "SUPPORT"]
        conflicts = []
        if support_strong and cautionary:
            for s in support_strong:
                for c in cautionary:
                    conflicts.append({"support": s, "caution": c})
        consensus = not conflicts and not ("OPPOSE" in {ln.get("stance") for ln in lenses})

        if conflicts:
            rec = REC_CONFLICT
        elif any(ln.get("stance") == "OPPOSE" for ln in lenses):
            rec = REC_CAUTION
        elif support_strong:
            rec = REC_PROCEED
        else:
            rec = REC_INSUFFICIENT

        memo = self._compose_memo(question, topic, lenses, supportive, cautionary,
                                  conflicts, rec)
        return CouncilMemo(
            question=question, topic=topic, lenses=lenses, supportive=supportive,
            cautionary=cautionary, conflicts=conflicts, consensus=bool(consensus),
            recommendation=rec, memo=memo)

    @staticmethod
    def _compose_memo(question, topic, lenses, supportive, cautionary, conflicts, rec) -> str:
        lines = [f"Research Memo — {question}", f"Topic: {topic or '(none)'}", ""]
        for ln in lenses:
            lines.append(f"  [{ln.get('stance', 'NEUTRAL'):8}] {ln['lens']}: "
                         f"{ln.get('rationale', '')}")
        lines.append("")
        lines.append(f"Supportive: {', '.join(supportive) or '—'}")
        lines.append(f"Cautionary: {', '.join(cautionary) or '—'}")
        if conflicts:
            pairs = "; ".join(f"{c['support']}↔{c['caution']}" for c in conflicts)
            lines.append(f"Conflicts: {pairs}")
        lines.append(f"Recommendation: {rec}")
        lines.append("(Balanced memo — advisory only; human decides. No execution.)")
        return "\n".join(lines)

    def record_memo(self, memo: CouncilMemo, now="", *, commit=False):
        """메모를 기존 자문 노트 원장(ras_)에 append(비구속). 새 저장소 없음. 사람 승인 필요."""
        return self._asst.record_advisory(
            area=f"council:{memo.topic or memo.question}", rationale=memo.recommendation,
            evidence_count=len(memo.supportive) + len(memo.cautionary), now=now, commit=commit)
