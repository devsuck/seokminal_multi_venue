# Vultr Seoul 배치잡 이전 — launchd → systemd timer

> `docs/deploy/vultr-seoul.md`(서브프로젝트1: VM+API/대시보드 상시서비스) 후속.
> 이 문서는 서브프로젝트2 — 나머지 launchd 배치잡을 systemd timer/service로 옮기는 작업.

## 맥 launchd 잡 9개 중 매핑

| launchd job | 트리거 | 처리 |
|---|---|---|
| api, dashboard | 상시 | 서브1에서 이미 처리(`vultr-seoul.md`) |
| ai-portfolio | 주1(월07:00) | → `seokminal-ai-portfolio.timer` |
| autoresearch | 주1(일05:00) | → `seokminal-autoresearch.timer` |
| prune-research-data | 매일04:00 | → `seokminal-prune-research-data.timer` |
| research-ledger-sync | 평일08:00 | → `seokminal-research-ledger-sync.timer` |
| api-watchdog | 상시(uvicorn 행 감지) | → `seokminal-api-watchdog.service` |
| tailscale-watchdog | 상시 | **제외** — 맥 로컬 GUI 앱(Tailscale.app) 재기동 전용 로직, VM은 공인IP+도메인 직결이라 tailscale 자체를 안 씀 |
| collectors | 매분 | **제외** — `ensure_collectors.sh`의 desired-state 배열이 09-03부로 전부 비활성(메모리 경합 대응), 지금 옮겨도 no-op. 나중에 수집기 다시 켤 일 생기면 그때 추가 |

## 코드 변경 1건

`ops/api_watchdog.py`의 `RSS_LIMIT_MB`를 `SEOKMINAL_RSS_LIMIT_MB` 환경변수로 오버라이드
가능하게 함(기본값 4000 유지, 맥은 무변경). VM `.env`에 추가:

```
SEOKMINAL_RSS_LIMIT_MB=400
```

(1GB VM 기준 — RAM의 약 40%. 다른 스펙으로 가면 비례 조정)

## 설치 (VM에서)

```bash
cd ~/seokminal-multi-venue
sudo cp scripts/deploy/systemd/seokminal-{ai-portfolio,autoresearch,prune-research-data,research-ledger-sync}.{service,timer} \
       scripts/deploy/systemd/seokminal-api-watchdog.service \
       /etc/systemd/system/
# 각 .service 파일 안 <REPO_USER>/<REPO_PATH> 치환(주석 참고)
sudo systemctl daemon-reload
sudo systemctl enable --now seokminal-ai-portfolio.timer seokminal-autoresearch.timer \
    seokminal-prune-research-data.timer seokminal-research-ledger-sync.timer \
    seokminal-api-watchdog
```

## 검증

- `systemctl list-timers` — 4개 timer 다음 실행시각 확인
- 수동 1회 트리거로 스모크: `sudo systemctl start seokminal-ai-portfolio && journalctl -u seokminal-ai-portfolio -n 50`
  (나머지 3개 timer도 동일하게)
- `systemctl status seokminal-api-watchdog` — active(running) 확인, 로그에 헬스체크 폴링 찍히는지
