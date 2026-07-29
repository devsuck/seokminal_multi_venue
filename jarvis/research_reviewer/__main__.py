"""`python -m jarvis.research_reviewer <cmd>` — 연구 품질 AI 리뷰어 CLI. **평가·기록 전용.**

  review   --subject --reviewer --scores STATISTICAL=0.8,RISK=0.6,...  리뷰 [--commit]
  critique --review --dim --severity --desc          비평 [--commit]
  evidence --critique --type --ref [--detail]        증거 [--commit]
  report   --review                                  리뷰어 리포트 [--commit]
  verdict  --review                                  평결 조회
  reviews [--verdict] / verify / replay / summary

실제 자동 결정·승인·삭제 없음 — 평가·권고만. 연구 거부 ≠ 전략 삭제.
REVIEW ≠ DECISION · REJECT_RESEARCH ≠ DELETE_STRATEGY · VERDICT ≠ ACTION.
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
    from jarvis.research_reviewer.engine import ResearchReviewerEngine
    return ResearchReviewerEngine()


def _parse_scores(s: str) -> dict:
    out = {}
    for tok in (s or "").split(","):
        tok = tok.strip()
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k.strip().upper()] = float(v)
    return out


def _cmd_review(a) -> int:
    r = _eng().create_review(a.subject, a.reviewer, _parse_scores(a.scores), a.subject_type or "RESEARCH",
                             _now(), commit=a.commit)
    _p({"committed": a.commit, "review": r.to_dict(), "note": "REVIEW ≠ DECISION"})
    return 0


def _cmd_critique(a) -> int:
    c = _eng().add_critique(a.review, a.dim, a.severity, a.desc or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "critique": c.to_dict()})
    return 0


def _cmd_evidence(a) -> int:
    ev = _eng().add_evidence(a.critique, a.type, a.ref, a.detail or "", _now(), commit=a.commit)
    _p({"committed": a.commit, "evidence": ev.to_dict()})
    return 0


def _cmd_report(a) -> int:
    r = _eng().generate_report(a.review, _now(), commit=a.commit)
    _p({"committed": a.commit, "report": r.to_dict(), "note": "is_decision=False"})
    return 0


def _cmd_verdict(a) -> int:
    _p({"review": a.review, "verdict": _eng().get_verdict(a.review), "note": "VERDICT ≠ ACTION"})
    return 0


def _cmd_reviews(a) -> int:
    _p({"reviews": _eng().list_reviews(a.verdict or "")})
    return 0


def _cmd_verify(a) -> int:
    from jarvis.research_reviewer.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.research_reviewer.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def _cmd_summary(a) -> int:
    _p(_eng().summary(_now()).to_dict())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.research_reviewer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rv = sub.add_parser("review")
    rv.add_argument("--subject", required=True)
    rv.add_argument("--reviewer", required=True)
    rv.add_argument("--scores", required=True)
    rv.add_argument("--subject-type", default="RESEARCH")
    rv.add_argument("--commit", action="store_true")
    cr = sub.add_parser("critique")
    cr.add_argument("--review", required=True)
    cr.add_argument("--dim", required=True)
    cr.add_argument("--severity", required=True)
    cr.add_argument("--desc", default="")
    cr.add_argument("--commit", action="store_true")
    ev = sub.add_parser("evidence")
    ev.add_argument("--critique", required=True)
    ev.add_argument("--type", required=True)
    ev.add_argument("--ref", required=True)
    ev.add_argument("--detail", default="")
    ev.add_argument("--commit", action="store_true")
    rp = sub.add_parser("report")
    rp.add_argument("--review", required=True)
    rp.add_argument("--commit", action="store_true")
    vd = sub.add_parser("verdict")
    vd.add_argument("--review", required=True)
    re = sub.add_parser("reviews")
    re.add_argument("--verdict", default="")
    sub.add_parser("verify")
    sub.add_parser("replay")
    sub.add_parser("summary")
    args = ap.parse_args(argv)
    disp = {"review": _cmd_review, "critique": _cmd_critique, "evidence": _cmd_evidence,
            "report": _cmd_report, "verdict": _cmd_verdict, "reviews": _cmd_reviews,
            "verify": _cmd_verify, "replay": _cmd_replay, "summary": _cmd_summary}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
