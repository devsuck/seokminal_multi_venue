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
