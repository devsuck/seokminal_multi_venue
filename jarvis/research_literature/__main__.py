"""`python -m jarvis.research_literature <cmd>` — 외부 문헌 인텔리전스 CLI. **읽기·기록 전용.**

  paper    --title [--doi --year --venue]      논문 등록 [--commit]
  concepts --paper --items name:TYPE,name2     개념 추출 [--commit]
  ideas    --paper --items name:desc           전략 아이디어 추출(정보용) [--commit]
  cite     --citing --cited                    인용 추가 [--commit]
  compare  --a --b                             논문 비교 [--commit]
  graph                                        인용 그래프
  duplicates                                   중복 논문 후보
  integrity                                    지식 무결성
  papers / verify / replay / summary

실제 자동 전략 생성·배포·실행 없음 — 문헌 연결·기록만.
LITERATURE ≠ STRATEGY · IDEA ≠ DEPLOYMENT · CITATION ≠ EXECUTION.
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
    from jarvis.research_literature.engine import ResearchLiteratureEngine
    return ResearchLiteratureEngine()


def _cmd_paper(a) -> int:
    p = _eng().register_paper(a.title, (a.authors or "").split(";") if a.authors else [],
                              a.year or 0, a.venue or "", a.doi or "", a.url or "", _now(),
                              commit=a.commit)
    _p({"committed": a.commit, "paper": p.to_dict()})
    return 0


def _cmd_concepts(a) -> int:
    items = []
    for tok in (a.items or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if ":" in tok:
            name, ctype = tok.split(":", 1)
            items.append((name.strip(), ctype.strip(), ""))
        else:
            items.append((tok, "CONCEPT", ""))
    cs = _eng().extract_concepts(a.paper, items, _now(), commit=a.commit)
    _p({"committed": a.commit, "concepts": [c.to_dict() for c in cs]})
    return 0


def _cmd_ideas(a) -> int:
    ideas = []
    for tok in (a.items or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if ":" in tok:
            name, desc = tok.split(":", 1)
            ideas.append((name.strip(), desc.strip()))
        else:
            ideas.append((tok, ""))
    cs = _eng().extract_strategy_ideas(a.paper, ideas, _now(), commit=a.commit)
    _p({"committed": a.commit, "ideas": [c.to_dict() for c in cs], "note": "IDEA ≠ DEPLOYMENT"})
    return 0


def _cmd_cite(a) -> int:
    c = _eng().add_citation(a.citing, a.cited, _now(), commit=a.commit)
    _p({"committed": a.commit, "citation": c.to_dict()})
    return 0


def _cmd_compare(a) -> int:
    r = _eng().compare_papers(a.a, a.b, _now(), commit=a.commit)
    _p({"committed": a.commit, "comparison": r.to_dict()})
    return 0


def _cmd_graph(a) -> int:
    _p(_eng().build_citation_graph())
    return 0


def _cmd_duplicates(a) -> int:
    _p({"duplicates": _eng().detect_duplicate_papers()})
    return 0


def _cmd_integrity(a) -> int:
    res = _eng().knowledge_integrity()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_papers(a) -> int:
    _p({"papers": _eng().list_papers()})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_literature.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_literature.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_literature")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("paper")
    pa.add_argument("--title", required=True)
    pa.add_argument("--authors", default="")
    pa.add_argument("--year", type=int, default=0)
    pa.add_argument("--venue", default="")
    pa.add_argument("--doi", default="")
    pa.add_argument("--url", default="")
    pa.add_argument("--commit", action="store_true")
    co = sub.add_parser("concepts")
    co.add_argument("--paper", required=True)
    co.add_argument("--items", required=True)
    co.add_argument("--commit", action="store_true")
    id = sub.add_parser("ideas")
    id.add_argument("--paper", required=True)
    id.add_argument("--items", required=True)
    id.add_argument("--commit", action="store_true")
    ci = sub.add_parser("cite")
    ci.add_argument("--citing", required=True)
    ci.add_argument("--cited", required=True)
    ci.add_argument("--commit", action="store_true")
    cm = sub.add_parser("compare")
    cm.add_argument("--a", required=True)
    cm.add_argument("--b", required=True)
    cm.add_argument("--commit", action="store_true")
    sub.add_parser("graph")
    sub.add_parser("duplicates")
    sub.add_parser("integrity")
    sub.add_parser("papers")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"paper": _cmd_paper, "concepts": _cmd_concepts, "ideas": _cmd_ideas, "cite": _cmd_cite,
            "compare": _cmd_compare, "graph": _cmd_graph, "duplicates": _cmd_duplicates,
            "integrity": _cmd_integrity, "papers": _cmd_papers, "verify": _cmd_verify,
            "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
