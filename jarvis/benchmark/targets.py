"""벤치마크 타겟 (P14) — 결정적 합성 워크로드. **자체 완결·부작용 없음(임시 파일 제외).**

기존 원장/모듈을 건드리지 않고, 대표 연산 형태를 합성 데이터로 재현해 성능 특성을 측정한다. 각 타겟은 결정적 값을
반환하여 재현성(checksum)을 보장한다. 측정 대상: 원장 append·replay·해시 검증·계보 순회·지식 그래프 순회·시뮬레이션
replay·의사결정 평가·메모리 검색·에이전트 워크플로·OS 스냅샷.
"""
from __future__ import annotations

import hashlib
import json
import os


def _h(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def make_records(n: int) -> list[dict]:
    """결정적 합성 레코드 n 개(해시체인 형태)."""
    recs: list[dict] = []
    prev = "GENESIS"
    for i in range(n):
        core = {"id": f"R{i:06d}", "seq": i, "payload": f"p{i % 97}"}
        rec_hash = "sha256:" + _h({**core, "previous_hash": prev})
        recs.append({**core, "previous_hash": prev, "record_hash": rec_hash})
        prev = rec_hash
    return recs


def ledger_append(path: str, n: int) -> int:
    """원장 append 속도(임시 파일에 n 레코드 기록). 반환: 기록 바이트 수."""
    total = 0
    with open(path, "w") as f:
        for rec in make_records(n):
            line = json.dumps(rec, ensure_ascii=False) + "\n"
            total += len(line)
            f.write(line)
    return total


def replay(records: list[dict]) -> str:
    """replay 속도(해시체인 재계산). 반환: 최종 체인 지문."""
    prev = "GENESIS"
    for r in records:
        prev = "sha256:" + _h({"id": r["id"], "seq": r["seq"], "payload": r["payload"],
                               "previous_hash": prev})
    return prev


def hash_verification(records: list[dict]) -> int:
    """해시 검증 속도. 반환: 검증 통과 레코드 수."""
    ok = 0
    prev = "GENESIS"
    for r in records:
        expect = "sha256:" + _h({"id": r["id"], "seq": r["seq"], "payload": r["payload"],
                                 "previous_hash": prev})
        if r.get("record_hash") == expect:
            ok += 1
        prev = r.get("record_hash")
    return ok


def make_tree(n: int) -> dict:
    """계보 트리(부모 링크). 노드 i 의 부모는 (i-1)//2."""
    return {f"A{i}": (f"A{(i - 1) // 2}" if i > 0 else "") for i in range(n)}


def lineage_traversal(tree: dict) -> int:
    """계보 순회(각 노드에서 루트까지 조상 수 합)."""
    total = 0
    for node in tree:
        cur = node
        while tree.get(cur):
            cur = tree[cur]
            total += 1
    return total


def make_graph(n: int, degree: int = 3) -> dict:
    """지식 그래프(노드→이웃). 결정적 인접."""
    return {i: sorted({(i * (k + 1) + 7) % n for k in range(degree)} - {i}) for i in range(n)}


def graph_traversal(graph: dict, start: int = 0) -> int:
    """지식 그래프 BFS(방문 노드 수)."""
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for nb in graph.get(node, ()):
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen)


def simulation_replay(steps: int) -> float:
    """시뮬레이션 replay(결정적 상태 진행). 반환: 최종 상태값."""
    state = 1.0
    for i in range(steps):
        state = (state * 1.0000001 + (i % 13) * 0.0001) % 1000.0
    return round(state, 6)


def decision_evaluation(candidates: int) -> int:
    """의사결정 평가(합성 후보 점수화 → 최고 점수 인덱스)."""
    best_i, best_s = -1, -1
    for i in range(candidates):
        score = (i * 31 + 17) % 101
        if score > best_s:
            best_s, best_i = score, i
    return best_i


def memory_retrieval(n: int, queries: int) -> int:
    """메모리 검색(딕셔너리 인덱스 조회). 반환: 적중 수."""
    index = {f"K{i}": i for i in range(n)}
    hits = 0
    for q in range(queries):
        if f"K{(q * 7) % n}" in index:
            hits += 1
    return hits


def agent_workflow(steps: int) -> str:
    """에이전트 워크플로(상태 머신 진행). 반환: 최종 상태."""
    states = ["INIT", "PLAN", "ACT", "OBSERVE", "RECORD"]
    s = 0
    for i in range(steps):
        s = (s + 1 + (i % 2)) % len(states)
    return states[s]


def os_snapshot_generation(layers: int, per_layer: int) -> dict:
    """OS 스냅샷 생성(계층별 카운트 집계). 반환: 결정적 집계."""
    counts = {f"L{i}": (i + 1) * per_layer for i in range(layers)}
    return {"layers": layers, "total": sum(counts.values()),
            "counts": dict(sorted(counts.items()))}
