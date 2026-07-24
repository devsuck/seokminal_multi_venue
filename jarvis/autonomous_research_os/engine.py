"""Autonomous Research OS Engine (P13) — 최상위 연구 통합. **관찰·분석·기록 전용.**

모든 하위 계층(P10.x/P12.x)을 **READ ONLY** 로 연결·관찰·집계한다. **거래·주문·자본 배분·전략 배포·모델 승격·권한 변경을
절대 하지 않는다.** execution/broker/portfolio/risk/permission/deployment/live import·호출 없음. Research OS =
OBSERVATION + ANALYSIS + RECORDING ONLY. 결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.autonomous_research_os import ledger
from jarvis.autonomous_research_os.models import (
    ART_EPISODE,
    ART_OS,
    ART_SNAPSHOT,
    ART_VIEW,
    GENESIS,
    OS_ANALYZING,
    OS_ARCHIVED,
    OS_CONNECTED,
    OS_INITIALIZED,
    OS_OBSERVING,
    OS_REPORTING,
    ArtifactRecord,
    EpisodeRecord,
    IllegalOSTransition,
    ImmutableOSError,
    OSEventRecord,
    OSReportRecord,
    OSSummary,
    SnapshotRecord,
    UnknownOSError,
    ViewRecord,
    artifact_id as _artifact_id,
    can_transition,
    content_hash,
    episode_id as _episode_id,
    input_digest,
    os_event_id as _os_event_id,
    os_id as _os_id,
    report_id as _report_id,
    snapshot_id as _snapshot_id,
    view_id as _view_id,
)

_DISCLAIMER = ("Autonomous Research OS 데이터 — OS ≠ EXECUTION · CONNECT ≠ CONTROL · SNAPSHOT ≠ DEPLOYMENT. "
               "모든 하위 연구 계층 관찰·분석·기록 전용 — 거래·주문·자본 배분·전략 배포·모델 승격·권한 변경 절대 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AutonomousResearchOSEngine:
    """자율 연구 OS 엔진. 최상위 관찰·집계 계층. 불변·append-only·이벤트 소싱·결정적.

    실행·거래·배포·승격·권한 권한 없음. 하위 계층은 READ ONLY.
    """

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, now: str,
                *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    # ══════════════ OS 레지스트리 생애주기(event-sourced) ══════════════
    def _os_event(self, os: str, name: str, frm: str, to: str, note: str, now: str,
               *, commit: bool) -> OSEventRecord:
        seq = len(ledger.os_events(os))
        eid = _os_event_id(os, to, seq)
        rec = OSEventRecord(os_event_id=eid, os_id=os, name=name, from_state=frm, to_state=to,
                            note=note, occurred_at=now, input_hash=input_digest(os, to, seq),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.os_event_exists(eid):
            head = ledger.registry_head()
            ledger.append_os_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return OSEventRecord(**rec)

    def _meta(self, os: str) -> dict:
        evs = ledger.os_events(os)
        if not evs:
            raise UnknownOSError(f"미등록 OS {os}")
        return {"os_id": os, "name": evs[0].get("name"), "state": evs[-1].get("to_state")}

    def current_state(self, os: str) -> str | None:
        evs = ledger.os_events(os)
        return evs[-1].get("to_state") if evs else None

    def _require_os(self, os: str) -> str:
        st = self.current_state(os)
        if st is None:
            raise UnknownOSError(f"미등록 OS {os}")
        return st

    def _transition(self, os: str, to: str, note: str, now: str,
                  *, commit: bool) -> OSEventRecord:
        frm = self._require_os(os)
        if not can_transition(frm, to):
            raise IllegalOSTransition(f"{os} {frm}→{to} 불가")
        m = self._meta(os)
        return self._os_event(os, m["name"], frm, to, note, now, commit=commit)

    # ══════════════ initialize_os (Research OS Registry) ══════════════
    def initialize_os(self, name: str = "research-os", now: str = "",
                   *, commit: bool = False) -> OSEventRecord:
        """연구 OS 인스턴스 초기화(genesis INITIALIZED). **관찰 시스템 선언만.**"""
        oid = _os_id(name)
        evs = ledger.os_events(oid)
        if evs:
            g = evs[0]
            return OSEventRecord(**{k: v for k, v in g.items()
                                    if k in OSEventRecord.__dataclass_fields__})
        ev = self._os_event(oid, name, GENESIS, OS_INITIALIZED, "initialized", now, commit=commit)
        self._artifact(ART_OS, oid, "", now, commit=commit)
        return ev

    def connect(self, os: str, now: str = "", *, commit: bool = False) -> OSEventRecord:
        """하위 계층 연결(INITIALIZED→CONNECTED). READ ONLY 연결 선언만."""
        return self._transition(os, OS_CONNECTED, "connected", now, commit=commit)

    # ══════════════ collect_research_state (Research Episodes, →OBSERVING) ══════════════
    def collect_research_state(self, os: str, layer: str, note: str = "", now: str = "",
                            *, commit: bool = False) -> EpisodeRecord:
        """하위 계층 상태를 READ ONLY 로 관찰·에피소드 기록 + CONNECTED/OBSERVING→OBSERVING.

        하위 원장 파일만 읽는다(쓰지 않는다). **관찰 기록만 — 실행 아님.**
        """
        st = self._require_os(os)
        if st == OS_ARCHIVED:
            raise IllegalOSTransition(f"{os} ARCHIVED — 관찰 종료(불변)")
        if st == OS_INITIALIZED:
            raise IllegalOSTransition(f"{os} — connect() 먼저 필요(INITIALIZED)")
        if can_transition(st, OS_OBSERVING):
            self._transition(os, OS_OBSERVING, "observing", now, commit=commit)
        seq = len(ledger.os_episodes(os))
        eid = _episode_id(os, layer, seq)
        spec = ledger.SOURCE_LAYERS.get(layer)
        source_file = spec[0] if spec else ""
        count = ledger.source_count(layer)
        rec = EpisodeRecord(episode_id=eid, os_id=os, layer=layer, source_file=source_file,
                            observed_count=count, note=note, recorded_at=now,
                            input_hash=input_digest(os, layer, seq),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.episode_exists(eid):
            head = ledger.episodes_head()
            ledger.append_episode(_seal(rec, head["record_hash"] if head else GENESIS))
        os_art = _artifact_id(ART_OS, os)
        self._artifact(ART_EPISODE, eid, os_art if ledger.artifact_exists(os_art) else "", now,
                       commit=commit)
        return EpisodeRecord(**rec)

    # ══════════════ build_research_view (Knowledge Views) ══════════════
    def build_research_view(self, os: str, kind: str = "LAYER_COUNTS", now: str = "",
                         *, commit: bool = False) -> ViewRecord:
        """모든 하위 계층 집계 지식 뷰(결정적, READ ONLY). **is_binding=False, 관찰·집계만.**"""
        if self._require_os(os) == OS_ARCHIVED:
            raise IllegalOSTransition(f"{os} ARCHIVED — 집계 종료(불변)")
        counts = ledger.all_layer_counts()
        total = sum(counts.values())
        vid = _view_id(os, kind, now)
        rec = ViewRecord(view_id=vid, os_id=os, kind=kind, layer_counts=dict(sorted(counts.items())),
                         total_records=total, is_binding=False, created_at=now,
                         input_hash=input_digest(os, kind, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.view_exists(vid):
            head = ledger.views_head()
            ledger.append_view(_seal(rec, head["record_hash"] if head else GENESIS))
        os_art = _artifact_id(ART_OS, os)
        self._artifact(ART_VIEW, vid, os_art if ledger.artifact_exists(os_art) else "", now,
                       commit=commit)
        return ViewRecord(**rec)

    # ══════════════ create_snapshot (System Snapshots, →ANALYZING) ══════════════
    def create_snapshot(self, os: str, now: str = "", *, commit: bool = False) -> SnapshotRecord:
        """전체 시스템 결정적 스냅샷(관찰 집계) + OBSERVING→ANALYZING. **is_binding=False.**"""
        st = self._require_os(os)
        if st == OS_ARCHIVED:
            raise IllegalOSTransition(f"{os} ARCHIVED — 스냅샷 종료(불변)")
        if st == OS_OBSERVING:
            self._transition(os, OS_ANALYZING, "analyzing", now, commit=commit)
        counts = ledger.all_layer_counts()
        total = sum(counts.values())
        sid = _snapshot_id(os, now)
        rec = SnapshotRecord(
            snapshot_id=sid, os_id=os, timestamp=now, os_state=self.current_state(os),
            episode_count=len(ledger.os_episodes(os)), layer_counts=dict(sorted(counts.items())),
            total_records=total, is_binding=False, created_at=now,
            input_hash=input_digest(os, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        os_art = _artifact_id(ART_OS, os)
        self._artifact(ART_SNAPSHOT, sid, os_art if ledger.artifact_exists(os_art) else "", now,
                       commit=commit)
        return SnapshotRecord(**rec)

    # ══════════════ generate_os_report (Operational Reports, →REPORTING) ══════════════
    def generate_os_report(self, os: str, scope: str = "OS", now: str = "",
                        *, commit: bool = False) -> OSReportRecord:
        """OS 운영 리포트(연결 계층·에피소드·뷰·스냅샷 집계). **is_binding=False, 관찰·모니터링만.**"""
        st = self._require_os(os)
        if st == OS_ARCHIVED:
            raise IllegalOSTransition(f"{os} ARCHIVED — 리포트 종료(불변)")
        if st == OS_ANALYZING:
            self._transition(os, OS_REPORTING, "reporting", now, commit=commit)
        episodes = ledger.os_episodes(os)
        connected = len({e.get("layer") for e in episodes})
        rid = _report_id(os, scope, now)
        rec = OSReportRecord(
            report_id=rid, os_id=os, scope=scope, os_state=self.current_state(os),
            episode_count=len(episodes), view_count=len(ledger.read_views()),
            snapshot_count=len(ledger.read_snapshots()), connected_layers=connected,
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(os, scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return OSReportRecord(**rec)

    def archive_os(self, os: str, now: str = "", *, commit: bool = False) -> OSEventRecord:
        """OS 보관(REPORTING→ARCHIVED). **상태 기록만.**"""
        return self._transition(os, OS_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ verify_system_integrity ══════════════
    def verify_system_integrity(self) -> dict:
        from jarvis.autonomous_research_os.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_os(self) -> list:
        return ledger.os_ids()

    def os_meta(self, os: str) -> dict:
        return self._meta(os)

    def connected_layers(self, os: str) -> list:
        return sorted({e.get("layer") for e in ledger.os_episodes(os)})

    def layer_counts(self) -> dict:
        return ledger.all_layer_counts()

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> OSSummary:
        return OSSummary(
            timestamp=now, os_event_count=len(ledger.read_os_events()),
            episode_count=len(ledger.read_episodes()), view_count=len(ledger.read_views()),
            snapshot_count=len(ledger.read_snapshots()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
