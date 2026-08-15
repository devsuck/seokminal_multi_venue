"""노드 스코어 이력 — /graph/history/{node_id}.

버그: 프론트 /infra의 "병목 스코어 추세" 패널이 이 엔드포인트를 부르는데 서버에 아예
라우트가 없어 404 → 항상 빈 배열 → 패널이 영구 미표시였다(2026-08-06 발견).
패치 때마다 스냅샷이 쌓이고, 노드별로 시간순 필터되는지 확인.
"""
from __future__ import annotations

import json

import api_server.graph_api as g


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "_GRAPH_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(g, "_HISTORY_PATH", tmp_path / "graph_history.jsonl")


def test_history_empty_before_any_patch(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert g.get_node_history("nvidia")["history"] == []


def test_patch_appends_snapshot_per_node_and_filters_by_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    g.patch_graph({"nodes": [{"id": "nvidia", "bottleneck_score": 0.5}]})
    g.patch_graph({"nodes": [{"id": "nvidia", "bottleneck_score": 0.7}]})

    h = g.get_node_history("nvidia")["history"]
    assert [r["bottleneck_score"] for r in h] == [0.5, 0.7]      # 오래된 것 → 최신
    assert all(r["node_id"] == "nvidia" for r in h)
    # 같은 패치에서 다른 노드도 함께 스냅샷됨(추세 비교용)
    assert len(g.get_node_history("tsmc")["history"]) == 2


def test_history_limit_keeps_latest(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    rows = [{"ts": f"2026-08-0{i}", "node_id": "nvidia", "bottleneck_score": i / 10} for i in range(1, 6)]
    (tmp_path / "graph_history.jsonl").write_text("\n".join(json.dumps(r) for r in rows))

    h = g.get_node_history("nvidia", limit=2)["history"]
    assert [r["bottleneck_score"] for r in h] == [0.4, 0.5]
