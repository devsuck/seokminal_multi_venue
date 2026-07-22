"""jarvis.knowledge — Research Knowledge Graph (P4).

P3 SQLite projection 위에 세우는 설명가능 지식그래프. graph.db는 disposable 프로젝션.
JSONL = 불변 진실. 소스 무변경. 삭제 후 rebuild하면 동일 checksum.
"""
from jarvis.knowledge.builder import GraphReport, build, graph_checksum  # noqa: F401
from jarvis.knowledge.schema import NODE_TYPES, RELATIONS, graph_db_path, graph_exists  # noqa: F401
from jarvis.knowledge.verify import verify  # noqa: F401
