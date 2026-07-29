"""`python -m jarvis.research_event_bus <cmd>` — 내부 연구 이벤트 버스 CLI. **통신 인프라 전용.**

  type       --name [--desc --category]                       이벤트 유형 등록 [--commit]
  source     --layer --source-id [--note]                     인가 소스 등록 [--commit]
  stream     --name [--type-filter --desc]                    스트림 정의 [--commit]
  publish    --type --layer --source-id [--payload --parent]  이벤트 발행(→PUBLISHED) [--commit]
  subscriber --name --type [--source-filter]                  구독자 등록 [--commit]
  route      --type --subscriber [--condition]                라우팅 규칙 [--commit]
  deliver    --event --subscriber                             전달 추적(→ROUTED) [--commit]
  consume    --event --subscriber                             소비(→CONSUMED) [--commit]
  archive    --event                                          아카이브(→ARCHIVED) [--commit]
  snapshot   [--scope] / report [--scope] / events [--type] / verify / replay / summary

실제 실행·배포·전략/모델 수정·자본 배분·권한/설정 변경·자동 승인 없음 — 이벤트 통신·기록만.
EVENT ≠ EXECUTION · PUBLISH ≠ DEPLOY · ROUTE ≠ APPROVAL.
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
    from jarvis.research_event_bus.engine import ResearchEventBusEngine
    return ResearchEventBusEngine()


def _cmd_type(a) -> int:
    _p({"committed": a.commit,
        "event_type": _eng().register_event_type(a.name, a.desc or "", a.category or "", _now(),
                                                  commit=a.commit).to_dict()})
    return 0


def _cmd_source(a) -> int:
    _p({"committed": a.commit,
        "source": _eng().register_source(a.layer, a.source_id, a.note or "", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_stream(a) -> int:
    _p({"committed": a.commit,
        "stream": _eng().build_event_stream(a.name, a.type_filter or "", a.desc or "", _now(),
                                            commit=a.commit).to_dict()})
    return 0


def _cmd_publish(a) -> int:
    payload = json.loads(a.payload) if a.payload else None
    _p({"committed": a.commit,
        "event": _eng().publish_event(a.type, a.layer, a.source_id, payload, a.parent or "", None,
                                      _now(), commit=a.commit).to_dict(),
        "note": "PUBLISH ≠ DEPLOY"})
    return 0


def _cmd_subscriber(a) -> int:
    _p({"committed": a.commit,
        "subscriber": _eng().register_subscriber(a.name, a.type, a.source_filter or "", _now(),
                                                 commit=a.commit).to_dict()})
    return 0


def _cmd_route(a) -> int:
    _p({"committed": a.commit,
        "route": _eng().register_route(a.type, a.subscriber, a.condition or "", _now(),
                                       commit=a.commit).to_dict(),
        "note": "ROUTE ≠ APPROVAL"})
    return 0


def _cmd_deliver(a) -> int:
    _p({"committed": a.commit,
        "delivery": _eng().track_delivery(a.event, a.subscriber, "", _now(),
                                          commit=a.commit).to_dict()})
    return 0


def _cmd_consume(a) -> int:
    _p({"committed": a.commit,
        "consumption": _eng().consume_event(a.event, a.subscriber, "", _now(),
                                            commit=a.commit).to_dict()})
    return 0


def _cmd_archive(a) -> int:
    _p({"committed": a.commit,
        "event": _eng().archive_event(a.event, _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_snapshot(a) -> int:
    _p({"committed": a.commit,
        "snapshot": _eng().snapshot_events(a.scope or "ALL", _now(), commit=a.commit).to_dict()})
    return 0


def _cmd_report(a) -> int:
    _p({"committed": a.commit,
        "report": _eng().generate_report(a.scope or "ALL", _now(), commit=a.commit).to_dict(),
        "note": "is_binding=False"})
    return 0


def _cmd_events(a) -> int:
    eng = _eng()
    evs = eng.list_events(a.type or "")
    _p({"events": [{"event_id": e, "state": eng.current_state(e)} for e in evs]})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_event_bus.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_event_bus.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_event_bus")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ty = sub.add_parser("type")
    ty.add_argument("--name", required=True)
    ty.add_argument("--desc", default="")
    ty.add_argument("--category", default="")
    ty.add_argument("--commit", action="store_true")

    so = sub.add_parser("source")
    so.add_argument("--layer", required=True)
    so.add_argument("--source-id", dest="source_id", required=True)
    so.add_argument("--note", default="")
    so.add_argument("--commit", action="store_true")

    st = sub.add_parser("stream")
    st.add_argument("--name", required=True)
    st.add_argument("--type-filter", dest="type_filter", default="")
    st.add_argument("--desc", default="")
    st.add_argument("--commit", action="store_true")

    pb = sub.add_parser("publish")
    pb.add_argument("--type", required=True)
    pb.add_argument("--layer", required=True)
    pb.add_argument("--source-id", dest="source_id", required=True)
    pb.add_argument("--payload", default="")
    pb.add_argument("--parent", default="")
    pb.add_argument("--commit", action="store_true")

    su = sub.add_parser("subscriber")
    su.add_argument("--name", required=True)
    su.add_argument("--type", required=True)
    su.add_argument("--source-filter", dest="source_filter", default="")
    su.add_argument("--commit", action="store_true")

    ro = sub.add_parser("route")
    ro.add_argument("--type", required=True)
    ro.add_argument("--subscriber", required=True)
    ro.add_argument("--condition", default="")
    ro.add_argument("--commit", action="store_true")

    dl = sub.add_parser("deliver")
    dl.add_argument("--event", required=True)
    dl.add_argument("--subscriber", required=True)
    dl.add_argument("--commit", action="store_true")

    co = sub.add_parser("consume")
    co.add_argument("--event", required=True)
    co.add_argument("--subscriber", required=True)
    co.add_argument("--commit", action="store_true")

    ar = sub.add_parser("archive")
    ar.add_argument("--event", required=True)
    ar.add_argument("--commit", action="store_true")

    sn = sub.add_parser("snapshot")
    sn.add_argument("--scope", default="ALL")
    sn.add_argument("--commit", action="store_true")

    rp = sub.add_parser("report")
    rp.add_argument("--scope", default="ALL")
    rp.add_argument("--commit", action="store_true")

    ev = sub.add_parser("events")
    ev.add_argument("--type", default="")

    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")

    args = ap.parse_args(argv)
    disp = {"type": _cmd_type, "source": _cmd_source, "stream": _cmd_stream, "publish": _cmd_publish,
            "subscriber": _cmd_subscriber, "route": _cmd_route, "deliver": _cmd_deliver,
            "consume": _cmd_consume, "archive": _cmd_archive, "snapshot": _cmd_snapshot,
            "report": _cmd_report, "events": _cmd_events, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
