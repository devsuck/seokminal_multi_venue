# 논문 기반 알파 마이닝 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** arXiv q-fin 논문을 자동으로 읽어 `research/hypotheses/runner.py` 엔진이 검증 가능한 시그널 가설로 변환하고, 신규 격리 BH-FDR 풀로 통계 검증하는 1회성 트리거 파이프라인을 만든다.

**Architecture:** arXiv API 폴링(커서 dedup) → PDF 텍스트 추출 → LLM(Claude Code CLI 서브프로세스) 구조화 스펙 추출 → 자산커버리지 필터(equity_intraday만) → LLM 코드생성(few-shot) → 스모크체크(exec+fixture) → `research/hypotheses/papers/*.py` 저장 → 별도 검증러너가 `runner.run_universe()`에 태우고 결과 p-value를 신규 격리 BH-FDR 풀로 묶는다.

**Tech Stack:** Python 3.11+, `pdfplumber`(PDF→텍스트), `xml.etree.ElementTree`(arXiv Atom 파싱, 표준라이브러리), `claude` CLI 서브프로세스(LLM, 신규 API 키 불필요), 기존 `research/hypotheses/runner.py` + `research/validation/*` 재사용.

## Global Constraints

- v1 코드생성 대상 자산군은 `equity_intraday`만 (스펙 4절). 스펙 파싱 스키마는 자산군 무관하게 설계하되, 코드생성기는 `equity_intraday`일 때만 연결.
- LLM 호출은 `research/papers/llm_cli.py`의 `call_claude()`만 사용 — 신규 Anthropic API 키 발급 금지, `claude -p ... --output-format json --allowedTools ""` 서브프로세스로 기존 인증 재사용 (스펙 6절).
- SignalFn 시그니처 고정: `(ohlc, feat, aux, params) -> {"entry": bool[], "eligible": int[]}` — `research/hypotheses/runner.py`의 기존 컨벤션 그대로, 절대 변경 금지.
- 신규 격리 BH-FDR 풀 (alpha=0.1) — 논문가설 전용, 기존 수동가설 풀과 절대 안 섞음 (스펙 5, 7절).
- `run_paper_ingest.py`는 1회성 트리거 스크립트 — OS-level cron 자동화는 범위 밖 (스펙 7절).
- 신규 의존성은 `pdfplumber`만 추가 (스펙 8절).
- 거절된 논문은 사유와 함께 `research/data/paper_pipeline/rejected.jsonl`에 감사기록 (스펙 9절).
- 라이브 arXiv fetch / 라이브 Claude CLI 호출은 테스트에서 하지 않음 — 전부 mock (스펙 10절, 기존 컨벤션).
- CANDIDATE 판정 가설이라도 라이브 집행은 기존 Jarvis `arm_criteria`(최소 페이퍼기간) 게이트를 그대로 통과해야 함 — 이 파이프라인은 생성·검증까지만 (스펙 11절).
- Python 실행은 `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3` (프로젝트 컨벤션).

---

## File Structure

```
research/papers/__init__.py           ← 신규 패키지
research/papers/llm_cli.py            ← Claude CLI 서브프로세스 래퍼
research/papers/arxiv_fetcher.py      ← arXiv 폴링, 커서dedup, PDF→텍스트
research/papers/coverage_filter.py    ← 순수함수 자산커버리지 필터
research/papers/extract_spec.py       ← LLM: 논문텍스트→구조화스펙
research/papers/codegen_signal.py     ← LLM: 스펙→SignalFn 코드
research/papers/smoke_check.py        ← 생성코드 exec+fixture 체크
research/run_paper_ingest.py          ← 5단계 orchestration (1회성)
research/run_paper_hypothesis_validate.py  ← 신규 격리 BH-FDR 검증러너
research/hypotheses/papers/           ← 자동생성 가설 모듈 저장 위치(런타임 mkdir, 커밋 안 함)
research/data/paper_pipeline/         ← 커서파일+rejected.jsonl(런타임 mkdir)
pyproject.toml                        ← pdfplumber 의존성 추가 (Task 2에서)
tests/test_llm_cli.py
tests/test_arxiv_fetcher.py
tests/test_coverage_filter.py
tests/test_extract_spec.py
tests/test_smoke_check.py
tests/test_codegen_signal.py
tests/test_run_paper_ingest.py
tests/test_run_paper_hypothesis_validate.py
```

Task 순서는 의존성 순: llm_cli(기반) → arxiv_fetcher/coverage_filter(독립) → extract_spec/codegen_signal(llm_cli 의존) → smoke_check(독립) → run_paper_ingest(전부 의존) → run_paper_hypothesis_validate(runner.py만 의존, 독립적으로 병행 가능).

---

### Task 1: `research/papers/llm_cli.py` — Claude CLI 서브프로세스 래퍼

**Files:**
- Create: `research/papers/__init__.py` (빈 파일)
- Create: `research/papers/llm_cli.py`
- Test: `tests/test_llm_cli.py`

**Interfaces:**
- Consumes: 없음 (기반 모듈)
- Produces: `call_claude(prompt: str, timeout: int = 300) -> str` — 성공 시 CLI 응답의 `result` 필드(생성된 텍스트) 반환. `LLMCallError` 예외 — subprocess 실패/타임아웃/JSON파싱실패/result필드누락 시 발생. 이후 Task 4(`extract_spec.py`)와 Task 6(`codegen_signal.py`)가 이 두 심볼을 그대로 import해서 쓴다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_cli.py
import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from research.papers.llm_cli import call_claude, LLMCallError


def _cli_payload(result="Yo.", is_error=False):
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": is_error,
        "duration_ms": 2592, "result": result, "session_id": "abc",
        "total_cost_usd": 0.1057719,
    })


def test_call_claude_extracts_result_field():
    proc = MagicMock(stdout=_cli_payload(result="hello world"), returncode=0)
    with patch("subprocess.run", return_value=proc) as mock_run:
        out = call_claude("say hi")
    assert out == "hello world"
    args, kwargs = mock_run.call_args
    assert args[0] == ["claude", "-p", "say hi", "--output-format", "json", "--allowedTools", ""]
    assert kwargs["timeout"] == 300


def test_call_claude_custom_timeout_passed_through():
    proc = MagicMock(stdout=_cli_payload(), returncode=0)
    with patch("subprocess.run", return_value=proc) as mock_run:
        call_claude("say hi", timeout=60)
    assert mock_run.call_args.kwargs["timeout"] == 60


def test_call_claude_raises_on_is_error_true():
    proc = MagicMock(stdout=_cli_payload(is_error=True), returncode=0)
    with patch("subprocess.run", return_value=proc):
        with pytest.raises(LLMCallError):
            call_claude("say hi")


def test_call_claude_raises_on_malformed_json():
    proc = MagicMock(stdout="not json{{{", returncode=0)
    with patch("subprocess.run", return_value=proc):
        with pytest.raises(LLMCallError):
            call_claude("say hi")


def test_call_claude_raises_on_missing_result_field():
    proc = MagicMock(stdout=json.dumps({"type": "result", "is_error": False}), returncode=0)
    with patch("subprocess.run", return_value=proc):
        with pytest.raises(LLMCallError):
            call_claude("say hi")


def test_call_claude_raises_on_subprocess_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=300)):
        with pytest.raises(LLMCallError):
            call_claude("say hi")


def test_call_claude_raises_on_nonzero_exit():
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "claude")):
        with pytest.raises(LLMCallError):
            call_claude("say hi")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_llm_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.papers'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/papers/__init__.py
```

```python
# research/papers/llm_cli.py
"""Claude Code CLI 헤드리스 서브프로세스 호출 — 신규 API 키 불필요.

extract_spec.py/codegen_signal.py 전용 LLM 호출 경로. 툴 접근 없이 순수
텍스트생성만 하도록 --allowedTools ""로 제한(파일쓰기는 호출측이 직접 함)."""
from __future__ import annotations

import json
import subprocess


class LLMCallError(Exception):
    pass


def call_claude(prompt: str, timeout: int = 300) -> str:
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json", "--allowedTools", ""],
            capture_output=True, text=True, timeout=timeout, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise LLMCallError(f"claude CLI 호출 실패: {e}") from e

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise LLMCallError(f"claude CLI 출력 JSON 파싱 실패: {e}\n원본: {proc.stdout[:500]}") from e

    if payload.get("is_error"):
        raise LLMCallError(f"claude CLI가 에러 반환: {payload}")

    result = payload.get("result")
    if not isinstance(result, str):
        raise LLMCallError(f"claude CLI 출력에 result 필드 없음: {payload}")
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_llm_cli.py -v`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add research/papers/__init__.py research/papers/llm_cli.py tests/test_llm_cli.py
git commit -m "feat: add Claude CLI subprocess wrapper for paper-mining LLM calls"
```

---

### Task 2: `research/papers/arxiv_fetcher.py` — arXiv 폴링 + 커서 dedup + PDF 텍스트 추출

**Files:**
- Modify: `pyproject.toml` (dependencies에 `pdfplumber>=0.11` 추가)
- Create: `research/papers/arxiv_fetcher.py`
- Test: `tests/test_arxiv_fetcher.py`

**Interfaces:**
- Consumes: 없음 (독립)
- Produces:
  - `load_cursor(path: str = _CURSOR_PATH) -> str | None` — 마지막 처리 논문의 `published` ISO 문자열, 파일 없으면 `None`
  - `save_cursor(published: str, path: str = _CURSOR_PATH) -> None`
  - `fetch_papers(max_results: int = 50, categories: list[str] | None = None) -> list[dict]` — 각 dict: `{"id": str, "title": str, "abstract": str, "published": str, "pdf_url": str}`, arXiv API HTTP 실패 시 최대 3회 재시도(1s/2s/4s 백오프) 후 `RuntimeError`
  - `filter_new_papers(papers: list[dict], last_seen: str | None) -> list[dict]` — `published > last_seen`인 것만, `last_seen`이 `None`이면 전부 통과. 순수함수.
  - `download_pdf_text(pdf_url: str) -> str` — pdfplumber로 PDF 다운로드+텍스트 추출
  - Task 7(`run_paper_ingest.py`)이 이 5개 심볼 전부 import해서 쓴다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_arxiv_fetcher.py
import json
from unittest.mock import patch, MagicMock

import pytest
import requests

from research.papers.arxiv_fetcher import (
    load_cursor, save_cursor, fetch_papers, filter_new_papers,
)

_ATOM_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2601.00001v1</id>
    <title>Momentum Signals in Intraday Equity Markets</title>
    <summary>We study intraday momentum signals.</summary>
    <published>2026-07-10T00:00:00Z</published>
    <link title="pdf" href="http://arxiv.org/pdf/2601.00001v1" rel="related" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2601.00002v1</id>
    <title>Options Volatility Risk Premium</title>
    <summary>We study the vol risk premium.</summary>
    <published>2026-07-11T00:00:00Z</published>
    <link title="pdf" href="http://arxiv.org/pdf/2601.00002v1" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""


def test_load_cursor_returns_none_when_file_missing(tmp_path):
    path = str(tmp_path / "cursor.json")
    assert load_cursor(path) is None


def test_save_and_load_cursor_roundtrip(tmp_path):
    path = str(tmp_path / "cursor.json")
    save_cursor("2026-07-11T00:00:00Z", path)
    assert load_cursor(path) == "2026-07-11T00:00:00Z"


def test_fetch_papers_parses_atom_feed():
    resp = MagicMock(text=_ATOM_RESPONSE, status_code=200)
    resp.raise_for_status = MagicMock()
    with patch("requests.get", return_value=resp):
        papers = fetch_papers(max_results=10)
    assert len(papers) == 2
    assert papers[0]["id"] == "2601.00001v1"
    assert papers[0]["title"] == "Momentum Signals in Intraday Equity Markets"
    assert papers[0]["pdf_url"] == "http://arxiv.org/pdf/2601.00001v1"
    assert papers[0]["published"] == "2026-07-10T00:00:00Z"


def test_fetch_papers_retries_on_failure_then_succeeds():
    resp_ok = MagicMock(text=_ATOM_RESPONSE, status_code=200)
    resp_ok.raise_for_status = MagicMock()
    with patch("requests.get", side_effect=[requests.ConnectionError("boom"), resp_ok]) as mock_get, \
         patch("time.sleep"):
        papers = fetch_papers(max_results=10)
    assert len(papers) == 2
    assert mock_get.call_count == 2


def test_fetch_papers_raises_after_max_retries():
    with patch("requests.get", side_effect=requests.ConnectionError("boom")), \
         patch("time.sleep"):
        with pytest.raises(RuntimeError):
            fetch_papers(max_results=10)


def test_filter_new_papers_keeps_only_after_cursor():
    papers = [
        {"id": "1", "published": "2026-07-10T00:00:00Z"},
        {"id": "2", "published": "2026-07-12T00:00:00Z"},
    ]
    out = filter_new_papers(papers, last_seen="2026-07-11T00:00:00Z")
    assert [p["id"] for p in out] == ["2"]


def test_filter_new_papers_keeps_all_when_no_cursor():
    papers = [{"id": "1", "published": "2026-07-10T00:00:00Z"}]
    out = filter_new_papers(papers, last_seen=None)
    assert [p["id"] for p in out] == ["1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_arxiv_fetcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.papers.arxiv_fetcher'`

- [ ] **Step 3: Add pdfplumber dependency**

Edit `pyproject.toml` dependencies list:

```toml
dependencies = [
    "nautilus_trader",
    "requests>=2.31",
    "python-dotenv>=1.0",
    "ib_async>=2.1.0",
    "fastapi>=0.110",
    "pydantic>=2.0",
    "uvicorn>=0.29",
    "numpy>=1.26",
    "scipy>=1.13",
    "pandas>=2.0",
    "websockets>=15.0",
    "pdfplumber>=0.11",
]
```

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pip install pdfplumber>=0.11`

- [ ] **Step 4: Write minimal implementation**

```python
# research/papers/arxiv_fetcher.py
"""arXiv q-fin 논문 폴링 — 커서 dedup, PDF→텍스트 추출.

1회성 트리거 스크립트(run_paper_ingest.py)에서 호출. 24/7 폴러 아님 —
arXiv는 일단위 다이제스트라 커서파일로 마지막 처리 논문 이후만 가져온다.
"""
from __future__ import annotations

import json
import os
import time
import xml.etree.ElementTree as ET

import requests

_CURSOR_PATH = "research/data/paper_pipeline/cursor.json"
_ARXIV_API = "http://export.arxiv.org/api/query"
_DEFAULT_CATEGORIES = ["q-fin.PM", "q-fin.TR", "q-fin.ST", "q-fin.CP"]
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_MAX_RETRIES = 3


def load_cursor(path: str = _CURSOR_PATH) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f).get("last_seen_published")


def save_cursor(published: str, path: str = _CURSOR_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"last_seen_published": published}, f)


def _parse_atom(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    papers = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        raw_id = entry.findtext("atom:id", default="", namespaces=_ATOM_NS)
        arxiv_id = raw_id.rsplit("/", 1)[-1]
        title = (entry.findtext("atom:title", default="", namespaces=_ATOM_NS) or "").strip()
        abstract = (entry.findtext("atom:summary", default="", namespaces=_ATOM_NS) or "").strip()
        published = entry.findtext("atom:published", default="", namespaces=_ATOM_NS)
        pdf_url = ""
        for link in entry.findall("atom:link", _ATOM_NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href", "")
                break
        papers.append({
            "id": arxiv_id, "title": title, "abstract": abstract,
            "published": published, "pdf_url": pdf_url,
        })
    return papers


def fetch_papers(max_results: int = 50, categories: list[str] | None = None) -> list[dict]:
    cats = categories or _DEFAULT_CATEGORIES
    query = " OR ".join(f"cat:{c}" for c in cats)
    params = {
        "search_query": query, "sortBy": "submittedDate", "sortOrder": "descending",
        "max_results": max_results,
    }
    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(_ARXIV_API, params=params, timeout=30)
            resp.raise_for_status()
            return _parse_atom(resp.text)
        except requests.RequestException as e:
            last_err = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"arXiv fetch 최대 재시도 초과: {last_err}")


def filter_new_papers(papers: list[dict], last_seen: str | None) -> list[dict]:
    if last_seen is None:
        return list(papers)
    return [p for p in papers if p["published"] > last_seen]


def download_pdf_text(pdf_url: str) -> str:
    import pdfplumber
    import io

    resp = requests.get(pdf_url, timeout=60)
    resp.raise_for_status()
    text_parts = []
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_arxiv_fetcher.py -v`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml research/papers/arxiv_fetcher.py tests/test_arxiv_fetcher.py
git commit -m "feat: add arXiv fetcher with cursor dedup and PDF text extraction"
```

---

### Task 3: `research/papers/coverage_filter.py` — 자산커버리지 필터 (순수함수)

**Files:**
- Create: `research/papers/coverage_filter.py`
- Test: `tests/test_coverage_filter.py`

**Interfaces:**
- Consumes: 없음 (독립, 순수함수)
- Produces: `is_covered(spec: dict) -> bool`, `rejection_reason(spec: dict) -> str | None` (통과 시 `None`). Task 7(`run_paper_ingest.py`)이 `rejection_reason`을 import해서 쓴다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coverage_filter.py
from research.papers.coverage_filter import is_covered, rejection_reason


def test_equity_intraday_is_covered():
    assert is_covered({"asset_class": "equity_intraday"}) is True
    assert rejection_reason({"asset_class": "equity_intraday"}) is None


def test_other_asset_classes_are_rejected():
    for ac in ["equity_daily", "crypto", "futures", "options", "fx", "other"]:
        spec = {"asset_class": ac}
        assert is_covered(spec) is False
        reason = rejection_reason(spec)
        assert reason is not None
        assert ac in reason


def test_missing_asset_class_is_rejected():
    assert is_covered({}) is False
    assert rejection_reason({}) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_coverage_filter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.papers.coverage_filter'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/papers/coverage_filter.py
"""자산커버리지 필터 — v1은 equity_intraday만 코드생성 대상.

순수함수. 통과 못 한 스펙 기록(rejected.jsonl)은 호출측(run_paper_ingest.py)
책임 — 이 모듈은 판정만 한다."""
from __future__ import annotations

SUPPORTED_ASSET_CLASSES = {"equity_intraday"}


def is_covered(spec: dict) -> bool:
    return spec.get("asset_class") in SUPPORTED_ASSET_CLASSES


def rejection_reason(spec: dict) -> str | None:
    if is_covered(spec):
        return None
    return f"자산군 미지원: {spec.get('asset_class')!r} (v1 지원: {sorted(SUPPORTED_ASSET_CLASSES)})"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_coverage_filter.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add research/papers/coverage_filter.py tests/test_coverage_filter.py
git commit -m "feat: add asset-coverage filter for paper hypotheses"
```

---

### Task 4: `research/papers/extract_spec.py` — LLM 논문텍스트→구조화스펙

**Files:**
- Create: `research/papers/extract_spec.py`
- Test: `tests/test_extract_spec.py`

**Interfaces:**
- Consumes: `research.papers.llm_cli.call_claude(prompt: str, timeout: int = 300) -> str` (Task 1)
- Produces: `extract_spec(paper_text: str) -> dict` — 반환 dict는 반드시 `asset_class`, `signal_description`, `direction`, `holding_period`, `data_requirements` 키를 가짐. LLM 응답이 JSON이 아니거나 필수 키가 빠지면 `ValueError`. Task 7이 이 심볼을 import해서 쓴다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extract_spec.py
import json
from unittest.mock import patch

import pytest

from research.papers.extract_spec import extract_spec

_VALID_SPEC = {
    "asset_class": "equity_intraday",
    "signal_description": "장 시작 30분 이후 VWAP 대비 0.4% 이상 이탈 시 평균회귀",
    "direction": "long_only",
    "holding_period": "1일 이내",
    "data_requirements": ["15분봉 OHLCV"],
}


def test_extract_spec_parses_valid_llm_response():
    with patch("research.papers.extract_spec.call_claude", return_value=json.dumps(_VALID_SPEC)):
        spec = extract_spec("some paper text")
    assert spec == _VALID_SPEC


def test_extract_spec_raises_on_malformed_json():
    with patch("research.papers.extract_spec.call_claude", return_value="not json{{{"):
        with pytest.raises(ValueError):
            extract_spec("some paper text")


def test_extract_spec_raises_on_missing_required_key():
    incomplete = {k: v for k, v in _VALID_SPEC.items() if k != "asset_class"}
    with patch("research.papers.extract_spec.call_claude", return_value=json.dumps(incomplete)):
        with pytest.raises(ValueError):
            extract_spec("some paper text")


def test_extract_spec_truncates_long_paper_text():
    captured = {}

    def fake_call(prompt, *a, **kw):
        captured["prompt"] = prompt
        return json.dumps(_VALID_SPEC)

    with patch("research.papers.extract_spec.call_claude", side_effect=fake_call):
        extract_spec("x" * 100_000)
    assert len(captured["prompt"]) < 100_000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_extract_spec.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.papers.extract_spec'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/papers/extract_spec.py
"""논문 텍스트 → 구조화 스펙(JSON) — LLM 호출 1건.

llm_cli.call_claude()로 Claude CLI 서브프로세스를 호출하고, 응답을 고정
스키마(asset_class/signal_description/direction/holding_period/
data_requirements)로 검증한다. asset_class는 자산군 무관하게 항상 채우되,
코드생성기(codegen_signal.py)는 equity_intraday일 때만 연결한다."""
from __future__ import annotations

import json

from research.papers.llm_cli import call_claude

_REQUIRED_KEYS = {"asset_class", "signal_description", "direction", "holding_period", "data_requirements"}
_MAX_CHARS = 40_000

_PROMPT_TEMPLATE = """다음은 계량투자 학술논문의 텍스트다. 이 논문이 제시하는 트레이딩
시그널/전략을 아래 JSON 스키마로만 응답하라 (설명 텍스트 없이 JSON만):

{{
  "asset_class": "equity_intraday" | "equity_daily" | "crypto" | "futures" | "options" | "fx" | "other",
  "signal_description": "<시그널을 계산 가능한 수준으로 한 문단 요약>",
  "direction": "long_only" | "long_short" | "unclear",
  "holding_period": "<보유기간, 예: '1일 이내' 또는 '5-20 거래일'>",
  "data_requirements": ["<필요 데이터 종류, 예: '15분봉 OHLCV', '옵션 IV 서페이스'>"]
}}

asset_class는 논문이 실제로 검증한 자산군을 반영하되, 일중(장중) 주가/거래량만으로
계산 가능한 시그널이면 "equity_intraday"로 분류하라.

논문:
---
{paper_text}
---
"""


def extract_spec(paper_text: str) -> dict:
    prompt = _PROMPT_TEMPLATE.format(paper_text=paper_text[:_MAX_CHARS])
    raw = call_claude(prompt)
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM 응답 JSON 파싱 실패: {e}\n원본: {raw[:500]}") from e
    missing = _REQUIRED_KEYS - spec.keys()
    if missing:
        raise ValueError(f"LLM 응답에 필수 키 누락: {missing}")
    return spec
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_extract_spec.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add research/papers/extract_spec.py tests/test_extract_spec.py
git commit -m "feat: add LLM-based paper spec extraction"
```

---

### Task 5: `research/papers/smoke_check.py` — 생성코드 스모크체크 (순수함수, exec 기반)

**Files:**
- Create: `research/papers/smoke_check.py`
- Test: `tests/test_smoke_check.py`

**Interfaces:**
- Consumes: 없음 (독립)
- Produces: `check(code: str) -> tuple[bool, str]` — `(통과여부, 사유)`, 통과면 사유는 빈 문자열. Task 7이 이 심볼을 import해서 쓴다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke_check.py
from research.papers.smoke_check import check

_GOOD_CODE = '''
NAME = "vwap_fade"
DESCRIPTION = "VWAP 이탈 평균회귀"

def signal_fn(ohlc, feat, aux, params):
    c = ohlc["close"]
    n = len(c)
    entry = [False] * n
    elig = list(range(n))
    for i in range(n):
        if i % 10 == 0:
            entry[i] = True
    return {"entry": entry, "eligible": elig}
'''

_CRASHING_CODE = '''
NAME = "broken"
DESCRIPTION = "d"

def signal_fn(ohlc, feat, aux, params):
    raise RuntimeError("boom")
'''

_ALL_FALSE_CODE = '''
NAME = "dead"
DESCRIPTION = "d"

def signal_fn(ohlc, feat, aux, params):
    n = len(ohlc["close"])
    return {"entry": [False] * n, "eligible": list(range(n))}
'''

_NAN_CODE = '''
NAME = "nan"
DESCRIPTION = "d"

def signal_fn(ohlc, feat, aux, params):
    n = len(ohlc["close"])
    return {"entry": [float("nan")] * n, "eligible": list(range(n))}
'''

_SYNTAX_ERROR_CODE = "def signal_fn(:::\n"

_MISSING_SYMBOLS_CODE = '''
X = 1
'''


def test_check_passes_valid_signal_fn():
    ok, reason = check(_GOOD_CODE)
    assert ok is True
    assert reason == ""


def test_check_rejects_syntax_error():
    ok, reason = check(_SYNTAX_ERROR_CODE)
    assert ok is False
    assert "exec" in reason.lower() or "syntax" in reason.lower()


def test_check_rejects_missing_required_symbols():
    ok, reason = check(_MISSING_SYMBOLS_CODE)
    assert ok is False
    assert "심볼" in reason


def test_check_rejects_crashing_signal_fn():
    ok, reason = check(_CRASHING_CODE)
    assert ok is False
    assert "boom" in reason


def test_check_rejects_all_false_entry():
    ok, reason = check(_ALL_FALSE_CODE)
    assert ok is False
    assert "False" in reason


def test_check_rejects_nan_entry():
    ok, reason = check(_NAN_CODE)
    assert ok is False
    assert "NaN" in reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_smoke_check.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.papers.smoke_check'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/papers/smoke_check.py
"""생성된 SignalFn 코드 스모크체크 — 크래시/전부-False/NaN 여부만 확인하는
싼 필터. 통계적 유의미성은 여기서 안 봄(그건 run_paper_hypothesis_validate.py
+ runner.py 엔진 몫). fixture OHLC는 합성 데이터 — exec 안전성 확인용."""
from __future__ import annotations

import math

REQUIRED_SYMBOLS = ("NAME", "DESCRIPTION", "signal_fn")


def _fixture_ohlc(n: int = 200) -> dict:
    close = [100.0 + (i % 20) * 0.5 - (i % 7) * 0.3 for i in range(n)]
    high = [c + 0.5 for c in close]
    low = [c - 0.5 for c in close]
    open_ = [c - 0.1 for c in close]
    volume = [1000.0 + (i % 10) * 50 for i in range(n)]
    ts = list(range(n))
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume, "ts": ts}


def _fixture_feat(ohlc: dict) -> dict:
    n = len(ohlc["close"])
    return {
        "sids": [0] * n,
        "mso": [float(i % 390) for i in range(n)],
        "vwap": list(ohlc["close"]),
        "atr_abs": [1.0] * n,
    }


def check(code: str) -> tuple[bool, str]:
    namespace: dict = {}
    try:
        exec(code, namespace)
    except Exception as e:
        return False, f"exec 실패: {e}"

    missing = [s for s in REQUIRED_SYMBOLS if s not in namespace]
    if missing:
        return False, f"필수 심볼 누락: {missing}"

    signal_fn = namespace["signal_fn"]
    ohlc = _fixture_ohlc()
    feat = _fixture_feat(ohlc)
    try:
        result = signal_fn(ohlc, feat, {}, {})
    except Exception as e:
        return False, f"signal_fn 실행 실패: {e}"

    if not isinstance(result, dict) or "entry" not in result or "eligible" not in result:
        return False, "signal_fn 반환값에 entry/eligible 키 없음"

    entry = result["entry"]
    if len(entry) != len(ohlc["close"]):
        return False, f"entry 길이 불일치: {len(entry)} != {len(ohlc['close'])}"
    if any(e is None for e in entry):
        return False, "entry에 None 포함(bool이어야 함)"
    if any(isinstance(e, float) and math.isnan(e) for e in entry):
        return False, "entry에 NaN 포함"
    if not any(entry):
        return False, "entry 전부 False — 시그널 없음"

    return True, ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_smoke_check.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add research/papers/smoke_check.py tests/test_smoke_check.py
git commit -m "feat: add smoke-check for LLM-generated signal code"
```

---

### Task 6: `research/papers/codegen_signal.py` — LLM 스펙→SignalFn 코드생성

**Files:**
- Create: `research/papers/codegen_signal.py`
- Test: `tests/test_codegen_signal.py`

**Interfaces:**
- Consumes: `research.papers.llm_cli.call_claude(prompt: str, timeout: int = 300) -> str` (Task 1)
- Produces: `generate_signal_code(spec: dict) -> str` — 생성된 Python 소스코드 문자열 그대로 반환(파일 저장은 안 함, 호출측 책임). Task 7이 이 심볼을 import해서 쓴다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_codegen_signal.py
from unittest.mock import patch

from research.papers.codegen_signal import generate_signal_code

_SPEC = {
    "asset_class": "equity_intraday",
    "signal_description": "VWAP 이탈 평균회귀",
    "direction": "long_only",
    "holding_period": "1일 이내",
    "data_requirements": ["15분봉 OHLCV"],
}

_GENERATED_CODE = '''NAME = "vwap_fade"
DESCRIPTION = "VWAP 이탈 평균회귀"

def signal_fn(ohlc, feat, aux, params):
    return {"entry": [False] * len(ohlc["close"]), "eligible": []}
'''


def test_generate_signal_code_returns_llm_output_verbatim():
    with patch("research.papers.codegen_signal.call_claude", return_value=_GENERATED_CODE) as mock_call:
        code = generate_signal_code(_SPEC)
    assert code == _GENERATED_CODE
    mock_call.assert_called_once()


def test_generate_signal_code_prompt_includes_spec_fields():
    captured = {}

    def fake_call(prompt, *a, **kw):
        captured["prompt"] = prompt
        return _GENERATED_CODE

    with patch("research.papers.codegen_signal.call_claude", side_effect=fake_call):
        generate_signal_code(_SPEC)
    assert "VWAP 이탈 평균회귀" in captured["prompt"]
    assert "signal_fn" in captured["prompt"]
    assert "entry" in captured["prompt"] and "eligible" in captured["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_codegen_signal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.papers.codegen_signal'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/papers/codegen_signal.py
"""구조화 스펙 → SignalFn 코드 생성 — LLM 호출 1건.

runner.py 시그니처 (ohlc, feat, aux, params) -> {"entry": bool[], "eligible": int[]}
를 반드시 지키도록 few-shot(strategies.py 발췌)으로 강제한다. 생성된 코드는
문자열로만 반환 — 파일 저장은 호출측(run_paper_ingest.py) 책임."""
from __future__ import annotations

import json

from research.papers.llm_cli import call_claude

_FEW_SHOT = '''# 예시 — 기존 research/hypotheses/strategies.py의 실제 가설 하나:
def vwap_mean_reversion(ohlc, feat, aux, params):
    c, vwap, mso, atr = ohlc["close"], feat["vwap"], feat["mso"], feat["atr_abs"]
    dev_k = params.get("dev_k", 0.004)
    n = len(c); entry = [False] * n; elig = []
    for i in range(n):
        if not (mso[i] >= 30 and vwap[i] and atr[i]):
            continue
        elig.append(i)
        dev = (c[i] - vwap[i]) / vwap[i]
        if dev < -dev_k:
            entry[i] = True
    return {"entry": entry, "eligible": elig}
'''

_PROMPT_TEMPLATE = '''아래는 트레이딩 시그널 함수 작성 예시다:
{few_shot}

feat 딕셔너리 키: sids(세션ID), mso(장시작후경과분), vwap(세션VWAP), atr_abs(ATR절대값).
전부 ohlc["close"]와 같은 길이 리스트, 세션 시작 전이나 계산불가 구간은 None.

이제 아래 스펙을 구현하는 Python 함수를 작성하라. 반드시 이 형식만 출력(설명
없이 코드만, 마크다운 코드펜스도 없이):

NAME = "<영문 소문자 스네이크케이스 슬러그, 20자 이내>"
DESCRIPTION = "<한 줄 요약>"

def signal_fn(ohlc, feat, aux, params):
    ...
    return {{"entry": entry, "eligible": elig}}

제약: 롱온리(entry는 매수 진입 신호만), params는 튜닝 없이 고정값 사용(하드코딩
가능), 외부 네트워크/파일 접근 금지, import는 표준 라이브러리만.

스펙:
{spec_json}
'''


def generate_signal_code(spec: dict) -> str:
    prompt = _PROMPT_TEMPLATE.format(
        few_shot=_FEW_SHOT, spec_json=json.dumps(spec, ensure_ascii=False, indent=2),
    )
    return call_claude(prompt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_codegen_signal.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add research/papers/codegen_signal.py tests/test_codegen_signal.py
git commit -m "feat: add LLM-based signal code generation from paper spec"
```

---

### Task 7: `research/run_paper_ingest.py` — 5단계 orchestration (1회성 트리거)

**Files:**
- Create: `research/run_paper_ingest.py`
- Test: `tests/test_run_paper_ingest.py`

**Interfaces:**
- Consumes:
  - `research.papers.arxiv_fetcher.{load_cursor, save_cursor, fetch_papers, filter_new_papers, download_pdf_text}` (Task 2)
  - `research.papers.coverage_filter.rejection_reason(spec: dict) -> str | None` (Task 3)
  - `research.papers.extract_spec.extract_spec(paper_text: str) -> dict` (Task 4)
  - `research.papers.smoke_check.check(code: str) -> tuple[bool, str]` (Task 5)
  - `research.papers.codegen_signal.generate_signal_code(spec: dict) -> str` (Task 6)
- Produces: `process_paper(paper: dict) -> str` (상태 문자열: `"accepted"|"pdf_error"|"spec_error"|"coverage_reject"|"codegen_error"|"smoke_reject"`), `main(max_results: int = 50) -> dict`. `research/hypotheses/papers/<arxiv_id>_<slug>.py` 파일들을 생성 — Task 8(`run_paper_hypothesis_validate.py`)이 이 디렉토리를 읽는다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_paper_ingest.py
import json
from unittest.mock import patch

import research.run_paper_ingest as ingest


def _paper(id="1234.5678", title="Momentum Test", published="2026-07-10T00:00:00Z", pdf_url="http://x/1.pdf"):
    return {"id": id, "title": title, "abstract": "a", "published": published, "pdf_url": pdf_url}


def test_process_paper_accepted_writes_module_file(tmp_path):
    with patch.object(ingest, "_HYPOTHESES_DIR", tmp_path), \
         patch.object(ingest, "download_pdf_text", return_value="paper text"), \
         patch.object(ingest, "extract_spec", return_value={"asset_class": "equity_intraday", "signal_description": "d"}), \
         patch.object(ingest, "rejection_reason", return_value=None), \
         patch.object(ingest, "generate_signal_code",
                       return_value="NAME = 'x'\nDESCRIPTION = 'd'\ndef signal_fn(o,f,a,p):\n    return {'entry': [], 'eligible': []}\n"), \
         patch.object(ingest, "smoke_check", return_value=(True, "")):
        status = ingest.process_paper(_paper())
    assert status == "accepted"
    files = list(tmp_path.glob("*.py"))
    assert len(files) == 1
    assert "signal_fn" in files[0].read_text()
    assert "1234.5678" in files[0].read_text()


def test_process_paper_coverage_reject_logs_and_skips_codegen(tmp_path):
    rejected_path = tmp_path / "rejected.jsonl"
    with patch.object(ingest, "_REJECTED_PATH", rejected_path), \
         patch.object(ingest, "download_pdf_text", return_value="paper text"), \
         patch.object(ingest, "extract_spec", return_value={"asset_class": "options"}), \
         patch.object(ingest, "rejection_reason", return_value="자산군 미지원: 'options'"), \
         patch.object(ingest, "generate_signal_code") as mock_codegen:
        status = ingest.process_paper(_paper())
    assert status == "coverage_reject"
    mock_codegen.assert_not_called()
    logged = json.loads(rejected_path.read_text().strip())
    assert logged["stage"] == "coverage_filter"


def test_process_paper_smoke_reject_does_not_write_file(tmp_path):
    with patch.object(ingest, "_HYPOTHESES_DIR", tmp_path), \
         patch.object(ingest, "_REJECTED_PATH", tmp_path / "rejected.jsonl"), \
         patch.object(ingest, "download_pdf_text", return_value="paper text"), \
         patch.object(ingest, "extract_spec", return_value={"asset_class": "equity_intraday"}), \
         patch.object(ingest, "rejection_reason", return_value=None), \
         patch.object(ingest, "generate_signal_code", return_value="broken code((("), \
         patch.object(ingest, "smoke_check", return_value=(False, "exec 실패")):
        status = ingest.process_paper(_paper())
    assert status == "smoke_reject"
    assert list(tmp_path.glob("*.py")) == []


def test_process_paper_pdf_download_error_logs_and_stops():
    with patch.object(ingest, "_REJECTED_PATH", "unused"), \
         patch.object(ingest, "_log_rejected") as mock_log, \
         patch.object(ingest, "download_pdf_text", side_effect=RuntimeError("404")), \
         patch.object(ingest, "extract_spec") as mock_extract:
        status = ingest.process_paper(_paper())
    assert status == "pdf_error"
    mock_extract.assert_not_called()
    mock_log.assert_called_once()


def test_main_advances_cursor_to_max_published_among_new_papers():
    papers = [_paper(id="1", published="2026-07-10T00:00:00Z"),
              _paper(id="2", published="2026-07-12T00:00:00Z")]
    with patch.object(ingest, "load_cursor", return_value=None), \
         patch.object(ingest, "fetch_papers", return_value=papers), \
         patch.object(ingest, "filter_new_papers", return_value=papers), \
         patch.object(ingest, "process_paper", return_value="accepted") as mock_process, \
         patch.object(ingest, "save_cursor") as mock_save:
        result = ingest.main()
    assert mock_process.call_count == 2
    mock_save.assert_called_once_with("2026-07-12T00:00:00Z")
    assert result["counts"] == {"accepted": 2}
    assert result["n_fetched"] == 2
    assert result["n_new"] == 2


def test_main_does_not_advance_cursor_when_no_new_papers():
    with patch.object(ingest, "load_cursor", return_value="2026-07-12T00:00:00Z"), \
         patch.object(ingest, "fetch_papers", return_value=[]), \
         patch.object(ingest, "filter_new_papers", return_value=[]), \
         patch.object(ingest, "save_cursor") as mock_save:
        result = ingest.main()
    mock_save.assert_not_called()
    assert result["counts"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_paper_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.run_paper_ingest'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/run_paper_ingest.py
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
    download_pdf_text, fetch_papers, filter_new_papers, load_cursor, save_cursor,
)
from research.papers.codegen_signal import generate_signal_code
from research.papers.coverage_filter import rejection_reason
from research.papers.extract_spec import extract_spec
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
        code = generate_signal_code(spec)
    except Exception as e:
        _log_rejected(arxiv_id, title, "codegen", str(e))
        return "codegen_error"

    ok, smoke_reason = smoke_check(code)
    if not ok:
        _log_rejected(arxiv_id, title, "smoke_check", smoke_reason)
        return "smoke_reject"

    hyp_dir = Path(_HYPOTHESES_DIR)
    hyp_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(title)
    module_path = hyp_dir / f"{arxiv_id.replace('.', '_')}_{slug}.py"
    header = f'"""{title} (arXiv:{arxiv_id})\n{spec.get("signal_description", "")}\n"""\n'
    module_path.write_text(header + code)
    return "accepted"


def main(max_results: int = 50) -> dict:
    last_seen = load_cursor()
    papers = fetch_papers(max_results=max_results)
    new_papers = filter_new_papers(papers, last_seen)

    counts: dict[str, int] = {}
    max_published = last_seen
    for paper in new_papers:
        status = process_paper(paper)
        counts[status] = counts.get(status, 0) + 1
        if max_published is None or paper["published"] > max_published:
            max_published = paper["published"]

    if new_papers and max_published is not None:
        save_cursor(max_published)

    return {"n_fetched": len(papers), "n_new": len(new_papers), "counts": counts}


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2, ensure_ascii=False))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_paper_ingest.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add research/run_paper_ingest.py tests/test_run_paper_ingest.py
git commit -m "feat: add paper-ingest orchestration pipeline"
```

---

### Task 8: `research/run_paper_hypothesis_validate.py` — 신규 격리 BH-FDR 검증러너

**Files:**
- Create: `research/run_paper_hypothesis_validate.py`
- Test: `tests/test_run_paper_hypothesis_validate.py`

**Interfaces:**
- Consumes: `research.hypotheses.runner.run_universe(name: str, desc: str, signals_fn, aux_fn=None, params=None, universe=None) -> dict` (기존, 결과 dict에 `pooled.empirical_p_value: float | None`, `verdict: str` 포함), `research.validation.multiple_testing.benjamini_hochberg(pvals: list[float], alpha: float = 0.1) -> dict` (기존)
- Produces: `discover_hypotheses() -> list[dict]` (각 dict: `{"path": str, "name": str, "desc": str, "signal_fn": Callable}`), `main() -> dict` (반환: `{"results": list[dict], "bh_fdr": dict}`). 사람이 직접 실행하는 최종 단계 — 다른 모듈이 이 파일을 import하지 않는다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_paper_hypothesis_validate.py
from unittest.mock import patch

import research.run_paper_hypothesis_validate as v


def _fake_result(name, pval, total_pnl=10.0):
    return {
        "name": name, "verdict": "INCONCLUSIVE — 보류",
        "pooled": {"empirical_p_value": pval, "total_pnl": total_pnl,
                   "percentile_vs_random": 50.0, "num_trades": 5,
                   "expectancy": 1.0, "profit_factor": 1.1, "win_rate": 0.5,
                   "random_median": 0.0},
    }


def test_discover_hypotheses_loads_modules_with_required_symbols(tmp_path):
    good = tmp_path / "good.py"
    good.write_text(
        'NAME = "good"\nDESCRIPTION = "d"\n'
        'def signal_fn(ohlc, feat, aux, params):\n    return {"entry": [], "eligible": []}\n'
    )
    bad = tmp_path / "bad.py"
    bad.write_text("X = 1\n")
    with patch.object(v, "_HYPOTHESES_DIR", str(tmp_path)):
        found = v.discover_hypotheses()
    assert [h["name"] for h in found] == ["good"]
    assert callable(found[0]["signal_fn"])


def test_main_with_no_hypotheses_returns_empty_results():
    with patch.object(v, "discover_hypotheses", return_value=[]):
        result = v.main()
    assert result["results"] == []
    assert result["bh_fdr"]["n_survivors"] == 0
    assert result["bh_fdr"]["survivors"] == []


def test_main_pools_pvalues_across_hypotheses_and_runs_bh_fdr():
    fake_hyps = [
        {"path": "a.py", "name": "paper_a", "desc": "d", "signal_fn": lambda *a: None},
        {"path": "b.py", "name": "paper_b", "desc": "d", "signal_fn": lambda *a: None},
    ]
    fake_results = [_fake_result("paper_a", 0.01), _fake_result("paper_b", 0.9)]
    with patch.object(v, "discover_hypotheses", return_value=fake_hyps), \
         patch.object(v, "run_universe", side_effect=fake_results):
        result = v.main()
    assert [r["name"] for r in result["results"]] == ["paper_a", "paper_b"]
    assert result["results"][0]["verdict"] == "INCONCLUSIVE — 보류"
    assert result["bh_fdr"]["names"] == ["paper_a", "paper_b"]


def test_main_skips_none_pvalue_when_pooling():
    fake_hyps = [{"path": "a.py", "name": "paper_a", "desc": "d", "signal_fn": lambda *a: None}]
    fake_results = [_fake_result("paper_a", None)]
    with patch.object(v, "discover_hypotheses", return_value=fake_hyps), \
         patch.object(v, "run_universe", side_effect=fake_results):
        result = v.main()
    assert result["bh_fdr"]["names"] == []
    assert result["bh_fdr"]["n_survivors"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_paper_hypothesis_validate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.run_paper_hypothesis_validate'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/run_paper_hypothesis_validate.py
"""논문 자동생성 가설 검증 러너 — research/hypotheses/papers/*.py 통과분을
기존 runner.py 제네릭 엔진에 태우고, 논문가설 전용 신규 격리 BH-FDR 풀로
correction한다(기존 수동가설 풀과 절대 안 섞음, alpha=0.1).

각 가설은 이미 runner.run_universe() 내부에서 종목별 BH-FDR/OOS를 거친
pooled["empirical_p_value"]를 얻는다 — 이 러너는 그 pooled p-value들을
가설 간(논문 간) 레벨에서 다시 한번 BH-FDR로 묶는다. 실집행 근거 아님,
통계적 스크리닝만. CANDIDATE라도 라이브 집행은 기존 arm_criteria 게이트를
그대로 통과해야 함.
"""
from __future__ import annotations

import glob
import importlib.util
import os

from research.hypotheses.runner import run_universe
from research.validation.multiple_testing import benjamini_hochberg

_HYPOTHESES_DIR = "research/hypotheses/papers"


def _load_module(path: str):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(f"research.hypotheses.papers.{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_hypotheses() -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(_HYPOTHESES_DIR, "*.py"))):
        module = _load_module(path)
        if all(hasattr(module, s) for s in ("NAME", "DESCRIPTION", "signal_fn")):
            out.append({"path": path, "name": module.NAME, "desc": module.DESCRIPTION, "signal_fn": module.signal_fn})
    return out


def main() -> dict:
    hypotheses = discover_hypotheses()
    results = []
    pvals: list[float] = []
    names: list[str] = []

    for h in hypotheses:
        r = run_universe(h["name"], h["desc"], h["signal_fn"])
        results.append(r)
        pval = r["pooled"]["empirical_p_value"]
        if pval is not None:
            pvals.append(pval)
            names.append(h["name"])

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1,
    }
    bh["names"] = names

    print(f"\n=== 논문가설 {len(hypotheses)}개 검증 (신규 격리 BH-FDR 풀, alpha=0.1) ===\n")
    for r in results:
        p = r["pooled"]
        print(f"{r['name']}: pnl={p['total_pnl']} p={p['empirical_p_value']} "
              f"pct={p['percentile_vs_random']} verdict={r['verdict']}")
    survivors = [n for n, s in zip(bh["names"], bh["survivors"]) if s]
    print(f"\nsurvivors: {survivors}")
    print(f"n_survivors: {bh['n_survivors']} / {len(pvals)}")

    return {"results": results, "bh_fdr": bh}


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_paper_hypothesis_validate.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add research/run_paper_hypothesis_validate.py tests/test_run_paper_hypothesis_validate.py
git commit -m "feat: add isolated BH-FDR validation runner for paper hypotheses"
```

---

### Task 9: 전체 스위트 확인 + 진행 문서 갱신

**Files:**
- Modify: `docs/progress.md` (프로젝트 루트 = `seokminal-multi-venue`, 없으면 생성)

**Interfaces:**
- Consumes: 없음 (전체 검증 단계)
- Produces: 없음 (문서화 + 최종 확인)

- [ ] **Step 1: 전체 테스트 스위트 실행**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: 신규 8개 테스트 파일 전부 통과, 기존 pre-existing failures(test_auth.py ×3-4, test_backtest_happy_path)만 남고 나머지 전부 통과.

- [ ] **Step 2: docs/progress.md에 완료 항목 기록**

`docs/progress.md`에 다음 섹션 추가:

```markdown
## Phase 133: 논문 기반 알파 마이닝 파이프라인

완료된 작업: arXiv q-fin 논문 자동 폴링→PDF텍스트추출→LLM스펙추출→
자산커버리지필터(equity_intraday만)→LLM코드생성→스모크체크→
research/hypotheses/papers/ 저장, 별도 러너로 신규 격리 BH-FDR 풀 검증.
LLM은 Claude CLI 서브프로세스 재사용(신규 API키 불필요).

변경된 파일: research/papers/{__init__,llm_cli,arxiv_fetcher,coverage_filter,
extract_spec,codegen_signal,smoke_check}.py, research/run_paper_ingest.py,
research/run_paper_hypothesis_validate.py, pyproject.toml(pdfplumber 추가),
tests/test_{llm_cli,arxiv_fetcher,coverage_filter,extract_spec,smoke_check,
codegen_signal,run_paper_ingest,run_paper_hypothesis_validate}.py.

다음 할 일: `python -m research.run_paper_ingest` 실제 1회 실행해서 라이브
arXiv 논문으로 파이프라인 end-to-end 검증(코드생성 품질/스모크체크 통과율
확인). 통과 가설 쌓이면 `python -m research.run_paper_hypothesis_validate`
로 검증.

막힌 부분/결정사항: v1은 equity_intraday만, OS-level cron 자동화는 범위
밖(수동 트리거만). CANDIDATE 나와도 arm_criteria 게이트 통과 전엔 집행 안 함.
```

- [ ] **Step 3: Commit**

```bash
git add docs/progress.md
git commit -m "docs: record paper-alpha-mining pipeline completion in progress log"
```

---

## Self-Review

**1. Spec coverage:**
- 2절(arXiv 소스) → Task 2 `arxiv_fetcher.py` (categories 기본값 q-fin.PM/TR/ST/CP)
- 3절(완전자동+2단계 필터) → Task 3(coverage_filter) + Task 5(smoke_check), Task 7이 두 필터를 순서대로 배선
- 4절(v1 equity_intraday 스코프, 자산군 무관 파싱스키마) → Task 3(`SUPPORTED_ASSET_CLASSES = {"equity_intraday"}`) + Task 4(`extract_spec`은 6개 자산군 전부 스키마에 허용)
- 5절(아키텍처 7개 파일 + 데이터흐름) → Task 1-8이 정확히 1:1 대응
- 6절(Claude CLI, 신규 API키 불필요) → Task 1, 라이브 검증된 `result` 필드 스키마 그대로 반영
- 7절(1회성 트리거, cron 아님) → Task 7 `if __name__ == "__main__"` 진입점만, 스케줄러 코드 없음
- 8절(pdfplumber 신규의존성) → Task 2 Step 3
- 9절(에러처리, rejected.jsonl 감사기록) → Task 7 `_log_rejected` + 6개 실패단계 전부 분기
- 10절(테스트 5개+α) → Task 1,2,3,5에서 스펙이 명시한 5개 전부 작성, Task 4/6/7/8에 추가 테스트(스펙 미명시지만 품질상 필요)
- 11절(out of scope: 크립토/선물 코드생성 안 함, cron 없음, arm_criteria 그대로 유지) → Task 3이 equity_intraday 외 전부 차단, Task 7에 스케줄러 없음, Task 8 docstring에 arm_criteria 언급 유지

**2. Placeholder scan:** 전 Task 코드블록 완결 — TBD/TODO/"적절히 처리" 없음. 확인 완료.

**3. Type consistency:**
- `call_claude(prompt: str, timeout: int = 300) -> str` — Task 1 정의, Task 4/6에서 동일 시그니처로 import.
- `rejection_reason(spec: dict) -> str | None` — Task 3 정의, Task 7에서 동일하게 사용.
- `extract_spec(paper_text: str) -> dict` — Task 4 정의, Task 7에서 동일.
- `generate_signal_code(spec: dict) -> str` — Task 6 정의, Task 7에서 동일.
- `check(code: str) -> tuple[bool, str]` — Task 5 정의, Task 7에서 `smoke_check` 별칭으로 import(as smoke_check), 동일 시그니처.
- `SignalFn` 시그니처 `(ohlc, feat, aux, params) -> {"entry": bool[], "eligible": int[]}` — Task 5(fixture 체크), Task 6(codegen 프롬프트 강제), Task 8(`run_universe` 전달)에서 전부 일관.
- `run_universe(name, desc, signals_fn, aux_fn=None, params=None, universe=None) -> dict` — 기존 `research/hypotheses/runner.py:67`과 Task 8 호출부(`run_universe(h["name"], h["desc"], h["signal_fn"])`) 위치인자 순서 일치 확인.
- `benjamini_hochberg(pvals: list[float], alpha: float = 0.1) -> dict` — 기존 `research/validation/multiple_testing.py:6`과 Task 8 호출부(`alpha=0.1` 명시) 일치.

이상 없음.
