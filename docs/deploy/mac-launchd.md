# 맥 상시구동 자동화 (launchd) — 수집기 워치독 + (선택) API

> 목적: tmux 수동 babysitting 종결. 잠자기/크래시/재부팅 후 죽은 수집기를 자동 재생성.
> **비침습**: HUD의 tmux 기반 생존체크/재시작을 그대로 유지 — 세션이 죽었을 때만 되살림.

## 왜 이 설계인가
HUD(`/lab/status`, 재시작 버튼)는 tmux 세션 존재로 수집기 생존을 판단한다. 그래서 수집기를
완전 launchd 프로세스로 바꾸면 HUD가 다 "죽음"으로 오판한다. 대신 **launchd가 60초마다
`ensure_collectors.sh`를 돌려 죽은 tmux 세션만 재생성**한다 — HUD는 그대로, 자동 부활만 추가.

## 1. 수동 검증 먼저 (launchd 걸기 전)
```bash
cd <맥의 seokminal-multi-venue>
SEOKMINAL_PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
  bash scripts/deploy/ensure_collectors.sh
tmux ls          # 수집기 세션들 떠야 함
```
- 어떤 수집기를 상시 유지할지는 `ensure_collectors.sh`의 `ENSURE=(...)` 목록에서 편집
  (안 돌릴 것은 줄 삭제/주석). 이게 desired state.

## 2. launchd 등록 (수집기 워치독)
```bash
mkdir -p logs
cp scripts/deploy/launchd/com.seokminal.collectors.plist ~/Library/LaunchAgents/
# 편집: <REPO> → 맥의 절대경로, <PYTHON> → 실제 파이썬 경로 (두 군데씩)
launchctl load ~/Library/LaunchAgents/com.seokminal.collectors.plist
launchctl list | grep seokminal          # 등록 확인
tail -f logs/collectors-watchdog.log      # 매분 로그
```
확인: 수집기 하나를 `tmux kill-session -t hl-orderflow-tick`로 죽여보고, 1분 내 로그에
"재생성: hl-orderflow-tick" 뜨고 `tmux ls`에 다시 나타나면 정상.

해제: `launchctl unload ~/Library/LaunchAgents/com.seokminal.collectors.plist`

## 3. (선택) uvicorn API도 launchd로
재부팅/크래시에도 API 자동 기동을 원하면 `com.seokminal.api.plist`도 같은 방식으로.
KeepAlive라 죽으면 재기동. 단 재기동 시 WS 끊김. ProgramArguments를 실제 실행 커맨드로 맞출 것.
```bash
cp scripts/deploy/launchd/com.seokminal.api.plist ~/Library/LaunchAgents/
# <REPO>/<PYTHON> 치환, ProgramArguments 확인 후
launchctl load ~/Library/LaunchAgents/com.seokminal.api.plist
```

## 주의
- LaunchAgent는 로그인 세션에서 돎(tmux가 유저 tmux 서버를 쓰므로 정상). 로그아웃 상태 상시구동이
  필요하면 LaunchDaemon(root)로 승격해야 하는데, tmux 유저 컨텍스트 이슈가 있어 권장 안 함 —
  맥은 로그인 유지 전제.
- 데이터/상태(`data/`, `research/data/`)는 gitignore라 이 스크립트가 안 건드림. 수집기가 알아서 append.
