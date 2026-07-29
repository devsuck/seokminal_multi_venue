"""아티팩트 검증 (P15) — 리포트·스냅샷·벤치마크·그래프·시뮬레이션·연구 산출물. **읽기 전용·결정적.**

생성된 아티팩트의 구조·불변 표식(is_binding=False)·체크섬을 검증한다. 원본을 수정하지 않는다(완전 additive).
"""
from __future__ import annotations

import hashlib
import json

# 아티팩트 종류별 필수 필드
_REQUIRED = {
    "report": ("is_binding",),
    "snapshot": ("is_binding",),
    "benchmark": ("checksum", "results"),
    "graph_export": ("nodes", "edges"),
    "simulation": ("result",),
    "research_report": ("is_binding",),
}


def _sha(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def validate_artifact(artifact: dict, kind: str) -> dict:
    """단일 아티팩트 검증(필수 필드 + is_binding=False 강제). **읽기 전용.**"""
    issues: list = []
    required = _REQUIRED.get(kind, ())
    for field in required:
        if field not in artifact:
            issues.append(f"missing:{field}")
    # 관찰 전용 아티팩트는 배포/결정 금지 표식
    if kind in ("report", "snapshot", "research_report"):
        if artifact.get("is_binding") is not False:
            issues.append("is_binding_not_false")
    return {"ok": not issues, "kind": kind, "issues": issues}


def verify_benchmark(benchmark: dict) -> dict:
    """벤치마크 리포트 검증: 결과 목록의 name 정렬 + checksum 존재."""
    issues: list = []
    if "checksum" not in benchmark:
        issues.append("missing:checksum")
    results = benchmark.get("results", [])
    names = [r.get("name") for r in results]
    if names != sorted(names):
        issues.append("results_not_sorted")
    if not all(r.get("checksum", "").startswith("sha256:") for r in results):
        issues.append("result_missing_checksum")
    return {"ok": not issues, "issues": issues, "result_count": len(results)}


def verify_snapshot(snapshot: dict) -> dict:
    """스냅샷 검증: is_binding=False + 카운트 필드 존재."""
    issues: list = []
    if snapshot.get("is_binding") is not False:
        issues.append("is_binding_not_false")
    has_count = any(k for k in snapshot if k.endswith("_count") or k.endswith("counts")
                    or k == "total_records")
    if not has_count:
        issues.append("no_count_field")
    return {"ok": not issues, "issues": issues}


def verify_graph_export(graph: dict) -> dict:
    """그래프 익스포트 검증: nodes/edges 정합(모든 edge 끝점이 node 집합 내)."""
    issues: list = []
    nodes = set(graph.get("nodes", []))
    edges = graph.get("edges", {})
    if isinstance(edges, dict):
        for src, dsts in edges.items():
            if src not in nodes:
                issues.append(f"edge_src_not_node:{src}")
            for d in dsts:
                if d not in nodes:
                    issues.append(f"edge_dst_not_node:{d}")
    return {"ok": not issues, "issues": sorted(set(issues)), "node_count": len(nodes)}


def verify_checksum(payload: dict, checksum_field: str = "checksum",
                    exclude: tuple = ("checksum", "generated_at", "serial_number")) -> dict:
    """체크섬 재계산 검증(지정 필드 제외한 본문의 SHA256)."""
    claimed = payload.get(checksum_field)
    core = {k: v for k, v in payload.items() if k not in exclude}
    actual = _sha(core)
    return {"ok": claimed == actual, "claimed": claimed, "actual": actual}


def validate_artifacts(artifacts: list) -> dict:
    """다중 아티팩트 검증. artifacts: [{"kind":..., "data":...}, ...] → 집계."""
    results = []
    for a in artifacts:
        results.append(validate_artifact(a.get("data", {}), a.get("kind", "")))
    ok = all(r["ok"] for r in results)
    return {"ok": ok, "count": len(results), "results": results,
            "failed": [r for r in results if not r["ok"]]}
