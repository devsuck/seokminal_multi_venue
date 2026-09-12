# Vultr Seoul 백업/재해복구 — 서브프로젝트5

> `docs/deploy/vultr-seoul.md`(서브1)·`vultr-seoul-jobs.md`(서브2) 후속.

## 스코프

**최초 이관**(맥→VM 1회성 데이터 이동)은 이 문서 범위 아님 —
`docs/deploy/oracle-pilot.md` 5단계 rsync 런북 그대로 재사용(VM 주소만 교체).
이 문서는 **VM 운영중 지속 백업**(디스크 장애/실수 삭제 대비).

## 백업 대상

재생성 불가한 것만(재수집 가능한 시장데이터 캐시는 제외 — 디스크 절약, 장애시
그냥 다시 받으면 됨):

| 포함 | 제외 (재수집 가능) |
|---|---|
| `jarvis/_state/` (포지션·PnL·audit 원장, 3MB) | `data/krx`, `data/dart_financials`, `data/kr*`, `data/intraday`, `data/funding`, `data/openinsider` (총 550MB+) |
| `catalog/` (1MB) | `research/data/` (이미 90일 prune 정책 있음, `research/prune_old_data.py`) |
| `data/order_audit.jsonl`, `data/agents.db`, `data/graph_history.jsonl` | |

압축 전 ~10MB — 매일 백업해도 디스크 부담 없음.

## 구성 — 2단계 이중화

1. **로컬 rotate 백업** (이 서브프로젝트에서 구현): `scripts/backup_state.sh`가
   매일 tar.gz 스냅샷을 `backups/`에 남기고 7일치만 보관(`SEOKMINAL_BACKUP_RETENTION_DAYS`
   로 조정). 실수 삭제·로직버그로 인한 원장 손상 대비. **VM/디스크 전체 소실에는
   무의미**(백업이 같은 디스크에 있음) — 그래서 2번 필요.
2. **Vultr 볼륨 스냅샷** (사람이 직접 — 결제 연동이라 대행 불가): Vultr 대시보드
   → 서버 → Snapshots → 주 1회 정도 자동 스냅샷 예약. 디스크/VM 자체가 죽어도
   여기서 완전 복구 가능. 월 몇백원~1천원대 추가 요금.

오프사이트(S3 등) 3중 백업은 이 규모(1인 운영, 페이퍼 단계, 원장 10MB대)엔 과함(YAGNI)
— 필요해지면 `scripts/backup_state.sh` 끝에 rclone 업로드 한 줄 추가하면 됨.

## 설치 (VM에서)

```bash
cd ~/seokminal-multi-venue
sudo cp scripts/deploy/systemd/seokminal-backup-state.{service,timer} /etc/systemd/system/
# <REPO_USER>/<REPO_PATH> 치환
sudo systemctl daemon-reload
sudo systemctl enable --now seokminal-backup-state.timer
```

Vultr 스냅샷은 대시보드에서 별도 설정(위 참고).

## 검증

```bash
sudo systemctl start seokminal-backup-state
ls -lh backups/           # backup-<오늘날짜>.tar.gz 생성 확인
tar tzf backups/backup-*.tar.gz | head    # 내용물 확인
```

## 복구 절차 (재해시)

```bash
# 최신 백업 압축해제(repo root에서)
tar xzf backups/backup-<날짜>.tar.gz -C .
bash scripts/restart_api.sh 유사하게 서비스 재시작
```

VM 자체가 죽었다면: Vultr 스냅샷으로 새 인스턴스 복원 → 위 tar.gz 복구는
스냅샷 시점 이후 데이터만 보충하는 용도로 병행.
