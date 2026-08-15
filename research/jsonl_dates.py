"""날짜기반 jsonl 로더 공용 헬퍼.

`research/compress_old_data.py`가 2일 지난 파일을 `.jsonl.gz`로 압축하는데,
날짜 나열(glob)과 파일 열기 양쪽 다 `.gz`를 모르는 리더가 많아 압축된 과거
데이터가 무음으로 안 보이던 문제(2026-08-15 발견 — sharp_wallet 검증러너가
과거 데이터 씹혀서 최근 2~3일치만 본 걸 뒤늦게 알아챔). cross_venue_skew의
`load_venue_snapshots`가 오프너는 gz-aware였지만 정작 그 앞단 `_available_dates()`가
glob이라 gz 날짜 자체를 못 찾던 것도 같은 버그 계열 — 여기 하나로 합쳐 재사용."""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def list_dates(dirpath: Path, glob_prefix: str = "") -> list[str]:
    """dirpath 밑 `{glob_prefix}*.jsonl`/`.jsonl.gz` 매칭 파일명에서 YYYY-MM-DD만 뽑아 정렬."""
    dates = set()
    if not dirpath.is_dir():
        return []
    for suffix in (".jsonl", ".jsonl.gz"):
        for path in dirpath.glob(f"{glob_prefix}*{suffix}"):
            m = _DATE_RE.search(path.name)
            if m:
                dates.add(m.group(1))
    return sorted(dates)


def open_stem(dirpath: Path, stem: str):
    """`{dirpath}/{stem}.jsonl`(.gz) 중 존재하는 쪽을 텍스트모드로 연다. 없으면 None."""
    plain = dirpath / f"{stem}.jsonl"
    if plain.exists():
        return plain.open()
    gz = dirpath / f"{stem}.jsonl.gz"
    if gz.exists():
        return gzip.open(gz, "rt")
    return None


def iter_all_rows(dirpath: Path) -> list[dict]:
    """dirpath 밑 모든 `*.jsonl`(.gz) 파일을 파일명순으로 읽어 dict 리스트로 합친다."""
    if not dirpath.is_dir():
        return []
    paths = sorted(
        list(dirpath.glob("*.jsonl")) + list(dirpath.glob("*.jsonl.gz")),
        key=lambda p: p.name.removesuffix(".gz"),
    )
    rows: list[dict] = []
    for path in paths:
        opener = path.open if path.suffix == ".jsonl" else (lambda p=path: gzip.open(p, "rt"))
        with opener() as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows
