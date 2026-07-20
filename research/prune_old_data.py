"""research/data/ 밑에 쌓이는 raw tick/스냅샷 로그가 무제한 커지는 걸 막는 정리 스크립트.

파일명에 박힌 YYYY-MM-DD 날짜만 신뢰한다 — append-only 파일의 mtime은 마지막 쓰기
시점이라 날짜 판단에 부정확하다. 날짜가 안 박힌 파일은 안전하게 건너뛴다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

DATA_ROOT = Path("research/data")
RETENTION_DAYS = 90
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def find_expired_files(
    root: Path = DATA_ROOT,
    retention_days: int = RETENTION_DAYS,
    today: dt.date | None = None,
) -> list[Path]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    cutoff = today - dt.timedelta(days=retention_days)
    expired = []
    for path in root.rglob("*"):
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
            expired.append(path)
    return expired


def prune(
    root: Path = DATA_ROOT,
    retention_days: int = RETENTION_DAYS,
    dry_run: bool = False,
) -> list[Path]:
    expired = find_expired_files(root, retention_days)
    if not dry_run:
        for path in expired:
            path.unlink()
    return expired


def main() -> None:
    parser = argparse.ArgumentParser(description="research/data/ 밑 retention 기간 지난 raw 로그 삭제")
    parser.add_argument("--retention-days", type=int, default=RETENTION_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    deleted = prune(retention_days=args.retention_days, dry_run=args.dry_run)
    verb = "삭제 예정" if args.dry_run else "삭제됨"
    print(f"{len(deleted)}개 파일 {verb}")
    for path in deleted:
        print(f"  {path}")


if __name__ == "__main__":
    main()
