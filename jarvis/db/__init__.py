"""jarvis.db — SQLite Projection Layer (P3).

JSONL = 불변 진실. SQLite index.db = 재생성 가능한 프로젝션/인덱스(disposable).
소유권 이전 없음. 삭제 후 rebuild하면 동일 상태 복원.
"""
from jarvis.db.projector import ProjectionReport, rebuild, source_checksum  # noqa: F401
from jarvis.db.sqlite import Database, db_path, exists  # noqa: F401
from jarvis.db.verify import verify  # noqa: F401
