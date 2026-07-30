# 운영(ops) — 맥 상시구동 경화

원격 컨테이너가 아니라 **서버 돌리는 맥**에서 설치. 여기 스크립트는 자다가/자리 비운 사이
파이프가 끊기거나 실주문이 나가는 걸 막는 안전장치다.

## 1. 수집기 함대 워치독 (`collector_watchdog.py`)

`/lab/fleet`(신선도 verdict)를 폴링해 **dead** 수집기를 자동 재기동한다. 재기동은 기존
`/lab/collectors/{key}/restart`(멱등)를 호출 — launchd/tmux 결정과 무관하게 바로 붙는다.

```bash
# 수동 1회 (드라이런 확인)
python -m ops.collector_watchdog        # 상시 루프(120s). dead만 재기동.
python -m ops.collector_watchdog --restart-stale   # stale도 재기동(공격적)
```

### 상시화 — 택1

**A. tmux (기존 수집기와 동일 방식, 간단)**
```bash
tmux new-session -d -s collector-watchdog "cd $(pwd) && python -m ops.collector_watchdog"
```

**B. launchd (부팅 자동, 크래시 자동복구)** — `com.seokminal.watchdog.plist`를
`~/Library/LaunchAgents/`에 복사 후 경로/파이썬 수정:
```bash
cp ops/com.seokminal.watchdog.plist ~/Library/LaunchAgents/
# plist 안의 <경로> 2곳(WorkingDirectory, python 경로) 실제값으로 수정
launchctl load ~/Library/LaunchAgents/com.seokminal.watchdog.plist
launchctl list | grep seokminal          # 로드 확인
```

## 2. 개발 프로세스 방치 감시 (`dev_process_watchdog.py`)

`npm test`는 `vitest run`(1회성)이지만, 터미널에서 인자 없이 `vitest`를 직접 치면
watch 모드라 안 닫고 자리를 뜨면 CPU 100%로 몇 시간~며칠 방치될 수 있다(발열 사건
실사례, 2026-07-30). 5분마다 ps 스캔해서 30분 넘게 살아있는 vitest worker 프로세스만
SIGTERM — vitest 패턴에만 반응하므로 uvicorn/수집기/next dev 같은 상시 프로세스는
안전.

```bash
tmux new-session -d -s dev-process-watchdog "cd $(pwd) && python -m ops.dev_process_watchdog"
```

## 3. 의존성 락파일 (재현성)

컨테이너/맥 환경 드리프트(nautilus 버전 등)로 스위트가 깨지는 걸 막으려면 맥에서:
```bash
pip freeze > requirements.lock          # 현재 동작하는 정확한 버전 스냅샷
```
커밋해두면 새 환경에서 `pip install -r requirements.lock`으로 동일 재현. (컨테이너에서
생성하면 맥과 다른 버전이라 의미없음 — **맥에서** 떠야 함.)

## 4. 집행 안전 (참고)

`execution/broker.py`는 기본 페이퍼(dry-run). `make_broker(mode="live")`는 등록된 실어댑터가
없으면 거부하므로 실수로 실주문이 나갈 경로가 없다. 실집행은 엣지 확정 후 별도 태스크.
