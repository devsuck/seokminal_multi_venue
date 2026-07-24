"""복구·크래시 진단 (P14) — 해시체인 원장 복구. **원본 원장 절대 불변, 복구본은 새 파일.**

기존 P9~P13 원장 형식(JSONL + previous_hash + record_hash, content_hash 관례 동일)을 읽어 손상 지점을 진단하고,
유효 프리픽스까지만 부분 replay 로 복구한다. **원본을 수정/삭제하지 않으며** 복구 결과는 별도 대상 파일에 기록한다.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"


def content_hash(record: dict) -> str:
    """프로젝트 관례와 동일: previous_hash/record_hash/report_hash 제외 후 SHA256[:16]."""
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def read_raw_lines(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [ln.rstrip("\n") for ln in f]


@dataclass(frozen=True)
class ScanResult:
    path: str
    total_lines: int
    valid_records: int
    first_broken: int          # -1 이면 손상 없음
    reason: str
    recoverable: bool

    def to_dict(self) -> dict:
        return asdict(self)


def scan_ledger(path: str, *, id_field: str | None = None) -> ScanResult:
    """원장을 스캔해 첫 손상 지점 탐지(체인·record_hash·JSON·중복). **읽기 전용.**"""
    lines = read_raw_lines(path)
    prev = GENESIS
    seen: set = set()
    valid = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            # 마지막 빈 줄은 무해; 중간 빈 줄은 손상으로 간주
            if i == len(lines) - 1:
                continue
            return ScanResult(path, len(lines), valid, i, "blank_line", valid > 0)
        try:
            rec = json.loads(s)
        except (ValueError, json.JSONDecodeError):
            return ScanResult(path, len(lines), valid, i, "invalid_json", valid > 0)
        if rec.get("previous_hash") != prev:
            return ScanResult(path, len(lines), valid, i, "previous_hash_broken", valid > 0)
        if not rec.get("record_hash"):
            return ScanResult(path, len(lines), valid, i, "missing_record_hash", valid > 0)
        if content_hash(rec) != rec.get("record_hash"):
            return ScanResult(path, len(lines), valid, i, "record_hash_mismatch", valid > 0)
        if id_field is not None:
            rid = rec.get(id_field)
            if rid in seen:
                return ScanResult(path, len(lines), valid, i, "duplicate_id", valid > 0)
            seen.add(rid)
        prev = rec["record_hash"]
        valid += 1
    return ScanResult(path, len(lines), valid, -1, "intact", True)


def partial_replay(path: str, *, id_field: str | None = None) -> list[dict]:
    """손상 지점 직전까지의 유효 프리픽스 레코드 반환(부분 replay 복구). **읽기 전용.**"""
    res = scan_ledger(path, id_field=id_field)
    lines = read_raw_lines(path)
    out: list[dict] = []
    limit = res.valid_records
    for ln in lines:
        if len(out) >= limit:
            break
        s = ln.strip()
        if not s:
            continue
        out.append(json.loads(s))
    return out


def validate_checkpoint(path: str, checkpoint: dict) -> dict:
    """체크포인트(seq, record_hash) 가 원장의 해당 위치와 일치하는지 검증. **읽기 전용.**

    checkpoint: {"seq": int, "record_hash": str}
    """
    recs = partial_replay(path)
    seq = checkpoint.get("seq")
    exp = checkpoint.get("record_hash")
    if seq is None or seq < 0 or seq >= len(recs):
        return {"valid": False, "reason": "seq_out_of_range", "seq": seq}
    actual = recs[seq].get("record_hash")
    return {"valid": actual == exp, "reason": "match" if actual == exp else "hash_mismatch",
            "seq": seq, "expected": exp, "actual": actual}


def verify_recoverable(path: str, *, id_field: str | None = None) -> dict:
    """복구 가능성 검증(유효 프리픽스 존재 여부). **읽기 전용.**"""
    res = scan_ledger(path, id_field=id_field)
    return {"recoverable": res.recoverable, "valid_records": res.valid_records,
            "total_lines": res.total_lines, "intact": res.first_broken == -1,
            "first_broken": res.first_broken, "reason": res.reason}


def recover_to_copy(src: str, dst: str, *, id_field: str | None = None) -> dict:
    """유효 프리픽스를 **새 파일 dst** 에 복구 기록. 원본 src 는 절대 건드리지 않는다.

    dst 가 이미 존재하면 거부(덮어쓰기 방지).
    """
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError("복구 대상은 원본과 달라야 한다(원본 불변)")
    if os.path.exists(dst):
        raise FileExistsError(f"복구 대상 존재 — 덮어쓰기 금지: {dst}")
    before = read_raw_lines(src)
    recs = partial_replay(src, id_field=id_field)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    after = read_raw_lines(src)
    return {"recovered": len(recs), "dst": dst, "source_unchanged": before == after}


def snapshot_recovery(path: str, snapshot: dict, *, count_field: str = "total_records") -> dict:
    """스냅샷의 집계 카운트가 현재 원장 유효 레코드 수와 정합한지 검증. **읽기 전용.**"""
    recs = partial_replay(path)
    claimed = snapshot.get(count_field)
    return {"consistent": claimed == len(recs), "claimed": claimed, "actual": len(recs)}


def diagnose_corruption(path: str, *, id_field: str | None = None) -> dict:
    """손상 상세 진단(라인별 문제 분류). **읽기 전용.**"""
    lines = read_raw_lines(path)
    issues: list = []
    prev = GENESIS
    seen: set = set()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            if i != len(lines) - 1:
                issues.append({"line": i, "issue": "blank_line"})
            continue
        try:
            rec = json.loads(s)
        except (ValueError, json.JSONDecodeError):
            issues.append({"line": i, "issue": "invalid_json"})
            prev = None
            continue
        if prev is not None and rec.get("previous_hash") != prev:
            issues.append({"line": i, "issue": "chain_break"})
        if not rec.get("record_hash"):
            issues.append({"line": i, "issue": "missing_hash"})
        elif content_hash(rec) != rec.get("record_hash"):
            issues.append({"line": i, "issue": "hash_mismatch"})
        if id_field is not None:
            rid = rec.get(id_field)
            if rid in seen:
                issues.append({"line": i, "issue": "duplicate_id"})
            seen.add(rid)
        prev = rec.get("record_hash")
    return {"path": path, "total_lines": len(lines), "issue_count": len(issues),
            "issues": issues, "corrupted": bool(issues)}
