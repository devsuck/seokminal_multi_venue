"""Research Validation Engine (P10.9) — 연구 품질·재현성 검증 기록. **평가·기록 전용.**

P10.2~P10.8 연구 계층을 READ ONLY 로 소비해 검증 세션·재현성 체크리스트·증거·리플레이 검증·계보
무결성·검증 점수·감사 요약을 남긴다. **연구 품질 평가 기록만 수행한다.** execution/broker/portfolio
mutation/capital allocation/strategy deployment/model promotion/permission/config/autonomy 변경 없음.
VALIDATED ≠ APPROVED · VALIDATED ≠ DEPLOYABLE · score ≠ approval · score ≠ deployment. 상위 레이어
파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_validation import ledger
from jarvis.research_validation.models import (
    ARCHIVED,
    ART_CHECKLIST,
    ART_EVIDENCE,
    ART_LINEAGE,
    ART_REPLAY,
    ART_SCORE,
    ART_TARGET,
    ART_VALIDATION,
    COMPLETED,
    CREATED,
    FULL_VALIDATION,
    GENESIS,
    NON_REPRODUCIBLE,
    REPRODUCIBLE,
    RUNNING,
    CHECKLIST_ITEMS,
    EvidenceRecord,
    IllegalTransition,
    ImmutableValidationError,
    LineageReport,
    ReplayReport,
    ReproducibilityChecklist,
    UnknownValidation,
    ValidationArtifact,
    ValidationAuditSummary,
    ValidationEvent,
    ValidationScore,
    ValidationSession,
    artifact_id as _artifact_id,
    can_transition_validation,
    checklist_id as _checklist_id,
    checklist_summary,
    checklist_to_components,
    compute_score,
    content_hash,
    detect_cycle,
    evidence_hash as _evidence_hash,
    evidence_id as _evidence_id,
    input_digest,
    lineage_report_id as _lineage_report_id,
    output_hash,
    replay_id as _replay_id,
    score_grade,
    score_id as _score_id,
    session_id as _session_id,
    validation_event_id,
    validation_id as _validation_id,
)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchValidationEngine:
    """연구 검증·재현성 거버넌스 엔진. 불변·append-only·결정적. 실행/배포/자본배분/권한 변경 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         validation_id: str, now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = ValidationArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, validation_id=validation_id, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Validation Session ──
    def create_session(self, name: str, validator: str, targets: list, objective: str = "",
                       now: str = "", *, commit: bool = False) -> ValidationSession:
        tgts = sorted(targets or [])
        sid = _session_id(name, validator, tgts)
        for s in ledger.read_sessions():
            if s.get("session_id") == sid:
                return ValidationSession(**{k: v for k, v in s.items()
                                            if k in ValidationSession.__dataclass_fields__})
        rec = ValidationSession(
            session_id=sid, name=name, validator=validator, targets=tgts, objective=objective,
            created_at=now, input_hash=input_digest(name, validator), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.session_exists(sid):
            head = ledger.sessions_head()
            ledger.append_session(_seal(rec, head["record_hash"] if head else GENESIS))
        return ValidationSession(**rec)

    # ── Validation Registry (이벤트 소싱, 불변) ──
    def validation_state(self, validation_id: str) -> str:
        evs = ledger.validation_events_for(validation_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _validation_meta(self, validation_id: str) -> dict | None:
        evs = ledger.validation_events_for(validation_id)
        return evs[0] if evs else None

    def _emit_validation_event(self, meta: dict, frm: str, to: str, now: str,
                               *, commit: bool) -> dict:
        if not can_transition_validation(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(validation)")
        vid = meta["validation_id"]
        eid = validation_event_id(vid, frm, to)
        rec = ValidationEvent(
            event_id=eid, validation_id=vid, target_layer=meta["target_layer"],
            target_id=meta["target_id"], validation_type=meta["validation_type"],
            session_reference=meta["session_reference"], from_state=frm, to_state=to, status=to,
            score=meta.get("score", 0.0), evidence_hash=meta.get("evidence_hash", ""),
            created_at=now, input_hash=input_digest(vid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.validation_event_exists(eid):
            head = ledger.validations_head()
            ledger.append_validation_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_validation(self, target_layer: str, target_id: str,
                            validation_type: str = FULL_VALIDATION, session_reference: str = "",
                            now: str = "", *, commit: bool = False) -> ValidationEvent:
        """연구 산출물에 대한 검증을 불변 등록(CREATED). **VALIDATED ≠ APPROVED.**"""
        vid = _validation_id(target_layer, target_id, validation_type)
        existing = ledger.validation_events_for(vid)
        if existing:
            first = existing[0]
            if first.get("target_layer") != target_layer or first.get("target_id") != target_id:
                raise ImmutableValidationError(f"{vid} 검증 불변 — 대상 변경 불가")
            return ValidationEvent(**existing[-1])
        meta = {"validation_id": vid, "target_layer": target_layer, "target_id": target_id,
                "validation_type": validation_type, "session_reference": session_reference,
                "score": 0.0, "evidence_hash": ""}
        rec = self._emit_validation_event(meta, "", CREATED, now, commit=commit)
        self._record_artifact(ART_TARGET, f"{target_layer}:{target_id}", "", vid, now,
                              commit=commit)
        self._record_artifact(ART_VALIDATION, vid,
                              _artifact_id(ART_TARGET, f"{target_layer}:{target_id}"), vid, now,
                              commit=commit)
        return ValidationEvent(**rec)

    def transition_validation(self, validation_id: str, to: str, now: str = "", *,
                              commit: bool = False) -> dict:
        meta = self._validation_meta(validation_id)
        if meta is None:
            raise UnknownValidation(f"미존재 검증 {validation_id}")
        return self._emit_validation_event(meta, self.validation_state(validation_id), to, now,
                                           commit=commit)

    def _safe_advance(self, validation_id: str, to: str, now: str, *, commit: bool) -> None:
        meta = self._validation_meta(validation_id)
        if meta is None:
            return
        cur = self.validation_state(validation_id)
        if cur != to and can_transition_validation(cur, to):
            self._emit_validation_event(meta, cur, to, now, commit=commit)

    # ── Reproducibility Checklist (자동 수정 없음) ──
    def evaluate_checklist(self, validation_id: str, items: dict, now: str = "",
                           *, commit: bool = False) -> ReproducibilityChecklist:
        """8개 재현성 항목 결과를 기록(PASS/WARNING/FAILED). **자동 수정 없음 — 라벨만.**"""
        if self._validation_meta(validation_id) is None:
            raise UnknownValidation(f"미존재 검증 {validation_id}")
        clean = {k: items.get(k, "FAILED") for k in CHECKLIST_ITEMS}
        summary = checklist_summary(clean)
        cid = _checklist_id(validation_id)
        rec = ReproducibilityChecklist(
            checklist_id=cid, validation_id=validation_id, items=clean, summary=summary,
            created_at=now, input_hash=input_digest(validation_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.checklist_exists(cid):
            head = ledger.checklists_head()
            ledger.append_checklist(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_CHECKLIST, cid, _artifact_id(ART_VALIDATION, validation_id),
                              validation_id, now, commit=commit)
        self._safe_advance(validation_id, RUNNING, now, commit=commit)
        return ReproducibilityChecklist(**rec)

    # ── Evidence Registry ──
    def record_evidence(self, validation_id: str, name: str, evidence_type: str,
                        reference: str, payload: dict | None = None, now: str = "",
                        *, commit: bool = False) -> EvidenceRecord:
        if self._validation_meta(validation_id) is None:
            raise UnknownValidation(f"미존재 검증 {validation_id}")
        eid = _evidence_id(validation_id, name)
        eh = _evidence_hash(payload or {"reference": reference})
        rec = EvidenceRecord(
            evidence_id=eid, validation_id=validation_id, name=name, evidence_type=evidence_type,
            reference=reference, evidence_hash=eh, created_at=now,
            input_hash=input_digest(validation_id, name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.evidence_exists(eid):
            head = ledger.evidence_head()
            ledger.append_evidence(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_EVIDENCE, eid, _artifact_id(ART_VALIDATION, validation_id),
                              validation_id, now, commit=commit)
        return EvidenceRecord(**rec)

    # ── Experiment Replay Verification ──
    def verify_replay(self, validation_id: str, inputs: dict, metadata: dict, seed: str,
                      original_output_hash: str = "", now: str = "",
                      *, commit: bool = False) -> ReplayReport:
        """같은 입력+metadata+seed → 동일 output hash 확인. 불일치면 NON_REPRODUCIBLE 기록만."""
        if self._validation_meta(validation_id) is None:
            raise UnknownValidation(f"미존재 검증 {validation_id}")
        replay_hash = output_hash(inputs, metadata, seed)
        original = original_output_hash or replay_hash
        result = REPRODUCIBLE if original == replay_hash else NON_REPRODUCIBLE
        rid = _replay_id(validation_id)
        rec = ReplayReport(
            replay_id=rid, validation_id=validation_id, original_output_hash=original,
            replay_output_hash=replay_hash, result=result, created_at=now,
            input_hash=input_digest(validation_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.replay_exists(rid):
            head = ledger.replay_head()
            ledger.append_replay(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPLAY, rid, _artifact_id(ART_VALIDATION, validation_id),
                              validation_id, now, commit=commit)
        return ReplayReport(**rec)

    # ── Lineage Integrity Report ──
    def validate_lineage(self, validation_id: str, target_layer: str, now: str = "",
                         *, commit: bool = False) -> LineageReport:
        """상위 레이어 아티팩트 원장(READ ONLY)의 계보를 검사: dangling parent·cycle·broken chain."""
        if self._validation_meta(validation_id) is None:
            raise UnknownValidation(f"미존재 검증 {validation_id}")
        issues: list = []
        source_files = ledger.SOURCE_LEDGERS.get(target_layer, ())
        artifact_file = None
        for f in source_files:
            if "artifact" in f or "lineage" in f:
                artifact_file = f
                break
        arts = ledger.read_source(artifact_file) if artifact_file else []
        ids = {a.get("artifact_id") for a in arts}
        edges = []
        for a in arts:
            parent = a.get("parent_artifact")
            if parent:
                if parent not in ids:
                    issues.append(f"dangling_parent:{a.get('artifact_id')}->{parent}")
                edges.append((a.get("artifact_id"), parent))
        cyc = detect_cycle(edges)
        if cyc:
            issues.append("cycle:" + "->".join(cyc))
        if artifact_file is None:
            issues.append(f"missing_source:{target_layer}")
        lid = _lineage_report_id(validation_id)
        ok = not issues
        rec = LineageReport(
            lineage_report_id=lid, validation_id=validation_id, target_layer=target_layer,
            issues=sorted(set(issues)), n_checked=len(arts), ok=ok, created_at=now,
            input_hash=input_digest(validation_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.lineage_report_exists(lid):
            head = ledger.lineage_head()
            ledger.append_lineage_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_LINEAGE, lid, _artifact_id(ART_VALIDATION, validation_id),
                              validation_id, now, commit=commit)
        return LineageReport(**rec)

    # ── Validation Score ──
    def compute_validation_score(self, validation_id: str, components: dict | None = None,
                                 now: str = "", *, commit: bool = False) -> ValidationScore:
        """가중 검증 점수 계산·기록. components 없으면 체크리스트에서 파생. **score ≠ approval.**"""
        if self._validation_meta(validation_id) is None:
            raise UnknownValidation(f"미존재 검증 {validation_id}")
        if components is None:
            cl = None
            for c in ledger.read_checklists():
                if c.get("validation_id") == validation_id:
                    cl = c
                    break
            components = checklist_to_components(cl.get("items", {})) if cl else {}
        overall = compute_score(components)
        grade = score_grade(overall)
        sid = _score_id(validation_id)
        rec = ValidationScore(
            score_id=sid, validation_id=validation_id, components=dict(components),
            overall_score=overall, grade=grade, created_at=now,
            input_hash=input_digest(validation_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.score_exists(sid):
            head = ledger.scores_head()
            ledger.append_score(_seal(rec, head["record_hash"] if head else GENESIS))
        # 점수 산출 후 검증 COMPLETED 로 진행(RUNNING→COMPLETED).
        parent = _artifact_id(ART_CHECKLIST, _checklist_id(validation_id))
        if not ledger.artifact_exists(parent):
            parent = _artifact_id(ART_VALIDATION, validation_id)
        self._record_artifact(ART_SCORE, sid, parent, validation_id, now, commit=commit)
        self._safe_advance(validation_id, RUNNING, now, commit=commit)
        self._safe_advance(validation_id, COMPLETED, now, commit=commit)
        return ValidationScore(**rec)

    # ── 상위 레이어 READ ONLY 조회 ──
    def list_source_targets(self, target_layer: str, limit: int = 0) -> list:
        """상위 레이어 원장을 읽기 전용으로 스캔해 대상 참조 목록 반환. 등록·변경 없음."""
        files = ledger.SOURCE_LEDGERS.get(target_layer)
        if not files:
            return []
        rows = ledger.read_source(files[0])
        out: list = []
        for r in rows:
            for k in ("strategy_id", "signal_id", "portfolio_id", "entity_id", "agent_id",
                      "candidate_id", "scenario_id"):
                if r.get(k):
                    out.append(str(r[k]))
                    break
            if limit and len(out) >= limit:
                break
        return out

    # ── Audit Summary ──
    def generate_audit_summary(self, now: str = "") -> ValidationAuditSummary:
        validations = ledger.distinct_validations()
        vstate: dict = {}
        vtype: dict = {}
        tlayer: dict = {}
        for v in validations:
            st = self.validation_state(v.get("validation_id"))
            vstate[st] = vstate.get(st, 0) + 1
            vtype[v.get("validation_type")] = vtype.get(v.get("validation_type"), 0) + 1
            tlayer[v.get("target_layer")] = tlayer.get(v.get("target_layer"), 0) + 1

        checklists = ledger.read_checklists()
        cl_overall: dict = {}
        for c in checklists:
            ov = c.get("summary", {}).get("overall", "")
            cl_overall[ov] = cl_overall.get(ov, 0) + 1

        replays = ledger.read_replay_reports()
        non_repro = sum(1 for r in replays if r.get("result") == NON_REPRODUCIBLE)

        lineage_reports = ledger.read_lineage_reports()
        lineage_issues = sum(len(l.get("issues", [])) for l in lineage_reports)

        scores = ledger.read_scores()
        mean_score = round(sum(s.get("overall_score", 0.0) for s in scores) / len(scores), 8) \
            if scores else 0.0

        return ValidationAuditSummary(
            timestamp=now, validation_count=len(validations),
            validation_state_distribution=dict(sorted(vstate.items())),
            validation_type_distribution=dict(sorted(vtype.items())),
            target_layer_distribution=dict(sorted(tlayer.items())),
            session_count=len(ledger.read_sessions()), checklist_count=len(checklists),
            checklist_overall_distribution=dict(sorted(cl_overall.items())),
            evidence_count=len(ledger.read_evidence()), replay_count=len(replays),
            non_reproducible_count=non_repro, lineage_report_count=len(lineage_reports),
            lineage_issue_count=lineage_issues, score_count=len(scores), mean_score=mean_score)
