"""`python -m jarvis.integration_audit <cmd>` — 기존 아키텍처 통합 감사 CLI. **읽기전용.**

  inventory                모듈 인벤토리(카테고리/패턴)
  graph                    의존성 그래프 통계(상위 참조/고립)
  duplicates               중복·과중복 계열
  orphans                  미사용(고립) 모듈
  ui                       UI/페이지 인벤토리
  proposal                 통합 제안·로드맵
  summary                  감사 요약(digest 포함)
  render [--out DIR]       docs/integration_audit/ 에 문서 렌더

기존 원장·코드 변경 없음. 거래·집행·배포 없음.
"""
from __future__ import annotations

import argparse
import json
import os


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _eng():
    from jarvis.integration_audit.engine import IntegrationAuditEngine
    return IntegrationAuditEngine()


def _cmd_inventory(a) -> int:
    _p([i.to_dict() for i in _eng().inventory()])
    return 0


def _cmd_graph(a) -> int:
    _p(_eng().dependency_stats().to_dict())
    return 0


def _cmd_duplicates(a) -> int:
    _p([c.to_dict() for c in _eng().duplicate_clusters()])
    return 0


def _cmd_orphans(a) -> int:
    _p(_eng().orphans())
    return 0


def _cmd_ui(a) -> int:
    _p(_eng().ui_inventory())
    return 0


def _cmd_proposal(a) -> int:
    _p({"proposals": [p.to_dict() for p in _eng().integration_proposals()],
        "roadmap": _eng().roadmap()})
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary())
    return 0


def _cmd_render(a) -> int:
    out = a.out or os.path.join(os.getcwd(), "docs", "integration_audit")
    written = _eng().render_docs(out)
    _p({"out_dir": out, "written": written, "count": len(written)})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.integration_audit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("inventory", "graph", "duplicates", "orphans", "ui", "proposal", "summary"):
        sub.add_parser(name)
    rp = sub.add_parser("render")
    rp.add_argument("--out", default="")
    args = ap.parse_args(argv)
    disp = {"inventory": _cmd_inventory, "graph": _cmd_graph, "duplicates": _cmd_duplicates,
            "orphans": _cmd_orphans, "ui": _cmd_ui, "proposal": _cmd_proposal,
            "summary": _cmd_summary, "render": _cmd_render}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
