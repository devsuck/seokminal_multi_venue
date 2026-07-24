"""벤치마크 리포트·이력·비교 (P14) — 결정적. **기록/비교 전용, 원본 원장 불변.**

스위트 실행 결과를 정렬된 결정적 리포트로 집계한다. 이력은 append-only(bench_history.jsonl, 별도 네임스페이스)로
기록하며, 비교는 이전/현재 리포트의 per_iter 를 대조해 회귀/개선을 결정적으로 산출한다.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass

from jarvis.config import state_path

HISTORY_FILE = "bench_history.jsonl"


def _h(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class BenchmarkReport:
    label: str
    generated_at: str
    results: list           # BenchmarkResult.to_dict() 목록(name 정렬)
    total_elapsed: float
    checksum: str           # 작업 결정성 지문(name+checksum, 타이밍 제외)

    def to_dict(self) -> dict:
        return asdict(self)


def build_report(label: str, results: list, generated_at: str = "") -> BenchmarkReport:
    """결과 목록 → 결정적 리포트(name 정렬, 작업 checksum 집계)."""
    dicts = sorted((r.to_dict() if hasattr(r, "to_dict") else dict(r) for r in results),
                   key=lambda d: d["name"])
    total = round(sum(d["elapsed"] for d in dicts), 9)
    work_fingerprint = _h([(d["name"], d["checksum"], d["work_units"]) for d in dicts])
    return BenchmarkReport(label=label, generated_at=generated_at, results=dicts,
                           total_elapsed=total, checksum=work_fingerprint)


def append_history(report: BenchmarkReport) -> None:
    """이력 append(별도 네임스페이스 파일). 원본 원장 불변."""
    p = state_path(HISTORY_FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(report.to_dict(), ensure_ascii=False, default=str) + "\n")


def read_history() -> list[dict]:
    p = state_path(HISTORY_FILE)
    if not os.path.exists(p):
        return []
    out: list[dict] = []
    with open(p) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except (ValueError, json.JSONDecodeError):
                    continue
    return out


def compare_reports(previous: dict, current: dict, *, tolerance: float = 0.0) -> dict:
    """이전/현재 리포트 per_iter 대조 → 회귀/개선(결정적). tolerance: 상대 허용치.

    반환: {same_workload, regressions[], improvements[], unchanged[]}
    """
    prev_map = {r["name"]: r for r in previous.get("results", [])}
    cur_map = {r["name"]: r for r in current.get("results", [])}
    regressions: list = []
    improvements: list = []
    unchanged: list = []
    for name in sorted(set(prev_map) & set(cur_map)):
        p_it = prev_map[name]["per_iter"]
        c_it = cur_map[name]["per_iter"]
        thresh = p_it * (1.0 + tolerance)
        if c_it > thresh and c_it > p_it:
            regressions.append({"name": name, "previous": p_it, "current": c_it,
                                "delta": round(c_it - p_it, 9)})
        elif c_it < p_it * (1.0 - tolerance) and c_it < p_it:
            improvements.append({"name": name, "previous": p_it, "current": c_it,
                                 "delta": round(c_it - p_it, 9)})
        else:
            unchanged.append(name)
    same_workload = previous.get("checksum") == current.get("checksum")
    return {"same_workload": same_workload, "regressions": regressions,
            "improvements": improvements, "unchanged": sorted(unchanged),
            "added": sorted(set(cur_map) - set(prev_map)),
            "removed": sorted(set(prev_map) - set(cur_map))}
