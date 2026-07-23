"""Governance Evolution Engine (P10.22) — 거버넌스 생태계 시간적 변화 관찰·분석·기록. **관찰·분석·기록 전용.**

P9.8~P10.21 연구 거버넌스 생태계를 READ ONLY 로 참조(파일 기반, import 없음)해 진화 이벤트·거버넌스 상태
타임라인·성숙도 평가·변화 패턴·역사적 비교·스냅샷·리포트·계보를 남긴다. **거버넌스 규칙 수정·변경 적용·업그
레이드 승인·config 변경·시스템 배포 없음.** execution/broker/order/portfolio execution/capital allocation/
live trading/permission/risk controller import·호출 없음. EVOLUTION ANALYSIS ≠ EVOLUTION ACTION · MATURITY
SCORE ≠ PERMISSION · TREND DETECTION ≠ CHANGE EXECUTION · RECOMMENDATION ≠ IMPLEMENTATION. 상위 파일은 읽기만.
"""
from __future__ import annotations

from jarvis.governance_evolution import ledger
from jarvis.governance_evolution.models import (
    ART_COMPARISON,
    ART_EVENT,
    ART_LAYER,
    ART_MATURITY,
    ART_PATTERN,
    ART_REPORT,
    ART_SNAPSHOT,
    ART_STATE,
    EVENT_TYPES,
    GENESIS,
    MATURITY_LEVELS,
    EvolutionArtifact,
    EvolutionEvent,
    EvolutionPattern,
    EvolutionReport,
    EvolutionSnapshot,
    EvolutionSummary,
    GovernanceStateEvent,
    HistoricalComparison,
    IllegalTransition,
    ImmutableEventError,
    ImmutableMaturityError,
    ImmutablePatternError,
    InvalidEventType,
    InvalidMaturityLevel,
    MaturityAssessment,
    UnknownState,
    artifact_id as _artifact_id,
    can_transition_state,
    comparison_id as _comparison_id,
    content_hash,
    detect_cycle,
    evolution_health,
    evolution_score,
    event_id as _event_id,
    input_digest,
    is_regression,
    level_index,
    maturity_id as _maturity_id,
    metadata_hash as _metadata_hash,
    overall_maturity,
    pattern_confidence,
    pattern_id as _pattern_id,
    report_id as _report_id,
    snapshot_hash as _snapshot_hash,
    snapshot_id as _snapshot_id,
    state_event_id,
    state_id as _state_id,
)

_DISCLAIMER = ("거버넌스 진화 분석 데이터 — EVOLUTION ANALYSIS ≠ EVOLUTION ACTION · MATURITY SCORE ≠ "
               "PERMISSION · TREND DETECTION ≠ CHANGE EXECUTION · RECOMMENDATION ≠ IMPLEMENTATION. "
               "업그레이드/마이그레이션/정책변경/배포/실행 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class GovernanceEvolutionEngine:
    """거버넌스 진화 인텔리전스 엔진. 불변·append-only·결정적. 실행/변경/승인/배포 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = EvolutionArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _ensure_layer_artifact(self, source_layer: str, now: str, *, commit: bool) -> str:
        return self._record_artifact(ART_LAYER, source_layer, "", now,
                                     commit=commit)["artifact_id"]

    # ── Evolution Event Registry (불변) ──
    def record_event(self, source_layer: str, event_type: str, description: str, now: str = "",
                   *, commit: bool = False) -> EvolutionEvent:
        """진화 이벤트를 불변 기록. event_type 검증. **관찰·기록만.**"""
        if event_type not in EVENT_TYPES:
            raise InvalidEventType(f"미등록 이벤트 유형 {event_type}")
        eid = _event_id(source_layer, event_type, description)
        mh = _metadata_hash({"event_type": event_type, "description": description})
        existing = ledger.get_event(eid)
        if existing is not None:
            if existing.get("metadata_hash") != mh:
                raise ImmutableEventError(f"{eid} 진화 이벤트 불변 — 변경 불가")
            return EvolutionEvent(**{k: v for k, v in existing.items()
                                     if k in EvolutionEvent.__dataclass_fields__})
        self._ensure_layer_artifact(source_layer, now, commit=commit)
        rec = EvolutionEvent(
            event_id=eid, source_layer=source_layer, event_type=event_type,
            description=description, metadata_hash=mh, timestamp=now, created_at=now,
            input_hash=input_digest(source_layer, event_type, description),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.event_exists(eid):
            head = ledger.events_head()
            ledger.append_event(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_EVENT, eid, _artifact_id(ART_LAYER, source_layer), now,
                              commit=commit)
        return EvolutionEvent(**rec)

    # ── Governance State Timeline (이벤트 소싱, 전이 검증) ──
    def current_maturity(self, layer_reference: str) -> str:
        sid = _state_id(layer_reference)
        evs = ledger.state_events_for(sid)
        return evs[-1].get("to_maturity", "") if evs else ""

    def create_state(self, layer_reference: str, maturity_level: str,
                   capabilities: list | None = None, now: str = "",
                   *, commit: bool = False) -> GovernanceStateEvent:
        """거버넌스 상태를 타임라인에 기록. 성숙도 전이 검증(레벨 건너뛰기 차단, 하락은 회귀로 추적)."""
        if maturity_level not in MATURITY_LEVELS:
            raise InvalidMaturityLevel(f"미등록 성숙도 레벨 {maturity_level}")
        sid = _state_id(layer_reference)
        evs = ledger.state_events_for(sid)
        frm = evs[-1].get("to_maturity", "") if evs else ""
        if not can_transition_state(frm, maturity_level):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {maturity_level} 차단(성숙도 레벨 건너뛰기)")
        seq = len(evs) + 1
        eid = state_event_id(sid, seq)
        rec = GovernanceStateEvent(
            event_id=eid, state_id=sid, layer_reference=layer_reference, sequence=seq,
            from_maturity=frm, to_maturity=maturity_level, maturity_level=maturity_level,
            capabilities=list(capabilities or []), regression=is_regression(frm, maturity_level),
            timestamp=now, created_at=now, input_hash=input_digest(sid, seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.state_event_exists(eid):
            head = ledger.states_head()
            ledger.append_state_event(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_LAYER, layer_reference) if ledger.artifact_exists(
            _artifact_id(ART_LAYER, layer_reference)) else ""
        if not parent:
            self._ensure_layer_artifact(layer_reference, now, commit=commit)
            parent = _artifact_id(ART_LAYER, layer_reference)
        self._record_artifact(ART_STATE, eid, parent, now, commit=commit)
        return GovernanceStateEvent(**rec)

    def maturity_trajectory(self, layer_reference: str) -> list:
        """레이어 성숙도 궤적(순서대로 to_maturity 리스트)."""
        sid = _state_id(layer_reference)
        return [e.get("to_maturity") for e in ledger.state_events_for(sid)]

    def regression_indicators(self) -> list:
        """성숙도 하락(회귀) 상태 지표. **정보용 — 개입 없음.**"""
        out: list = []
        for e in ledger.read_state_events():
            if e.get("regression"):
                out.append(f"{e.get('layer_reference')}:{e.get('from_maturity')}->"
                           f"{e.get('to_maturity')}")
        return sorted(set(out))

    # ── Maturity Assessment (불변) ──
    def assess_maturity(self, layer_reference: str, dimension_scores: dict | None = None,
                      evidence_reference: str = "", epoch: str = "", now: str = "",
                      *, commit: bool = False) -> MaturityAssessment:
        """성숙도 평가를 불변 기록. overall_score 는 차원 가중 평균(결정적). **점수 ≠ 권한.**"""
        ds = dict(dimension_scores or {})
        aid = _maturity_id(layer_reference, epoch)
        existing = ledger.get_maturity(aid)
        if existing is not None:
            if existing.get("dimension_scores") != ds:
                raise ImmutableMaturityError(f"{aid} 성숙도 평가 불변 — 변경 불가")
            return MaturityAssessment(**{k: v for k, v in existing.items()
                                         if k in MaturityAssessment.__dataclass_fields__})
        rec = MaturityAssessment(
            assessment_id=aid, layer_reference=layer_reference, dimension_scores=ds,
            overall_score=overall_maturity(ds), evidence_reference=evidence_reference,
            epoch=epoch, created_at=now, input_hash=input_digest(layer_reference, epoch),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.maturity_exists(aid):
            head = ledger.maturity_head()
            ledger.append_maturity(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_LAYER, layer_reference) if ledger.artifact_exists(
            _artifact_id(ART_LAYER, layer_reference)) else ""
        self._record_artifact(ART_MATURITY, aid, parent, now, commit=commit)
        return MaturityAssessment(**rec)

    # ── Evolution Pattern (불변) ──
    def analyze_pattern(self, detected_sequence: list, frequency: int | None = None, now: str = "",
                      *, commit: bool = False) -> EvolutionPattern:
        """변화 패턴(이벤트 유형 시퀀스) 탐지. frequency 미지정 시 이벤트 타임라인에서 연속 매칭 파생."""
        seq = list(detected_sequence or [])
        if frequency is None:
            frequency = self._count_sequence(seq)
        conf = pattern_confidence(int(frequency), len(seq))
        pid = _pattern_id(seq)
        mh = _metadata_hash({"frequency": int(frequency), "sequence": seq})
        existing = ledger.get_pattern(pid)
        if existing is not None:
            if existing.get("metadata_hash") != mh:
                raise ImmutablePatternError(f"{pid} 진화 패턴 불변 — 변경 불가")
            return EvolutionPattern(**{k: v for k, v in existing.items()
                                       if k in EvolutionPattern.__dataclass_fields__})
        rec = EvolutionPattern(
            pattern_id=pid, detected_sequence=seq, frequency=int(frequency), confidence=conf,
            metadata_hash=mh, created_at=now, input_hash=input_digest(seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.pattern_exists(pid):
            head = ledger.patterns_head()
            ledger.append_pattern(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_PATTERN, pid, "", now, commit=commit)
        return EvolutionPattern(**rec)

    def _count_sequence(self, seq: list) -> int:
        """이벤트 타임라인의 event_type 목록에서 연속 부분열 seq 의 출현 횟수."""
        if not seq:
            return 0
        types = [e.get("event_type") for e in ledger.read_events()]
        n, m = len(types), len(seq)
        if m > n:
            return 0
        count = 0
        for i in range(n - m + 1):
            if types[i:i + m] == seq:
                count += 1
        return count

    # ── Historical Comparison (불변) ──
    def compare_states(self, previous_state: str, current_state: str, now: str = "",
                     *, commit: bool = False) -> HistoricalComparison:
        """두 상태 이벤트의 역사적 차이(성숙도 델타·역량 증감)를 기록. **서술적 비교만.**"""
        pa = ledger.get_state_event(previous_state)
        cu = ledger.get_state_event(current_state)
        if pa is None:
            raise UnknownState(f"미존재 상태 {previous_state}")
        if cu is None:
            raise UnknownState(f"미존재 상태 {current_state}")
        prev_caps = set(pa.get("capabilities", []))
        cur_caps = set(cu.get("capabilities", []))
        differences = {
            "maturity_delta": level_index(cu.get("to_maturity")) - level_index(
                pa.get("to_maturity")),
            "from_maturity": pa.get("to_maturity"), "to_maturity": cu.get("to_maturity"),
            "capabilities_added": sorted(cur_caps - prev_caps),
            "capabilities_removed": sorted(prev_caps - cur_caps),
            "regression": level_index(cu.get("to_maturity")) < level_index(pa.get("to_maturity")),
        }
        cid = _comparison_id(previous_state, current_state)
        if not ledger.comparison_exists(cid):
            rec = HistoricalComparison(
                comparison_id=cid, previous_state=previous_state, current_state=current_state,
                differences=differences, created_at=now,
                input_hash=input_digest(previous_state, current_state),
                previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit:
                head = ledger.comparisons_head()
                ledger.append_comparison(_seal(rec, head["record_hash"] if head else GENESIS))
            parent = _artifact_id(ART_STATE, current_state) if ledger.artifact_exists(
                _artifact_id(ART_STATE, current_state)) else ""
            self._record_artifact(ART_COMPARISON, cid, parent, now, commit=commit)
            return HistoricalComparison(**rec)
        existing = next(c for c in ledger.read_comparisons() if c.get("comparison_id") == cid)
        return HistoricalComparison(**{k: v for k, v in existing.items()
                                       if k in HistoricalComparison.__dataclass_fields__})

    # ── Evolution Snapshot (불변·결정적) ──
    def create_snapshot(self, name: str, epoch: str = "", collected_states: list | None = None,
                      summary: dict | None = None, now: str = "",
                      *, commit: bool = False) -> EvolutionSnapshot:
        """거버넌스 상태 집합·요약을 결정적 스냅샷으로 고정. 동일 (name, epoch) → 동일 스냅샷."""
        cs = sorted(collected_states or [])
        smy = dict(summary or {})
        sid = _snapshot_id(name, epoch)
        existing = ledger.get_snapshot(sid)
        if existing is not None:
            return EvolutionSnapshot(**{k: v for k, v in existing.items()
                                        if k in EvolutionSnapshot.__dataclass_fields__})
        sh = _snapshot_hash(cs, smy)
        rec = EvolutionSnapshot(
            snapshot_id=sid, name=name, epoch=epoch, collected_states=cs, summary=smy,
            state_count=len(cs), snapshot_hash=sh, created_at=now,
            input_hash=input_digest(name, epoch), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_SNAPSHOT, sid, "", now, commit=commit)
        return EvolutionSnapshot(**rec)

    # ── 진화 인텔리전스 ──
    def capability_evolution_map(self) -> dict:
        """레이어별 최신 역량 목록(진화 지도)."""
        out: dict = {}
        for s in ledger.distinct_states():
            out[s.get("layer_reference")] = sorted(s.get("capabilities", []))
        return dict(sorted(out.items()))

    def structural_change_history(self) -> list:
        """구조 변화 이벤트 이력(structural_change/process_transition)."""
        return [f"{e.get('source_layer')}:{e.get('event_type')}:{e.get('description')}"
                for e in ledger.read_events()
                if e.get("event_type") in ("structural_change", "process_transition")]

    def average_maturity(self) -> float:
        vals = [float(a.get("overall_score", 0.0)) for a in ledger.read_maturity()]
        return round(sum(vals) / len(vals), 8) if vals else 0.0

    def analyze(self, metrics: dict) -> dict:
        """진화 지표 → SCORE/HEALTH. **EVOLUTION ANALYSIS ≠ EVOLUTION ACTION — 집행 신호 아님.**"""
        return {"evolution_score": evolution_score(metrics),
                "evolution_health": evolution_health(metrics)}

    # ── 계보 검증 ──
    def verify_lineage(self) -> dict:
        """진화 계보(아티팩트 parent 체인): dangling parent·순환 탐지. **읽기 전용.**"""
        issues: list = []
        arts = ledger.read_artifacts()
        ids = {a.get("artifact_id") for a in arts}
        edges: list = []
        for a in arts:
            parent = a.get("parent_artifact")
            if parent:
                if parent not in ids:
                    issues.append(f"dangling:{a.get('artifact_id')}->{parent}")
                edges.append((a.get("artifact_id"), parent))
        cyc = detect_cycle(edges)
        if cyc:
            issues.append("lineage_cycle:" + "->".join(cyc))
        return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}

    def trace_lineage(self, artifact_ref: str) -> list:
        by_id = {a.get("artifact_id"): a for a in ledger.read_artifacts()}
        out: list = []
        seen: set = set()
        cur = by_id.get(artifact_ref)
        while cur:
            parent = cur.get("parent_artifact")
            if not parent or parent in seen:
                break
            seen.add(parent)
            out.append(parent)
            cur = by_id.get(parent)
        return out

    # ── Evolution Report ──
    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                      *, commit: bool = False) -> EvolutionReport:
        m = dict(metrics or {})
        events = ledger.read_events()
        et_dist: dict = {}
        for e in events:
            et_dist[e.get("event_type")] = et_dist.get(e.get("event_type"), 0) + 1
        states = ledger.distinct_states()
        ml_dist: dict = {}
        for s in states:
            ml_dist[s.get("to_maturity")] = ml_dist.get(s.get("to_maturity"), 0) + 1
        rid = _report_id(scope)
        rec = EvolutionReport(
            report_id=rid, scope=scope, event_count=len(events),
            event_type_distribution=dict(sorted(et_dist.items())), state_count=len(states),
            layer_count=len({s.get("layer_reference") for s in states}),
            maturity_level_distribution=dict(sorted(ml_dist.items())),
            assessment_count=len(ledger.read_maturity()), average_maturity=self.average_maturity(),
            pattern_count=len(ledger.read_patterns()),
            comparison_count=len(ledger.read_comparisons()),
            snapshot_count=len(ledger.read_snapshots()),
            regression_indicators=self.regression_indicators(),
            capability_evolution_map=self.capability_evolution_map(), metrics=m,
            evolution_score=evolution_score(m), evolution_health=evolution_health(m),
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return EvolutionReport(**rec)

    # ── 상위 레이어 READ ONLY 조회 ──
    def list_source_objects(self, layer: str, limit: int = 0) -> list:
        spec = ledger.SOURCE_LEDGERS.get(layer)
        if not spec:
            return []
        filename, id_field = spec
        seen: set = set()
        out: list = []
        for r in ledger.read_source(filename):
            ref = r.get(id_field)
            if ref and ref not in seen:
                seen.add(ref)
                out.append(f"{layer}:{ref}")
            if limit and len(out) >= limit:
                break
        return out

    # ── Summary ──
    def summary(self, now: str = "") -> EvolutionSummary:
        events = ledger.read_events()
        et_dist: dict = {}
        for e in events:
            et_dist[e.get("event_type")] = et_dist.get(e.get("event_type"), 0) + 1
        states = ledger.distinct_states()
        ml_dist: dict = {}
        for s in states:
            ml_dist[s.get("to_maturity")] = ml_dist.get(s.get("to_maturity"), 0) + 1
        return EvolutionSummary(
            timestamp=now, event_count=len(events),
            event_type_distribution=dict(sorted(et_dist.items())), state_count=len(states),
            layer_count=len({s.get("layer_reference") for s in states}),
            maturity_level_distribution=dict(sorted(ml_dist.items())),
            assessment_count=len(ledger.read_maturity()),
            pattern_count=len(ledger.read_patterns()),
            comparison_count=len(ledger.read_comparisons()),
            snapshot_count=len(ledger.read_snapshots()),
            report_count=len(ledger.read_reports()))
