"""데이터 pull 큐 — 세션이 babysit하던 장시간 pull을 service가 관리.

큐 파일(jsonl append) + 한 번에 한 job만 배경 스레드 실행(전부 재개 지원 pull이라
중단·재시작 안전). 완료 시 follow_up 커맨드 기록(자동 실행은 사전등록 러너만).

job 스키마: {id, kind, params, status(pending/running/done/error), enqueued, started,
             finished, result, follow_up}
kind 종류:
  ksd_lending   — params.families([...]) 유니버스 대차 히스토리 pull
  dart_events   — params.family DART 이벤트 pull(EVENT_DEFS/FAMILIES 필요)
  krx_range     — params.market/start/end 스냅샷 pull

CLI: PYTHONPATH=. python3 -m research.data.pull_queue enqueue ksd_lending
     PYTHONPATH=. python3 -m research.data.pull_queue list
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

from jarvis.config import state_path

_QUEUE = "pull_queue.jsonl"
_running: dict = {"job": None, "thread": None}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path() -> str:
    return state_path(_QUEUE)


def _load() -> list[dict]:
    if not os.path.exists(_path()):
        return []
    return [json.loads(ln) for ln in open(_path()) if ln.strip()]


def _save(jobs: list[dict]) -> None:
    with open(_path(), "w") as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")


def enqueue(kind: str, params: dict | None = None, follow_up: str | None = None) -> dict:
    job = {"id": uuid.uuid4().hex[:8], "kind": kind, "params": params or {},
           "status": "pending", "enqueued": _now(), "started": None,
           "finished": None, "result": None, "follow_up": follow_up}
    jobs = _load()
    jobs.append(job)
    _save(jobs)
    return job


def _run_job(job: dict) -> dict:
    """job 실행 — 전부 재개 지원 pull이라 재실행 안전."""
    kind, p = job["kind"], job["params"]
    if kind == "ksd_lending":
        from research.data.ksd_lending import event_universe_codes, pull_universe
        codes = event_universe_codes(p.get("families", ["buyback", "treasury_disposal"]))
        return pull_universe(codes, log=lambda *_: None)
    if kind == "dart_events":
        from research.data.kr_dart_events import EVENT_DEFS, pull_events, save_events
        from research.scanner.families import FAMILIES
        fam_id = p["family"]
        fam = FAMILIES[fam_id]
        EVENT_DEFS[fam_id] = {"include": fam["keywords"], "exclude": fam["exclude"],
                              "bias": fam["direction"], "pblntf_ty": fam.get("pblntf_ty", "B")}
        rows = pull_events(fam_id, years=float(p.get("years", 6.5)))
        save_events(fam_id, rows)
        return {"events": len(rows)}
    if kind == "krx_range":
        from research.data.krx_api import pull_range
        return pull_range(p["market"], p["start"], p["end"], log=lambda *_: None) or {"ok": True}
    raise ValueError(f"unknown kind: {kind}")


def _worker(job_id: str) -> None:
    jobs = _load()
    job = next((j for j in jobs if j["id"] == job_id), None)
    if job is None:
        return
    try:
        result = _run_job(job)
        job["status"], job["result"] = "done", result
    except Exception as exc:  # noqa: BLE001
        job["status"], job["result"] = "error", {"error": str(exc)[:200]}
    job["finished"] = _now()
    # 다른 스레드가 파일 바꿨을 수 있으니 재로드 후 해당 job만 교체
    fresh = _load()
    _save([job if j["id"] == job_id else j for j in fresh])
    _running["job"] = None


def tick() -> dict | None:
    """service 틱에서 호출 — 실행 중 없고 pending 있으면 하나 시작. 반환=시작한 job."""
    if _running["job"] is not None and _running["thread"] and _running["thread"].is_alive():
        return None
    _running["job"] = None
    jobs = _load()
    job = next((j for j in jobs if j["status"] == "pending"), None)
    if job is None:
        return None
    job["status"], job["started"] = "running", _now()
    _save(jobs)
    _running["job"] = job["id"]
    t = threading.Thread(target=_worker, args=(job["id"],), daemon=True)
    _running["thread"] = t
    t.start()
    return job


def status() -> dict:
    jobs = _load()
    return {"pending": sum(1 for j in jobs if j["status"] == "pending"),
            "running": next((j["id"] for j in jobs if j["status"] == "running"), None),
            "recent": jobs[-5:]}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "enqueue":
        kind = sys.argv[2]
        params = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        print(json.dumps(enqueue(kind, params), ensure_ascii=False))
    elif cmd == "run-once":
        j = tick()
        print(json.dumps(j, ensure_ascii=False) if j else "no pending")
        while _running["thread"] and _running["thread"].is_alive():
            time.sleep(5)
        print(json.dumps(status()["recent"][-1], ensure_ascii=False))
    else:
        print(json.dumps(status(), ensure_ascii=False, indent=1))
