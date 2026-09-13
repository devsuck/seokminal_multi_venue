# Vultr Seoul 컷오버 + 드라이런 — 서브프로젝트6

> `docs/deploy/oracle-pilot.md` 5·6단계 + 서브1~5 결과 통합. **이 문서는 런북만—
> 실행은 VM 생성(서브1 1단계, 결제/SSH키 필요, 대행 불가) 이후 사람이 진행.**
> 며칠 단위 실측 관찰이 전제라 자동화로 "완료"될 수 있는 작업이 아님.

## 전제조건 (서브1~5 모두 완료 확인)

- [ ] 서브1: VM 생성, nginx+HTTPS, API/대시보드 systemd 상시구동 (`vultr-seoul.md`)
- [ ] 서브2: 배치잡 9개→5개 systemd timer/service 이전 (`vultr-seoul-jobs.md`)
- [ ] 서브3: `COOKIE_SAMESITE=none`, `COOKIE_SECURE=true`, `CORS_ORIGINS` VM `.env`에 반영
- [ ] 서브4: `.env` scp 이관 완료, `.env.example` 최신본 대조로 누락 키 없음 확인
- [ ] 서브5: `seokminal-backup-state.timer` 활성화 확인

## 1단계 — 데이터/상태 마이그레이션 (맥 → VM, `oracle-pilot.md` 5단계 패턴)

⚠️ 봇 켜기 **전에** 먼저 옮길 것 — 안 그러면 포지션/PnL 연속성 끊김.
⚠️ 이전 중 맥·VM에서 같은 봇 동시 실행 금지(이중 주문/상태 충돌).

```bash
# 맥에서 실행 (VM으로 push)
cd <맥의 seokminal-multi-venue>
VM=<REPO_USER>@<VM-공인IP>

rsync -avz jarvis/_state/   $VM:~/seokminal-multi-venue/jarvis/_state/
rsync -avz catalog/         $VM:~/seokminal-multi-venue/catalog/
rsync -avz data/order_audit.jsonl data/agents.db data/graph_history.jsonl \
                             $VM:~/seokminal-multi-venue/data/
# 시장데이터 캐시(krx/dart_financials/kr* 등)는 재수집 가능 — 급하면 생략,
# 옮기고 싶으면 용량(550MB+) 감안해서 별도로.
```

체크리스트: `jarvis/_state/`, `catalog/`, `data/order_audit.jsonl`, `data/agents.db`,
`data/graph_history.jsonl` — 서브5 백업 스코프와 동일(재생성 불가한 것 = 이전 필수 대상).

## 2단계 — go/no-go 게이트

| 확인 | 명령 | 기준 |
|---|---|---|
| KIS 해외IP 관문 | `python scripts/deploy/test_kis_connectivity.py` (VM) | PASS (Seoul 리전이라 오라클보다 유리, 서브1 4단계 참고) |
| API 헬스 | `curl https://api.<도메인>/health` | 200 |
| 대시보드 로드+API 연동 | 브라우저 `https://app.<도메인>` | 로드 + API 호출 성공 (CORS 확인) |
| 세션 로그인 | 브라우저로 로그인 → 새로고침 유지 | 쿠키 유지됨 (`SameSite=None; Secure` 정상 동작 확인 — 서브3) |
| 배치잡 타이머 | `systemctl list-timers` | 5개 전부 `enabled`, 다음 실행시각 정상 |
| Claude API 키 | `.env`의 `ANTHROPIC_API_KEY` 값 확인 | 채워짐 — 없으면 `ai_portfolio`/lv5 에이전트 리뷰가 헤드리스 VM에서 조용히 no-op (`api_server/claude_cli.py`) |
| 백업 잡 | `sudo systemctl start seokminal-backup-state && ls backups/` | tar.gz 생성됨 |
| 재부팅 복구 | `sudo reboot` 후 | API/대시보드/timer 전부 자동 기동 |

하나라도 FAIL이면 컷오버 중단, 원인 해결 후 재확인. 이 단계에서 맥은 계속 fallback 유지.

## 3단계 — 드라이런 (며칠, 맥은 fallback 유지)

- 관찰 기간: 최소 3~4일 (군 입대 2026-10-19 전 여유 두고 역산해서 시작일 결정)
- 매일 확인: `journalctl -u seokminal-api --since today | grep -i error`,
  `systemctl status seokminal-api-watchdog`(RSS/health 재기동 로그 있는지),
  `ls -lh backups/`(매일 한 개씩 쌓이는지), 포지션/PnL 원장이 맥에서 본 것과 일치하는지.
- 이 기간 맥은 **켜두되 봇은 끔**(중복 실행 방지) — 롤백 필요시 즉시 재개 가능하게.
- 드라이런 중 하나라도 크래시/데이터유실/KIS 차단 발생 → 롤백(아래), 원인 조사 후
  드라이런 재시작.

## 4단계 — 컷오버 확정 & 맥 종료

드라이런 무사고로 끝나면:
1. 맥에서 최종 델타 rsync(드라이런 기간 맥 fallback 데이터 있었다면) — 보통 봇 꺼놨으면
   델타 없음.
2. 맥 봇/서비스 전부 종료 확인.
3. 맥 종료. 여기서부터 상시구동은 전적으로 VM.
4. 문제 재발 시 롤백 경로(아래)는 맥을 다시 켜는 것 — 군 입대 전까지는 맥을 완전
   폐기하지 말고 예비로 둘 것 권장.

## 롤백

- VM 서비스 중단(`sudo systemctl stop seokminal-api seokminal-dashboard`), 맥에서
  기존 방식대로(`bash scripts/restart_api.sh`) 재개.
- VM은 그대로 두고(원인 조사용) 맥에서 정상 운영 재개 — 데이터 유실 없음(서브5 백업 +
  1단계 이관 시점 데이터가 VM에 남아있음).

## 이 세션이 자율로 할 수 없는 것 (실행은 VM 생성 후 사람 확인 필요)

- VM 생성 자체 (결제/SSH키, 서브1 1단계)
- 1단계 rsync 실행 (맥→VM 실제 데이터 전송)
- 2단계 go/no-go 게이트 실측
- 3단계 며칠 관찰 (실제 경과시간 필요, 자동화 불가)
- 4단계 맥 종료 판단
