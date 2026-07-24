"""`python -m jarvis.autonomous_research_os <cmd>` — 자율 연구 OS CLI. **관찰·분석·기록 전용.**

  init      [--name]                       OS 초기화(INITIALIZED) [--commit]
  connect   --os                           하위 계층 연결(→CONNECTED) [--commit]
  observe   --os --layer [--note]          연구 상태 관찰·에피소드(→OBSERVING) [--commit]
  view      --os [--kind]                  지식 뷰 집계(is_binding=False) [--commit]
  snapshot  --os                           시스템 스냅샷(→ANALYZING) [--commit]
  report    --os / archive --os            운영 리포트(→REPORTING) / 보관 [--commit]
  layers  / list / verify / replay --os / summary

거래·주문·자본 배분·전략 배포·모델 승격·권한 변경 절대 없음. OS ≠ EXECUTION · CONNECT ≠ CONTROL · SNAPSHOT ≠ DEPLOYMENT.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _eng():
    from jarvis.autonomous_research_os.engine import AutonomousResearchOSEngine
    return AutonomousResearchOSEngine()


def _cmd_init(a) -> int:
    _p({"committed": a.commit,
        "os": _eng().initialize_os(a.name, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_connect(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().connect(a.os, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_observe(a) -> int:
    _p({"committed": a.commit,
        "episode": _eng().collect_research_state(a.os, a.layer, a.note or "", _now(),
                                                commit=a.commit).to_dict()})
    return 0


def _cmd_view(a) -> int:
    _p({"committed": a.commit,
        "view": _eng().build_research_view(a.os, a.kind, _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_snapshot(a) -> int:
    _p({"committed": a.commit,
        "snapshot": _eng().create_snapshot(a.os, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_os_report(a.os, "OS", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_archive(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().archive_os(a.os, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_layers(a) -> int:
    _p({"layer_counts": _eng().layer_counts()})
    return 0


def _cmd_list(a) -> int:
    eng = _eng()
    _p({"os": [{"os_id": o, "state": eng.current_state(o)} for o in eng.list_os()]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.autonomous_research_os.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.autonomous_research_os.verify import replay
    _p(replay(_eng(), a.os, _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.autonomous_research_os")
    sub = ap.add_subparsers(dest="cmd", required=True)

    it = sub.add_parser("init")
    it.add_argument("--name", default="research-os")
    it.add_argument("--commit", action="store_true")

    cn = sub.add_parser("connect")
    cn.add_argument("--os", required=True)
    cn.add_argument("--commit", action="store_true")

    ob = sub.add_parser("observe")
    ob.add_argument("--os", required=True)
    ob.add_argument("--layer", required=True)
    ob.add_argument("--note", default="")
    ob.add_argument("--commit", action="store_true")

    vw = sub.add_parser("view")
    vw.add_argument("--os", required=True)
    vw.add_argument("--kind", default="LAYER_COUNTS")
    vw.add_argument("--commit", action="store_true")

    sn = sub.add_parser("snapshot")
    sn.add_argument("--os", required=True)
    sn.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--os", required=True)
    rp.add_argument("--commit", action="store_true")

    ar = sub.add_parser("archive")
    ar.add_argument("--os", required=True)
    ar.add_argument("--commit", action="store_true")

    rpl = sub.add_parser("replay")
    rpl.add_argument("--os", required=True)

    sub.add_parser("layers")
    sub.add_parser("list")
    sub.add_parser("verify")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"init": _cmd_init, "connect": _cmd_connect, "observe": _cmd_observe, "view": _cmd_view,
            "snapshot": _cmd_snapshot, "report": _cmd_report, "archive": _cmd_archive,
            "layers": _cmd_layers, "list": _cmd_list, "verify": _cmd_verify, "replay": _cmd_replay,
            "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
