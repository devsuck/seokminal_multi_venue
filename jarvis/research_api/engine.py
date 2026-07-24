"""Research Intelligence API Backend Engine (P10.29) — 대시보드·AI 에이전트용 조회 백엔드. **읽기 전용.**

상위 계층(P10.23~P10.28)을 READ ONLY 로 참조(파일 기반, import 없음)해 시스템 상태·연구 타임라인·전략 계보·
알파/리스크/에이전트 요약·거버넌스 리포트를 결정적 조회 API 로 제공하고 모든 접근을 append-only 감사 원장에
남긴다. **API·데이터 접근 전용 — 거래 실행 없음.** POST 실행·trade·order·deployment 엔드포인트 없음. GET(읽기)만.
execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller import·호출
없음. READ ≠ WRITE · QUERY ≠ EXECUTE · API ≠ TRADE. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_api import ledger
from jarvis.research_api.models import (
    ALLOWED_METHODS,
    ENDPOINT_META,
    ENDPOINT_SCHEMAS,
    GENESIS,
    METHOD_GET,
    AccessLogRecord,
    APIResponse,
    APISummary,
    EndpointRecord,
    ForbiddenEndpoint,
    ImmutableEndpointError,
    ImmutableQueryError,
    ImmutableSchemaError,
    ImmutableViewError,
    InvalidEndpointMethod,
    QueryRecord,
    SchemaRecord,
    UnknownEndpointError,
    ViewRecord,
    access_id as _access_id,
    content_hash,
    distribution,
    endpoint_id as _endpoint_id,
    input_digest,
    is_forbidden_path,
    params_hash as _params_hash,
    query_id as _query_id,
    result_hash as _result_hash,
    schema_id as _schema_id,
    view_id as _view_id,
)

_DISCLAIMER = ("Research API 데이터 — READ ≠ WRITE · QUERY ≠ EXECUTE · API ≠ TRADE. 조회·데이터 접근 전용 — "
               "거래 실행/주문/배포 아님. POST 실행 엔드포인트 없음.")

# 타임라인 정렬용 타임스탬프 후보.
_TS_FIELDS = ("occurred_at", "created_at", "recorded_at", "timestamp", "generated_at",
              "computed_at", "snapshot_at", "accessed_at")


def _ts(rec: dict) -> str:
    for f in _TS_FIELDS:
        v = rec.get(f)
        if v:
            return str(v)
    return ""


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchAPIEngine:
    """대시보드·AI 에이전트용 조회 백엔드. 불변·append-only·결정적. 실행/거래/주문/배포 권한 없음."""

    # ══════════════ 레지스트리 등록 ══════════════
    def register_schema(self, name: str, endpoint: str, fields, version: str = "v1",
                       now: str = "", *, commit: bool = False) -> SchemaRecord:
        """API 응답 스키마 등록(불변)."""
        sid = _schema_id(name)
        flds = list(fields)
        existing = ledger.get_schema(sid)
        if existing is not None:
            if list(existing.get("fields", [])) != flds:
                raise ImmutableSchemaError(f"{sid} 스키마 불변 — 변경 불가")
            return SchemaRecord(**{k: v for k, v in existing.items()
                                   if k in SchemaRecord.__dataclass_fields__})
        rec = SchemaRecord(schema_id=sid, name=name, endpoint=endpoint, fields=flds,
                           version=version, created_at=now, input_hash=input_digest(name),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.schema_exists(sid):
            head = ledger.schemas_head()
            ledger.append_schema(_seal(rec, head["record_hash"] if head else GENESIS))
        return SchemaRecord(**rec)

    def register_query(self, name: str, source_layer: str, description: str = "", now: str = "",
                     *, commit: bool = False) -> QueryRecord:
        """명명된 조회(Query Registry) 등록(불변)."""
        qid = _query_id(name)
        existing = ledger.get_query(qid)
        if existing is not None:
            if existing.get("source_layer") != source_layer:
                raise ImmutableQueryError(f"{qid} 쿼리 불변 — 변경 불가")
            return QueryRecord(**{k: v for k, v in existing.items()
                                  if k in QueryRecord.__dataclass_fields__})
        rec = QueryRecord(query_id=qid, name=name, source_layer=source_layer,
                          description=description, created_at=now, input_hash=input_digest(name),
                          previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.query_exists(qid):
            head = ledger.queries_head()
            ledger.append_query(_seal(rec, head["record_hash"] if head else GENESIS))
        return QueryRecord(**rec)

    def register_view(self, name: str, endpoint: str, columns, refresh_hint: str = "on_read",
                    now: str = "", *, commit: bool = False) -> ViewRecord:
        """대시보드 데이터 뷰 등록(불변)."""
        vid = _view_id(name)
        cols = list(columns)
        existing = ledger.get_view(vid)
        if existing is not None:
            if list(existing.get("columns", [])) != cols:
                raise ImmutableViewError(f"{vid} 뷰 불변 — 변경 불가")
            return ViewRecord(**{k: v for k, v in existing.items()
                                 if k in ViewRecord.__dataclass_fields__})
        rec = ViewRecord(view_id=vid, name=name, endpoint=endpoint, columns=cols,
                         refresh_hint=refresh_hint, created_at=now, input_hash=input_digest(name),
                         previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.view_exists(vid):
            head = ledger.views_head()
            ledger.append_view(_seal(rec, head["record_hash"] if head else GENESIS))
        return ViewRecord(**rec)

    def register_endpoint(self, path: str, function: str, source_layers, method: str = METHOD_GET,
                        description: str = "", now: str = "", *, commit: bool = False) -> EndpointRecord:
        """엔드포인트 메타 등록(불변). **GET 만 허용 — 실행/거래/주문/배포 엔드포인트 거부.**"""
        if method not in ALLOWED_METHODS:
            raise InvalidEndpointMethod(f"허용되지 않은 메서드 {method} — 읽기(GET)만 가능")
        if is_forbidden_path(path, function):
            raise ForbiddenEndpoint(f"금지 엔드포인트(실행/거래/주문/배포): {path} {function}")
        eid = _endpoint_id(path)
        layers = list(source_layers)
        existing = ledger.get_endpoint(eid)
        if existing is not None:
            if existing.get("function") != function or existing.get("method") != method:
                raise ImmutableEndpointError(f"{eid} 엔드포인트 불변 — 변경 불가")
            return EndpointRecord(**{k: v for k, v in existing.items()
                                     if k in EndpointRecord.__dataclass_fields__})
        rec = EndpointRecord(endpoint_id=eid, path=path, method=method, function=function,
                             source_layers=layers, read_only=True, description=description,
                             created_at=now, input_hash=input_digest(path),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.endpoint_exists(eid):
            head = ledger.endpoints_head()
            ledger.append_endpoint(_seal(rec, head["record_hash"] if head else GENESIS))
        return EndpointRecord(**rec)

    def bootstrap(self, now: str = "", *, commit: bool = False) -> dict:
        """기본 스키마·엔드포인트·뷰·쿼리 레지스트리 구성. **등록만 — 실행 없음.**"""
        n_ep = n_sc = n_vw = n_q = 0
        for function, path, layers in ENDPOINT_META:
            self.register_endpoint(path, function, layers, METHOD_GET,
                                   f"read-only {function}", now, commit=commit)
            n_ep += 1
            self.register_schema(function, path, ENDPOINT_SCHEMAS[function], "v1", now,
                                 commit=commit)
            n_sc += 1
            self.register_view(function, path, ENDPOINT_SCHEMAS[function], "on_read", now,
                               commit=commit)
            n_vw += 1
            for layer in layers:
                self.register_query(f"{function}:{layer}", layer, f"read {layer}", now,
                                    commit=commit)
                n_q += 1
        return {"endpoints": n_ep, "schemas": n_sc, "views": n_vw, "queries": n_q}

    # ══════════════ 응답 + 접근 감사 ══════════════
    def _respond(self, endpoint: str, data: dict, params: dict, now: str,
               *, commit: bool) -> APIResponse:
        # 스키마 키 검증(일관성) — 등록 스키마와 정확히 일치해야 함.
        expected = list(ENDPOINT_SCHEMAS.get(endpoint, ()))
        if expected and set(data.keys()) != set(expected):
            raise UnknownEndpointError(f"{endpoint} 응답 키 불일치")
        rhash = _result_hash(data)
        phash = _params_hash(params)
        resp = APIResponse(endpoint=endpoint, schema_id=_schema_id(endpoint), read_only=True,
                           data=data, result_hash=rhash, disclaimer=_DISCLAIMER, generated_at=now)
        self._log_access(endpoint, phash, rhash, now, commit=commit)
        return resp

    def _log_access(self, endpoint: str, phash: str, rhash: str, now: str,
                  *, commit: bool) -> dict:
        aid = _access_id(endpoint, phash, now)
        rec = AccessLogRecord(access_id=aid, endpoint=endpoint, method=METHOD_GET,
                              params_hash=phash, result_hash=rhash, read_only=True,
                              accessed_at=now, input_hash=input_digest(endpoint, phash, now),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.access_exists(aid):
            head = ledger.access_head()
            ledger.append_access(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ══════════════ 조회 API (7 함수) — READ ONLY ══════════════
    def get_system_status(self, now: str = "", *, commit: bool = False) -> APIResponse:
        """P10.28 Research Control Plane 개요·헬스 기반 시스템 상태. **읽기만.**"""
        overview = ledger.read_role("research_control_plane", "overview")
        health = ledger.read_role("research_control_plane", "health")
        ov = overview[-1] if overview else {}
        hl = health[-1] if health else {}
        data = {
            "component_count": int(ov.get("component_count", 0)),
            "active_component_count": int(ov.get("active_component_count", 0)),
            "dependency_count": int(ov.get("dependency_count", 0)),
            "health_level": hl.get("level", ov.get("health_level", "UNKNOWN")),
            "overall_score": float(hl.get("overall_score", ov.get("overall_score", 0.0))),
            "category_distribution": dict(sorted((ov.get("category_distribution") or {}).items())),
            "last_snapshot_at": ov.get("snapshot_at", ""),
        }
        return self._respond("get_system_status", data, {}, now, commit=commit)

    def get_research_timeline(self, limit: int = 0, now: str = "",
                            *, commit: bool = False) -> APIResponse:
        """P10.28 컨트롤 타임라인 + P10.26 라이프사이클 이벤트 병합 타임라인. **읽기만.**"""
        events: list = []
        for e in ledger.read_role("research_control_plane", "timeline"):
            events.append({"source": "control_plane", "kind": e.get("kind", ""),
                           "reference": e.get("reference", ""), "at": _ts(e)})
        for e in ledger.read_role("research_lifecycle", "events"):
            events.append({"source": "lifecycle", "kind": e.get("event_type", e.get("kind", "")),
                           "reference": e.get("event_id", ""), "at": _ts(e)})
        events.sort(key=lambda x: (x["at"], x["source"], x["reference"]))
        total = len(events)
        truncated = bool(limit and total > limit)
        if limit:
            events = events[:limit]
        data = {"events": events, "event_count": total, "truncated": truncated}
        return self._respond("get_research_timeline", data, {"limit": limit}, now, commit=commit)

    def get_strategy_lineage(self, strategy: str, now: str = "",
                           *, commit: bool = False) -> APIResponse:
        """P10.26 라이프사이클 전이·이벤트에서 전략/연구 계보(단계 순서) 추출. **읽기만.**"""
        stages: list = []
        for t in ledger.read_role("research_lifecycle", "transitions"):
            subj = str(t.get("subject", t.get("project", t.get("strategy", ""))))
            if strategy in (subj, t.get("project"), t.get("strategy")):
                stages.append({"from": t.get("from_stage", t.get("from", "")),
                               "to": t.get("to_stage", t.get("to", "")), "at": _ts(t)})
        for e in ledger.read_role("research_lifecycle", "events"):
            subj = str(e.get("subject", e.get("project", e.get("strategy", ""))))
            if strategy in (subj, e.get("project"), e.get("strategy")):
                stages.append({"from": "", "to": e.get("stage", e.get("to_stage", "")),
                               "at": _ts(e)})
        stages.sort(key=lambda x: (x["at"], x["from"], x["to"]))
        data = {"strategy": strategy, "stages": stages, "stage_count": len(stages)}
        return self._respond("get_strategy_lineage", data, {"strategy": strategy}, now,
                             commit=commit)

    def get_alpha_summary(self, now: str = "", *, commit: bool = False) -> APIResponse:
        """P10.27 Knowledge Intelligence 인사이트·패턴·클러스터 요약(발견된 지식/알파). **읽기만.**"""
        insights = ledger.read_role("knowledge_intelligence", "insights")
        patterns = ledger.read_role("knowledge_intelligence", "patterns")
        clusters = ledger.read_role("knowledge_intelligence", "clusters")
        it_dist: dict = {}
        for i in insights:
            it_dist[i.get("insight_type", "")] = it_dist.get(i.get("insight_type", ""), 0) + 1
        data = {
            "insight_count": len(insights),
            "insight_type_distribution": dict(sorted(it_dist.items())),
            "pattern_count": len(patterns),
            "cluster_count": len(clusters),
            "recommendation_count": it_dist.get("RECOMMENDATION", 0),
        }
        return self._respond("get_alpha_summary", data, {}, now, commit=commit)

    def get_risk_summary(self, now: str = "", *, commit: bool = False) -> APIResponse:
        """P10.25 Research Risk Intelligence 평가·요인 요약(연구 프로세스 리스크). **읽기만.**"""
        assessments = ledger.read_role("research_risk_intelligence", "assessments")
        factors = ledger.read_role("research_risk_intelligence", "factors")
        data = {
            "assessment_count": len(assessments),
            "result_distribution": distribution(assessments, ("result", "level", "severity",
                                                              "status")),
            "factor_count": len(factors),
        }
        return self._respond("get_risk_summary", data, {}, now, commit=commit)

    def get_agent_summary(self, now: str = "", *, commit: bool = False) -> APIResponse:
        """P10.24 Self Audit Intelligence 자율 감사 에이전트 활동 요약. **읽기만.**"""
        audits = ledger.read_role("self_audit_intelligence", "audits")
        checks = ledger.read_role("self_audit_intelligence", "checks")
        violations = ledger.read_role("self_audit_intelligence", "violations")
        data = {
            "audit_count": len(audits),
            "check_count": len(checks),
            "violation_count": len(violations),
            "result_distribution": distribution(audits, ("result", "status", "outcome", "level")),
        }
        return self._respond("get_agent_summary", data, {}, now, commit=commit)

    def get_governance_report(self, now: str = "", *, commit: bool = False) -> APIResponse:
        """P10.23 Governance Orchestration 계층·리포트·충돌·헬스 요약. **읽기만.**"""
        layers = ledger.read_role("governance_orchestration", "layers")
        reports = ledger.read_role("governance_orchestration", "reports")
        conflicts = ledger.read_role("governance_orchestration", "conflicts")
        health = ledger.read_role("governance_orchestration", "health")
        hl = health[-1] if health else {}
        distinct_layers = {l.get("layer_id", l.get("event_id", l.get("name"))) for l in layers}
        data = {
            "layer_count": len([x for x in distinct_layers if x is not None]),
            "report_count": len(reports),
            "conflict_count": len(conflicts),
            "health_level": hl.get("level", hl.get("health_level", "UNKNOWN")),
        }
        return self._respond("get_governance_report", data, {}, now, commit=commit)

    # ══════════════ 일반 디스패치 ══════════════
    _FUNCTIONS = ("get_system_status", "get_research_timeline", "get_strategy_lineage",
                  "get_alpha_summary", "get_risk_summary", "get_agent_summary",
                  "get_governance_report")

    def call(self, function: str, params: dict | None = None, now: str = "",
           *, commit: bool = False) -> APIResponse:
        """등록 함수명으로 조회 디스패치. **읽기 전용 — 실행 없음.**"""
        if function not in self._FUNCTIONS:
            raise UnknownEndpointError(f"미등록 엔드포인트 {function}")
        p = dict(params or {})
        if function == "get_research_timeline":
            return self.get_research_timeline(int(p.get("limit", 0)), now, commit=commit)
        if function == "get_strategy_lineage":
            return self.get_strategy_lineage(str(p.get("strategy", "")), now, commit=commit)
        return getattr(self, function)(now, commit=commit)

    # ══════════════ 조회 편의 ══════════════
    def list_endpoints(self) -> list:
        return sorted(e.get("path") for e in ledger.read_endpoints() if e.get("path"))

    def endpoint_schema(self, function: str) -> dict | None:
        return ledger.get_schema(_schema_id(function))

    def access_log(self, endpoint: str = "") -> list:
        out = ledger.read_access()
        if endpoint:
            out = [a for a in out if a.get("endpoint") == endpoint]
        return out

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> APISummary:
        return APISummary(
            timestamp=now, schema_count=len(ledger.read_schemas()),
            query_count=len(ledger.read_queries()), view_count=len(ledger.read_views()),
            endpoint_count=len(ledger.read_endpoints()), access_count=len(ledger.read_access()))
