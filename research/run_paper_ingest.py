"""논문→가설 자동생성 파이프라인 — 1회성 트리거 스크립트(cron 아님).

arXiv 신규논문 fetch → PDF 텍스트 추출 → LLM 스펙추출 → 자산커버리지 필터 →
LLM 코드생성 → 스모크체크 → research/hypotheses/papers/에 저장.
통과 못한 논문은 사유와 함께 research/data/paper_pipeline/rejected.jsonl에 기록.

사용: python -m research.run_paper_ingest
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from research.papers.arxiv_fetcher import (
    download_pdf_text, fetch_papers, filter_new_papers, load_cursor, load_cursor_ids, save_cursor,
)
from research.papers.codegen_signal import generate_signal_code
from research.papers.coverage_filter import rejection_reason
from research.papers.extract_spec import extract_spec
from research.papers.llm_cli import strip_code_fence
from research.papers.smoke_check import check as smoke_check

_HYPOTHESES_DIR = Path("research/hypotheses/papers")
_REJECTED_PATH = Path("research/data/paper_pipeline/rejected.jsonl")


def _log_rejected(arxiv_id: str, title: str, stage: str, reason: str) -> None:
    path = Path(_REJECTED_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({
            "arxiv_id": arxiv_id, "title": title, "stage": stage, "reason": reason,
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        }, ensure_ascii=False) + "\n")


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:40]


def process_paper(paper: dict) -> str:
    arxiv_id, title = paper["id"], paper["title"]

    try:
        text = download_pdf_text(paper["pdf_url"])
    except Exception as e:
        _log_rejected(arxiv_id, title, "pdf_download", str(e))
        return "pdf_error"

    try:
        spec = extract_spec(text)
    except Exception as e:
        _log_rejected(arxiv_id, title, "extract_spec", str(e))
        return "spec_error"

    reason = rejection_reason(spec)
    if reason is not None:
        _log_rejected(arxiv_id, title, "coverage_filter", reason)
        return "coverage_reject"

    try:
        code = strip_code_fence(generate_signal_code(spec))
    except Exception as e:
        _log_rejected(arxiv_id, title, "codegen", str(e))
        return "codegen_error"

    ok, smoke_reason = smoke_check(code)
    if not ok:
        _log_rejected(arxiv_id, title, "smoke_check", smoke_reason)
        return "smoke_reject"

    try:
        hyp_dir = Path(_HYPOTHESES_DIR)
        slug = _slug(title)
        module_path = hyp_dir / f"{arxiv_id.replace('.', '_')}_{slug}.py"
        if module_path.exists():
            _log_rejected(arxiv_id, title, "write", f"이미 존재(재처리 스킵): {module_path}")
            return "already_exists"
        hyp_dir.mkdir(parents=True, exist_ok=True)
        header = f'"""{title} (arXiv:{arxiv_id})\n{spec.get("signal_description", "")}\n"""\n'
        module_path.write_text(header + code)
    except Exception as e:
        _log_rejected(arxiv_id, title, "write", str(e))
        return "write_error"
    return "accepted"


def main(max_results: int = 50) -> dict:
    last_seen = load_cursor()
    seen_ids = load_cursor_ids()
    papers = fetch_papers(max_results=max_results)
    new_papers = filter_new_papers(papers, last_seen, seen_ids)

    counts: dict[str, int] = {}
    max_published = last_seen
    ids_at_max = set(seen_ids) if last_seen is not None else set()
    for paper in new_papers:
        status = process_paper(paper)
        counts[status] = counts.get(status, 0) + 1
        # pdf_error/write_error는 내용과 무관한 일시적 문제(arXiv PDF 생성 지연,
        # 디스크 이슈 등) — 커서를 이 논문 너머로 전진시키지 않아 다음 사이클에
        # 재시도되게 한다. 나머지 상태(accepted/spec_error/coverage_reject/
        # codegen_error/smoke_reject/already_exists)는 내용 기반 최종 판정이라 그대로 전진.
        if status in ("pdf_error", "write_error"):
            continue
        if max_published is None or paper["published"] > max_published:
            max_published = paper["published"]
            ids_at_max = {paper["id"]}
        elif paper["published"] == max_published:
            ids_at_max.add(paper["id"])

    if new_papers and max_published is not None:
        save_cursor(max_published, sorted(ids_at_max))

    return {"n_fetched": len(papers), "n_new": len(new_papers), "counts": counts}


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2, ensure_ascii=False))
