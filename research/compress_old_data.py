"""research/data/ 밑 오래된 raw tick/스냅샷 로그를 gzip으로 압축 — 삭제 아님.

파일명에 박힌 YYYY-MM-DD 날짜만 신뢰한다(append-only 파일의 mtime은 마지막 쓰기
시점이라 부정확 — `prune_old_data.py`와 동일 원칙). 최근 N일은 아직 쓰기 중일 수
있어 건드리지 않는다. 이미 .gz인 파일과 날짜 없는 파일은 건너뛴다.

읽는 쪽이 .jsonl.gz를 모르면 압축한 과거 데이터가 무음으로 유실된 것처럼 보이므로,
압축 대상 디렉토리를 넓힐 땐 해당 리더가 .gz도 찾아보게 같이 고칠 것
(`research/hypotheses/cross_venue_skew.py::load_venue_snapshots` 참고).
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import re
import shutil
from pathlib import Path

DATA_ROOT = Path("research/data")
KEEP_RECENT_DAYS = 2
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def find_compressible_files(
    root: Path = DATA_ROOT,
    keep_recent_days: int = KEEP_RECENT_DAYS,
    today: dt.date | None = None,
) -> list[Path]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    cutoff = today - dt.timedelta(days=keep_recent_days)
    targets = []
    for path in root.rglob("*.jsonl"):
        if not path.is_file():
            continue
        m = _DATE_RE.search(path.name)
        if not m:
            continue
        try:
            file_date = dt.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if file_date < cutoff:
            targets.append(path)
    return targets


def compress(
    root: Path = DATA_ROOT,
    keep_recent_days: int = KEEP_RECENT_DAYS,
    dry_run: bool = False,
    today: dt.date | None = None,
) -> list[Path]:
    targets = find_compressible_files(root, keep_recent_days, today=today)
    if not dry_run:
        for path in targets:
            gz_path = path.with_suffix(path.suffix + ".gz")
            with path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            path.unlink()
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description="research/data/ 밑 오래된 raw 로그 gzip 압축(삭제 아님)")
    parser.add_argument("--root", type=Path, default=DATA_ROOT,
                        help="특정 수집기 디렉토리만 대상으로 하려면 지정 "
                             "(예: research/data/polymarket_tick) — 리더가 .gz를 모르면 "
                             "그 디렉토리는 지정하지 말 것")
    parser.add_argument("--keep-recent-days", type=int, default=KEEP_RECENT_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    targets = compress(root=args.root, keep_recent_days=args.keep_recent_days, dry_run=args.dry_run)
    verb = "압축 예정" if args.dry_run else "압축됨"
    print(f"{len(targets)}개 파일 {verb}")
    for path in targets:
        print(f"  {path}")


if __name__ == "__main__":
    main()
