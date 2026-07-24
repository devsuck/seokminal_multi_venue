"""`python -m jarvis.research_navigation <cmd>` — 통합 네비게이션 CLI. **읽기전용, 결정 권한 없음.**

  tree                     네비게이션 트리(Home → 섹션 → 항목 → 모듈)
  sections                 섹션·항목별 모듈 배치
  duplicates               중복·혼란 페이지 후보
  panels                   기존 대시보드 패널 → 섹션 매핑
  coverage                 배치 커버리지
  summary                  매니페스트 요약(digest)
  render [--out DIR]       docs/navigation/ 에 문서·매니페스트 렌더

기존 기능 보존, 새 대시보드 없음. 거래·집행·승인 없음.
"""
from __future__ import annotations

import argparse
import json
import os


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _eng():
    from jarvis.research_navigation.engine import NavigationEngine
    return NavigationEngine()


def _cmd_tree(a) -> int:
    _p(_eng().tree())
    return 0


def _cmd_sections(a) -> int:
    _p([s.to_dict() for s in _eng().nav_sections()])
    return 0


def _cmd_duplicates(a) -> int:
    _p([d.to_dict() for d in _eng().duplicate_pages()])
    return 0


def _cmd_panels(a) -> int:
    _p(_eng().panel_mapping())
    return 0


def _cmd_coverage(a) -> int:
    eng = _eng()
    _p({"coverage": eng.coverage(), "unplaced": eng.unplaced()})
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary())
    return 0


def _cmd_render(a) -> int:
    out = a.out or os.path.join(os.getcwd(), "docs", "navigation")
    written = _eng().render_docs(out)
    _p({"out_dir": out, "written": written, "count": len(written)})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_navigation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("tree", "sections", "duplicates", "panels", "coverage", "summary"):
        sub.add_parser(name)
    rp = sub.add_parser("render")
    rp.add_argument("--out", default="")
    args = ap.parse_args(argv)
    disp = {"tree": _cmd_tree, "sections": _cmd_sections, "duplicates": _cmd_duplicates,
            "panels": _cmd_panels, "coverage": _cmd_coverage, "summary": _cmd_summary,
            "render": _cmd_render}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
