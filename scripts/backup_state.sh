#!/usr/bin/env bash
# 원장/상태 파일 로컬 스냅샷 — VM에서 systemd timer(매일)가 실행.
# 재수집 가능한 시장데이터 캐시(data/krx, dart_financials 등, research/data — 이미
# 90일 prune 정책 있음)는 제외. 재생성 불가한 것만: 포지션/PnL 원장, 주문감사로그,
# 에이전트 메모리 DB.
#
# 복구: tar xzf backups/backup-<날짜>.tar.gz -C / 로 원위치 압축해제 후 서비스 재시작.
# VM/디스크 전체 소실 대비는 이걸로 부족 — Vultr 대시보드에서 볼륨 스냅샷도 별도 켤 것
# (docs/deploy/vultr-seoul-backup.md 참고).
set -u

REPO_ROOT="${SEOKMINAL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKUP_DIR="${SEOKMINAL_BACKUP_DIR:-$REPO_ROOT/backups}"
RETENTION_DAYS="${SEOKMINAL_BACKUP_RETENTION_DAYS:-7}"

cd "$REPO_ROOT" || { echo "repo root 없음: $REPO_ROOT" >&2; exit 1; }
mkdir -p "$BACKUP_DIR"

STAMP="$(date '+%Y-%m-%d')"
OUT="$BACKUP_DIR/backup-$STAMP.tar.gz"

tar czf "$OUT" \
    jarvis/_state \
    catalog \
    data/order_audit.jsonl \
    data/agents.db \
    data/graph_history.jsonl \
    2>&1 | grep -v "^tar:.*No such file" # 파일 일부 없어도(신규 환경) 나머지는 백업

echo "$(date '+%F %T') 백업 완료: $OUT ($(du -h "$OUT" | cut -f1))"

find "$BACKUP_DIR" -name 'backup-*.tar.gz' -mtime "+$RETENTION_DAYS" -delete
