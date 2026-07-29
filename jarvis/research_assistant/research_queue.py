"""Research Queue Engine (P58) — Jarvis 가 **다음에 가치 있는 연구**를 제안한다. **분석·제안만, 결정·집행 없음.**

지금까지: 사람이 연구 질문을 던진다. 이제: Jarvis 가 축적 메모리에서 연구 후보를 결정적으로 도출한다.
입력 = 시장 레짐·최근 이벤트·기존 메모리·과거 실패·미탐색 조합. 출력 = Research Opportunity Queue.

원칙(문서 §Constitution, §P58):
  · **새 DB 없음.** 기존 원장(experiment_tracking/rmi)을 READ ONLY 로 읽는 ResearchAssistantEngine 재사용.
  · 제안은 자문일 뿐 — **사람 승인 없이는 실행되지 않는다**(requires_human_approval=True).
  · 결정적(LLM/랜덤 없음). 거래·집행·배포·자본배분 없음.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

from jarvis.research_assistant import models as M

LOW, MEDIUM, HIGH = "LOW", "MEDIUM", "HIGH"
K_COMBINATION, K_FAILURE_FIX, K_REGIME, K_EVENT = ("COMBINATION", "FAILURE_FIX",
                                                   "REGIME", "EVENT")

# 신호 토큰 추출 시 제외할 잡음(버전·일반어)
_STOP = frozenset({
    "the", "and", "for", "with", "test", "backtest", "strategy", "run", "exp",
    "experiment", "research", "signal", "model", "v1", "v2", "v3", "version",
    "reval", "revalidated", "demo", "synthetic", "unknown", "daily", "min",
    "long", "short", "cross", "flat", "gated", "simple",
})


def _proposal_id(name: str) -> str:
    return "RQP:" + hashlib.sha1(name.strip().lower().encode()).hexdigest()[:12]


def _tokens(text: str) -> set:
    out = set()
    for w in re.split(r"[^a-z0-9]+", (text or "").lower()):
        if len(w) >= 3 and w not in _STOP and not w.isdigit():
            out.add(w)
    return out


@dataclass(frozen=True)
class ResearchProposal:
    proposal_id: str
    name: str
    kind: str                    # COMBINATION | FAILURE_FIX | REGIME | EVENT
    reason: str
    confidence: str              # LOW | MEDIUM | HIGH
    expected_value: str          # LOW | MEDIUM | HIGH
    basis: list = field(default_factory=list)     # 근거(원장 참조·근거 수)
    requires_human_approval: bool = True
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResearchQueue:
    timestamp: str
    proposal_count: int
    by_kind: dict
    proposals: list = field(default_factory=list)
    requires_human_approval: bool = True
    disclaimer: str = ("Research Opportunity Queue — 제안일 뿐 사람 승인 전 실행 없음. "
                       "Jarvis proposes; humans decide.")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["proposals"] = [p.to_dict() if isinstance(p, ResearchProposal) else p
                          for p in self.proposals]
        return d


class ResearchQueueEngine:
    """다음 연구 후보 도출기. ResearchAssistantEngine(READ ONLY) 재사용. 실행 권한 없음."""

    def __init__(self, assistant=None, reader=None) -> None:
        if assistant is None:
            from jarvis.research_assistant.engine import ResearchAssistantEngine
            assistant = ResearchAssistantEngine(reader)
        self._asst = assistant

    # ── 실험 → 신호 토큰 집합 ──
    def _experiment_token_sets(self) -> list:
        sets = []
        for src in ("experiments", "experiment_runs"):
            for rec in self._asst._read(src):
                name = M.first_field(rec, ("name", "title", "objective", "note", "code_version"))
                toks = _tokens(name)
                if toks:
                    sets.append(toks)
        return sets

    def _unexplored_combinations(self, limit: int) -> list:
        """개별로 시도된 신호쌍 중 함께 시도되지 않은 조합 제안(결정적)."""
        token_sets = self._experiment_token_sets()
        freq: dict = {}
        co: set = set()
        for s in token_sets:
            for tkn in s:
                freq[tkn] = freq.get(tkn, 0) + 1
            for a in s:
                for b in s:
                    if a < b:
                        co.add((a, b))
        # 상위 빈도 신호만(경계·결정적)
        top = [t for t, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:6]]
        out = []
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                a, b = sorted((top[i], top[j]))
                if (a, b) in co:
                    continue    # 이미 함께 시도됨
                name = f"{a.title()} + {b.title()} Combination"
                out.append(ResearchProposal(
                    proposal_id=_proposal_id(name), name=name, kind=K_COMBINATION,
                    reason=(f"개별 신호 '{a}'({freq[a]}건)·'{b}'({freq[b]}건)는 시도됨. "
                            f"조합은 미탐색."),
                    confidence=MEDIUM, expected_value=HIGH,
                    basis=[f"{a}:{freq[a]}", f"{b}:{freq[b]}"]))
        out.sort(key=lambda p: (-sum(int(x.split(':')[1]) for x in p.basis), p.name))
        return out[:limit]

    def _failure_driven(self, limit: int) -> list:
        fi = self._asst.failure_intelligence()
        out = []
        for cat, n in list(fi.by_category.items())[:limit]:
            if cat == M.FAIL_UNCLASSIFIED:
                continue
            name = f"{cat.replace('_', ' ').title()}-robust variant"
            out.append(ResearchProposal(
                proposal_id=_proposal_id(name + cat), name=name, kind=K_FAILURE_FIX,
                reason=f"과거 실패 유형 {cat} {n}건 — 이 취약점을 겨냥한 강건화 연구.",
                confidence=HIGH if n >= 3 else MEDIUM, expected_value=MEDIUM,
                basis=[f"{cat}:{n}"]))
        return out

    def _regime_driven(self, regime: str) -> list:
        if not str(regime or "").strip():
            return []
        name = f"{str(regime).strip().title()} regime-fit study"
        return [ResearchProposal(
            proposal_id=_proposal_id(name), name=name, kind=K_REGIME,
            reason=f"현재 레짐 '{regime}' 에 적합한 신호·파라미터 재평가.",
            confidence=MEDIUM, expected_value=MEDIUM, basis=[f"regime:{regime}"])]

    def _event_driven(self, events) -> list:
        out = []
        for ev in (events or []):
            if isinstance(ev, dict):
                cand = ev.get("name") or ev.get("candidate") or ev.get("entity")
                reason = ev.get("reason", "이벤트 파생 연구 후보.")
                conf = str(ev.get("confidence", MEDIUM)).upper()
            else:
                cand, reason, conf = str(ev), "이벤트 파생 연구 후보.", MEDIUM
            if not cand:
                continue
            name = f"{cand} event-driven study"
            out.append(ResearchProposal(
                proposal_id=_proposal_id(name), name=name, kind=K_EVENT, reason=reason,
                confidence=conf if conf in (LOW, MEDIUM, HIGH) else MEDIUM,
                expected_value=HIGH, basis=[f"event:{cand}"]))
        return out

    def generate(self, regime=None, events=None, *, limit=10) -> ResearchQueue:
        """연구 기회 큐 생성. 미탐색 조합 + 실패 강건화 + 레짐 + 이벤트. 결정적. 사람 승인 필요."""
        proposals = []
        proposals += self._event_driven(events)
        proposals += self._unexplored_combinations(limit)
        proposals += self._failure_driven(limit)
        proposals += self._regime_driven(regime)
        # 이미 메모리에 강하게 존재하는 제안은 후순위(중복 회피)
        seen = {}
        ranked = []
        rank = {HIGH: 0, MEDIUM: 1, LOW: 2}
        for p in proposals:
            if p.proposal_id in seen:
                continue
            seen[p.proposal_id] = True
            ranked.append(p)
        ranked.sort(key=lambda p: (rank[p.expected_value], rank[p.confidence], p.name))
        ranked = ranked[:limit]
        by_kind: dict = {}
        for p in ranked:
            by_kind[p.kind] = by_kind.get(p.kind, 0) + 1
        ts = getattr(self, "_now", "")
        return ResearchQueue(timestamp=ts, proposal_count=len(ranked),
                             by_kind=dict(sorted(by_kind.items())), proposals=ranked)

    def record_proposals(self, queue: ResearchQueue, now="", *, commit=False) -> list:
        """제안을 기존 자문 노트 원장(ras_)에 append(비구속). **새 저장소 없음. 사람 승인 필요.**"""
        out = []
        for p in queue.proposals:
            rec = self._asst.record_advisory(
                area=p.name, rationale=p.reason, evidence_count=len(p.basis),
                now=now, commit=commit)
            out.append(rec.to_dict() if hasattr(rec, "to_dict") else rec)
        return out
