"""Knowledge Sharing 원장 (P11.8) — 12개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 ksh_ 접두사(Knowledge SHaring). 각 레코드: id · timestamp · previous_hash · record_hash. 에이전트 간
지식 공유 — 공유·기록만, 실행/연구결과변경/상위원장수정/배포승인 없음. 상위 계층은 **READ ONLY** — 소스 참조는
파일만 읽고 절대 쓰지 않는다. import 결합 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (ksh_ 접두사)
REGISTRY = ("ksh_registry.jsonl", "registry_id")       # Knowledge Registry
TOPICS = ("ksh_topics.jsonl", "topic_id")              # Knowledge Topics
ENTRIES = ("ksh_entries.jsonl", "entry_event_id")      # Knowledge Entries (event-sourced)
SOURCES = ("ksh_sources.jsonl", "source_id")           # Knowledge Sources
LINKS = ("ksh_links.jsonl", "link_id")                 # Knowledge Links
TRANSFERS = ("ksh_transfers.jsonl", "transfer_id")     # Knowledge Transfers
CONSUMERS = ("ksh_consumers.jsonl", "consumer_id")     # Knowledge Consumers
RATINGS = ("ksh_ratings.jsonl", "rating_id")           # Knowledge Ratings
SNAPSHOTS = ("ksh_snapshots.jsonl", "snapshot_id")     # Knowledge Snapshots
REPORTS = ("ksh_reports.jsonl", "report_id")           # Knowledge Reports
ARTIFACTS = ("ksh_artifacts.jsonl", "artifact_id")     # Knowledge Artifacts
LINEAGE = ("ksh_lineage.jsonl", "lineage_id")          # Knowledge Lineage

ALL_LEDGERS = (REGISTRY, TOPICS, ENTRIES, SOURCES, LINKS, TRANSFERS, CONSUMERS, RATINGS,
               SNAPSHOTS, REPORTS, ARTIFACTS, LINEAGE)

# ── 상위 소스 원장(READ ONLY) — 지식 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "research_kg": ("kg_entities.jsonl", "entity_id"),
    "knowledge_intelligence": ("ki_insights.jsonl", "insight_id"),
    "research_lifecycle": ("rl_events.jsonl", "event_id"),
    "research_council": ("cnl_consensus.jsonl", "consensus_id"),
}


def _append(filename: str, record: dict) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename: str) -> list[dict]:
    p = state_path(filename)
    if not os.path.exists(p):
        return []
    out: list[dict] = []
    with open(p) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except (ValueError, json.JSONDecodeError):
                continue
    return out


def _head(filename: str) -> dict | None:
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename: str, id_field: str, rid: str) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


def _get(filename: str, id_field: str, rid: str) -> dict | None:
    for r in read_jsonl(filename):
        if r.get(id_field) == rid:
            return r
    return None


# ── 상위 소스 READ ONLY ──
def source_ref_exists(layer: str, ref: str) -> bool:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


# ── Registry ──
def append_registry(rec: dict) -> None:
    _append(REGISTRY[0], rec)


def read_registry() -> list[dict]:
    return read_jsonl(REGISTRY[0])


def registry_head() -> dict | None:
    return _head(REGISTRY[0])


def registry_exists(registry_id: str) -> bool:
    return _exists(REGISTRY[0], REGISTRY[1], registry_id)


def get_registry(registry_id: str) -> dict | None:
    return _get(REGISTRY[0], REGISTRY[1], registry_id)


# ── Topics ──
def append_topic(rec: dict) -> None:
    _append(TOPICS[0], rec)


def read_topics() -> list[dict]:
    return read_jsonl(TOPICS[0])


def topics_head() -> dict | None:
    return _head(TOPICS[0])


def topic_exists(topic_id: str) -> bool:
    return _exists(TOPICS[0], TOPICS[1], topic_id)


def get_topic(topic_id: str) -> dict | None:
    return _get(TOPICS[0], TOPICS[1], topic_id)


# ── Entries (event-sourced) ──
def append_entry_event(rec: dict) -> None:
    _append(ENTRIES[0], rec)


def read_entry_events() -> list[dict]:
    return read_jsonl(ENTRIES[0])


def entries_head() -> dict | None:
    return _head(ENTRIES[0])


def entry_event_exists(entry_event_id: str) -> bool:
    return _exists(ENTRIES[0], ENTRIES[1], entry_event_id)


def entry_events(entry_id: str) -> list[dict]:
    return [r for r in read_entry_events() if r.get("entry_id") == entry_id]


def entry_ids() -> list[str]:
    return sorted({r.get("entry_id") for r in read_entry_events() if r.get("entry_id")})


# ── Sources ──
def append_source(rec: dict) -> None:
    _append(SOURCES[0], rec)


def read_sources() -> list[dict]:
    return read_jsonl(SOURCES[0])


def sources_head() -> dict | None:
    return _head(SOURCES[0])


def source_exists(source_id: str) -> bool:
    return _exists(SOURCES[0], SOURCES[1], source_id)


def get_source(source_id: str) -> dict | None:
    return _get(SOURCES[0], SOURCES[1], source_id)


# ── Links ──
def append_link(rec: dict) -> None:
    _append(LINKS[0], rec)


def read_links() -> list[dict]:
    return read_jsonl(LINKS[0])


def links_head() -> dict | None:
    return _head(LINKS[0])


def link_exists(link_id: str) -> bool:
    return _exists(LINKS[0], LINKS[1], link_id)


def links_of_type(link_type: str) -> list[dict]:
    return [r for r in read_links() if r.get("link_type") == link_type]


# ── Transfers ──
def append_transfer(rec: dict) -> None:
    _append(TRANSFERS[0], rec)


def read_transfers() -> list[dict]:
    return read_jsonl(TRANSFERS[0])


def transfers_head() -> dict | None:
    return _head(TRANSFERS[0])


def transfer_exists(transfer_id: str) -> bool:
    return _exists(TRANSFERS[0], TRANSFERS[1], transfer_id)


def entry_transfers(entry_id: str) -> list[dict]:
    return [r for r in read_transfers() if r.get("entry_id") == entry_id]


# ── Consumers ──
def append_consumer(rec: dict) -> None:
    _append(CONSUMERS[0], rec)


def read_consumers() -> list[dict]:
    return read_jsonl(CONSUMERS[0])


def consumers_head() -> dict | None:
    return _head(CONSUMERS[0])


def consumer_exists(consumer_id: str) -> bool:
    return _exists(CONSUMERS[0], CONSUMERS[1], consumer_id)


def entry_consumers(entry_id: str) -> list[dict]:
    return [r for r in read_consumers() if r.get("entry_id") == entry_id]


# ── Ratings ──
def append_rating(rec: dict) -> None:
    _append(RATINGS[0], rec)


def read_ratings() -> list[dict]:
    return read_jsonl(RATINGS[0])


def ratings_head() -> dict | None:
    return _head(RATINGS[0])


def rating_exists(rating_id: str) -> bool:
    return _exists(RATINGS[0], RATINGS[1], rating_id)


def get_rating(rating_id: str) -> dict | None:
    return _get(RATINGS[0], RATINGS[1], rating_id)


def entry_ratings(entry_id: str) -> list[dict]:
    return [r for r in read_ratings() if r.get("entry_id") == entry_id]


# ── Snapshots ──
def append_snapshot(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_exists(snapshot_id: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)


def get_snapshot(snapshot_id: str) -> dict | None:
    return _get(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)


# ── Lineage ──
def append_lineage(rec: dict) -> None:
    _append(LINEAGE[0], rec)


def read_lineage() -> list[dict]:
    return read_jsonl(LINEAGE[0])


def lineage_head() -> dict | None:
    return _head(LINEAGE[0])


def lineage_exists(lineage_id: str) -> bool:
    return _exists(LINEAGE[0], LINEAGE[1], lineage_id)
