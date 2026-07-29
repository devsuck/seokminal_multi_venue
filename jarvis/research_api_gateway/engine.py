"""Research API Gateway Engine (P33) — 통합 읽기 전용 API. **동작 없음, 변경 없음.**

읽기 전용 서비스만 노출한다: 지식 질의·연구 요약·이력·지표·리포트·계보. **거래·배포·실행·승인·배분을 노출하지 않는다.**
execution/broker/live_trading/portfolio_execution import·호출 없음. READ ONLY · GATEWAY ≠ EXECUTION · QUERY ≠
MUTATION. 결정적·불변·append-only. 상위 계층은 READ ONLY(질의만).
"""
from __future__ import annotations

from jarvis.research_api_gateway import ledger
from jarvis.research_api_gateway import models as M
from jarvis.research_api_gateway.models import (
    GENESIS,
    ArtifactRecord,
    ForbiddenServiceError,
    GatewayReportRecord,
    GatewaySummary,
    QueryRecord,
    ResponseRecord,
    ServiceRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Research API Gateway 데이터 — READ ONLY · GATEWAY ≠ EXECUTION · QUERY ≠ MUTATION. 통합 "
               "읽기 전용 서비스(지식 질의·연구 요약·이력·지표·리포트·계보) 전용 — 거래·배포·실행·승인·배분 노출 없음. "
               "상위 원장은 질의만(변경 없음).")

# ── 서비스 유형 → 기본 대상 계층(READ ONLY) ──
_SERVICE_DEFAULT_LAYER = {
    "KNOWLEDGE_QUERY": "knowledge_graph",
    "RESEARCH_SUMMARY": "autonomous_research",
    "HISTORY": "orchestration",
    "METRICS": "meta_intelligence",
    "REPORTS": "reliability",
    "LINEAGE": "insight_intelligence",
}


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchApiGatewayEngine:
    """연구 API 게이트웨이. 불변·append-only·결정적. 읽기 전용 — 거래/배포/실행/승인/배분 노출 없음."""

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _artifact(self, atype, ref, parent, now, *, commit) -> ArtifactRecord:
        aid = M.artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref, parent_artifact=parent,
                             created_at=now, input_hash=input_digest(atype, ref),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.artifact_exists, ledger.artifacts_head, ledger.append_artifact,
                         aid, rec, commit=commit)
        return ArtifactRecord(**rec)

    # ══════════════ register_service (읽기 전용만) ══════════════
    def register_service(self, service_type, name, description="", now="",
                         *, commit=False) -> ServiceRecord:
        """읽기 전용 서비스 등록(불변). **변경·실행 서비스 거부(ForbiddenServiceError).**"""
        if service_type in M.FORBIDDEN_SERVICE_TYPES:
            raise ForbiddenServiceError(f"금지 서비스 유형 노출 불가: {service_type}")
        if not M.is_readonly_service(service_type):
            raise ValueError(f"미지원 service_type {service_type}")
        sid = M.service_id(service_type, name)
        existing = next((s for s in ledger.read_services() if s.get("service_id") == sid), None)
        if existing:
            return ServiceRecord(**{k: v for k, v in existing.items()
                                    if k in ServiceRecord.__dataclass_fields__})
        rec = ServiceRecord(service_id=sid, service_type=service_type, name=name,
                            description=description, is_readonly=True, created_at=now,
                            input_hash=input_digest(service_type, name),
                            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.service_exists, ledger.services_head, ledger.append_service, sid,
                         rec, commit=commit)
        self._artifact(M.ART_SERVICE, sid, "", now, commit=commit)
        return ServiceRecord(**rec)

    # ══════════════ query (읽기 전용 실행 → 질의·응답 로그) ══════════════
    def query(self, service_type, target_layer=None, params=None, now="",
              *, commit=False) -> ResponseRecord:
        """읽기 전용 질의 실행(상위 원장 READ ONLY). 질의·응답 감사 로그 기록. **변경 없음.**"""
        if service_type in M.FORBIDDEN_SERVICE_TYPES:
            raise ForbiddenServiceError(f"금지 서비스 질의 불가: {service_type}")
        if not M.is_readonly_service(service_type):
            raise ValueError(f"미지원 service_type {service_type}")
        layer = target_layer or _SERVICE_DEFAULT_LAYER.get(service_type, "knowledge_graph")
        prm = dict(params or {})
        seq = len(ledger.queries_by(service_type, layer))
        qid = M.query_id(service_type, layer, seq)
        qrec = QueryRecord(query_id=qid, service_type=service_type, target_layer=layer, params=prm,
                           timestamp=now, input_hash=input_digest(service_type, layer, seq),
                           previous_hash=GENESIS).to_dict()
        qrec = self._emit(ledger.query_exists, ledger.queries_head, ledger.append_query, qid, qrec,
                          commit=commit)
        # 읽기 전용 결과 산출(상위 원장 READ ONLY)
        count = ledger.source_count(layer)
        summary = {"layer": layer, "count": count, "present": ledger.source_present(layer),
                   "read_only": True}
        rid = M.response_id(qid)
        rrec = ResponseRecord(response_id=rid, query_id=qid, service_type=service_type,
                              target_layer=layer, result_count=count, result_summary=summary,
                              is_readonly=True, timestamp=now, input_hash=input_digest(qid),
                              previous_hash=GENESIS).to_dict()
        rrec = self._emit(ledger.response_exists, ledger.responses_head, ledger.append_response, rid,
                          rrec, commit=commit)
        return ResponseRecord(**rrec)

    # ══════════════ 읽기 전용 서비스 헬퍼(감사 없이 즉시 조회) ══════════════
    def get_knowledge(self, layer="knowledge_graph") -> dict:
        return {"service": "KNOWLEDGE_QUERY", "layer": layer, "count": ledger.source_count(layer),
                "read_only": True}

    def get_summary(self) -> dict:
        return {"service": "RESEARCH_SUMMARY", "counts": ledger.all_source_counts(),
                "read_only": True}

    def get_history(self, layer="orchestration") -> dict:
        return {"service": "HISTORY", "layer": layer, "count": ledger.source_count(layer),
                "read_only": True}

    def get_metrics(self, layer="meta_intelligence") -> dict:
        return {"service": "METRICS", "layer": layer, "count": ledger.source_count(layer),
                "read_only": True}

    def get_reports(self, layer="reliability") -> dict:
        return {"service": "REPORTS", "layer": layer, "count": ledger.source_count(layer),
                "read_only": True}

    def get_lineage(self, layer="insight_intelligence") -> dict:
        return {"service": "LINEAGE", "layer": layer, "count": ledger.source_count(layer),
                "read_only": True}

    def list_services(self) -> list:
        return sorted(s.get("service_id") for s in ledger.read_services())

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> GatewayReportRecord:
        """게이트웨이 리포트(서비스·질의·응답 집계). **is_binding=False, READ ONLY.**"""
        services = ledger.read_services()
        queries = ledger.read_queries()
        st_dist: dict = {}
        for s in services:
            st_dist[s.get("service_type")] = st_dist.get(s.get("service_type"), 0) + 1
        layer_dist: dict = {}
        for q in queries:
            layer_dist[q.get("target_layer")] = layer_dist.get(q.get("target_layer"), 0) + 1
        rid = M.report_id(scope, now)
        rec = GatewayReportRecord(
            report_id=rid, scope=scope, service_count=len(services), query_count=len(queries),
            response_count=len(ledger.read_responses()),
            service_type_distribution=dict(sorted(st_dist.items())),
            layer_distribution=dict(sorted(layer_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return GatewayReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.research_api_gateway.verify import verify_chain
        return verify_chain()

    def summary(self, now="") -> GatewaySummary:
        return GatewaySummary(
            timestamp=now, service_count=len(ledger.read_services()),
            query_count=len(ledger.read_queries()), response_count=len(ledger.read_responses()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
