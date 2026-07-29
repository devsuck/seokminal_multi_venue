"""tmux 터미널(ttyd) + autopilot 인수인계 종료(shutdown) + API 재시작(update) 라우트.
alpaca_account/agents와 무관하게 완전히 독립적 — 공유 상태 없음."""
from __future__ import annotations

import os as _os
import re
import shutil
import signal as _signal
import socket
import subprocess
import threading as _threading

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/alpaca", tags=["alpaca"])

TTYD_PORT = 7681
TMUX_SESSION = "autopilot"


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _tmux_session_exists() -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True,
    )
    return result.returncode == 0


@router.post("/terminal/start")
def start_terminal() -> dict:
    """Start tmux+claude session and ttyd if not already running."""
    if shutil.which("tmux") is None:
        raise HTTPException(status_code=503, detail="tmux not installed — run: brew install tmux")
    if shutil.which("ttyd") is None:
        raise HTTPException(status_code=503, detail="ttyd not installed — run: brew install ttyd")
    if shutil.which("claude") is None:
        raise HTTPException(status_code=503, detail="claude not found in PATH")

    agent_loop = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        "..", "..", "autopilot", "agent_loop.sh",
    )
    agent_loop = _os.path.normpath(agent_loop)

    if not _tmux_session_exists():
        subprocess.Popen(
            ["tmux", "new-session", "-d", "-s", TMUX_SESSION, agent_loop],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    if not _port_in_use(TTYD_PORT):
        subprocess.Popen(
            ["ttyd", "-p", str(TTYD_PORT), "-W", "tmux", "attach-session", "-t", TMUX_SESSION],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    return {"status": "ok", "tmux_session": TMUX_SESSION, "ttyd_port": TTYD_PORT}


@router.get("/terminal/status")
def terminal_status() -> dict:
    return {
        "ttyd_running": _port_in_use(TTYD_PORT),
        "tmux_session": _tmux_session_exists(),
    }


# ── tmux pane capture (used by shutdown status) ───────────────────────────────

_ANSI_RE = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;]*[ -/]*[@-~])')


def _tmux_capture(n: int = 500) -> list[str]:
    try:
        if not _tmux_session_exists():
            return []
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", TMUX_SESSION, "-p", "-S", f"-{n}"],
            capture_output=True, text=True, timeout=3,
        )
        raw = _ANSI_RE.sub("", result.stdout)
        return [l.rstrip() for l in raw.split("\n") if l.strip()]
    except Exception:
        return []


# ── Shutdown ──────────────────────────────────────────────────────────────────

AUTOPILOT_DIR = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "..", "..", "autopilot"
))
KILL_FILE = _os.path.join(AUTOPILOT_DIR, "KILL")

HANDOFF_PROMPT = """
지금 즉시 현재 작업을 중단하고 다음 인수인계 작업을 수행해.

1. 현재 포트폴리오 상태 확인: bash tools/portfolio.sh
2. 오늘 분석/매매 요약을 memory.py에 기록:
   python3 tools/memory.py reflect '종료 전 인수인계: [현재 상태 요약, 보유 종목, 다음 사이클 주목 사항]'
3. 인수인계 완료 후 반드시 마지막 줄에 다음 텍스트만 출력:
   HANDOFF_COMPLETE

지금 바로 시작해.
"""


@router.post("/shutdown/initiate")
def shutdown_initiate() -> dict:
    """Stop agent loop, run handoff, signal ready."""
    with open(KILL_FILE, "w") as f:
        f.write("shutdown\n")

    if not _tmux_session_exists():
        return {"status": "initiated"}

    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "C-c", ""], capture_output=True)
    import time; time.sleep(1)
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "C-c", ""], capture_output=True)
    import time; time.sleep(1)

    handoff_cmd = (
        f"cd {AUTOPILOT_DIR} && "
        f"claude --print \"{HANDOFF_PROMPT.strip()}\" 2>&1; "
        f"echo HANDOFF_COMPLETE"
    )
    subprocess.run(
        ["tmux", "send-keys", "-t", TMUX_SESSION, handoff_cmd, "Enter"],
        capture_output=True,
    )
    return {"status": "initiated"}


@router.get("/shutdown/status")
def shutdown_status() -> dict:
    """Check if handoff is complete."""
    if not _tmux_session_exists():
        return {"done": True, "recent_lines": ["(autopilot 세션 없음 — 인수인계 생략)"]}
    lines = _tmux_capture(200)
    content = "\n".join(lines)
    done = "HANDOFF_COMPLETE" in content
    recent = lines[-20:] if len(lines) > 20 else lines
    return {"done": done, "recent_lines": recent}


def _kill_all() -> None:
    import time
    time.sleep(2)
    subprocess.run(["tmux", "kill-server"], capture_output=True)
    subprocess.run(["bash", "-c", "lsof -ti:7681 | xargs kill -9 2>/dev/null; true"],
                   shell=False, capture_output=True)
    subprocess.run(["bash", "-c", "lsof -ti:3000 | xargs kill -9 2>/dev/null; true"],
                   shell=False, capture_output=True)
    time.sleep(0.5)
    _os.kill(_os.getpid(), _signal.SIGTERM)


@router.post("/shutdown/execute")
def shutdown_execute() -> dict:
    """Kill all servers (2s delay to allow response to reach client)."""
    try:
        _os.remove(KILL_FILE)
    except FileNotFoundError:
        pass
    _threading.Thread(target=_kill_all, daemon=True).start()
    return {"status": "shutting_down"}


# ── API 재시작 (코드 업데이트 반영용) ───────────────────────────────────────────
# uvicorn을 --reload 없이 상시가동하기로 하면서(발열 원인 — reload가 감시+워커 프로세스를
# 따로 띄워 CPU/메모리 계속 먹음, 2026-07-26), 코드 수정 반영은 이 버튼으로 수동 트리거.
# scripts/restart_api.sh를 detached로 실행 — 스크립트가 포트 기준으로 자기 부모(=지금 이
# 요청을 처리 중인 프로세스 자신)를 죽이고 새로 띄우므로, 부모가 먼저 죽어도 계속 진행됨.

MULTI_VENUE_DIR = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
RESTART_SCRIPT = _os.path.join(MULTI_VENUE_DIR, "scripts", "restart_api.sh")


@router.post("/update/execute")
def update_execute() -> dict:
    """코드 반영 위해 uvicorn 재시작. restart_api.sh가 킬+재기동 다 처리."""
    subprocess.Popen(
        ["bash", RESTART_SCRIPT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,  # 부모(uvicorn) 프로세스 그룹과 분리 — 재시작 도중 죽어도 안 끊김
    )
    return {"status": "restarting"}
