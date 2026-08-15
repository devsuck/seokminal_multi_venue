"""Living Knowledge Graph — AI 인프라 공급망 그래프.

노드: 기업·기술·자원·정책
엣지: 공급·의존·경쟁·규제·자금흐름

AI 업데이트 파이프라인:
  뉴스/공시 원문 → 엔티티 추출 → 관계 추론 → 그래프 패치
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, BackgroundTasks

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["knowledge-graph"])

_GRAPH_PATH = Path(os.environ.get("GRAPH_DB_PATH", "data/knowledge_graph.json"))

# ── 초기 공급망 데이터 ─────────────────────────────────────────────────────────
_SEED: dict[str, Any] = {
    "meta": {
        "version": 1,
        "last_updated": "2026-07-04",
        "update_count": 0,
        "description": "AI 인프라 물리적 공급망 Living Knowledge Graph",
    },
    "nodes": [
        # ── HBM / 메모리 ────────────────────────────────────────────
        {
            "id": "sk_hynix", "label": "SK 하이닉스", "type": "company",
            "sector": "hbm_memory", "country": "KR",
            "bottleneck_score": 0.92,
            "supply_risk": 0.25, "demand_pressure": 0.97, "policy_risk": 0.15,
            "note": "HBM3E 사실상 독점 공급. HBM4 전환 진행 중. CoWoS 패키징 TSMC 의존.",
        },
        {
            "id": "samsung_semi", "label": "삼성 반도체", "type": "company",
            "sector": "hbm_memory", "country": "KR",
            "bottleneck_score": 0.65,
            "supply_risk": 0.45, "demand_pressure": 0.80, "policy_risk": 0.20,
            "note": "HBM3 수율 이슈. 엔비디아 퀄 테스트 진행 중.",
        },
        {
            "id": "micron", "label": "Micron", "type": "company",
            "sector": "hbm_memory", "country": "US",
            "bottleneck_score": 0.55,
            "supply_risk": 0.35, "demand_pressure": 0.75, "policy_risk": 0.10,
            "note": "HBM3E 3rd 공급자. US CHIPS Act 보조금 수혜.",
        },
        # ── GPU / 파운드리 ───────────────────────────────────────────
        {
            "id": "nvidia", "label": "NVIDIA", "type": "company",
            "sector": "gpu_demand", "country": "US",
            "bottleneck_score": 0.88,
            "supply_risk": 0.60, "demand_pressure": 0.99, "policy_risk": 0.35,
            "note": "Blackwell 공급 제한 지속. CoWoS 기판 병목. 中 수출 규제 리스크.",
        },
        {
            "id": "tsmc", "label": "TSMC", "type": "company",
            "sector": "foundry", "country": "TW",
            "bottleneck_score": 0.85,
            "supply_risk": 0.70, "demand_pressure": 0.95, "policy_risk": 0.50,
            "note": "CoWoS 첨단 패키징 병목. 지정학 리스크 최고. N3/N2 독점.",
        },
        {
            "id": "asml", "label": "ASML", "type": "company",
            "sector": "equipment", "country": "NL",
            "bottleneck_score": 0.80,
            "supply_risk": 0.30, "demand_pressure": 0.90, "policy_risk": 0.60,
            "note": "EUV 전 세계 독점. 中 수출 금지. 납기 2~3년 대기.",
        },
        # ── 전력 인프라 ─────────────────────────────────────────────
        {
            "id": "kepco", "label": "한국전력", "type": "company",
            "sector": "power_infra", "country": "KR",
            "bottleneck_score": 0.70,
            "supply_risk": 0.55, "demand_pressure": 0.80, "policy_risk": 0.40,
            "note": "AI 데이터센터 전력 급증으로 망 용량 포화 위기. 재무구조 취약.",
        },
        {
            "id": "ls_electric", "label": "LS ELECTRIC", "type": "company",
            "sector": "power_infra", "country": "KR",
            "bottleneck_score": 0.75,
            "supply_risk": 0.20, "demand_pressure": 0.88, "policy_risk": 0.10,
            "note": "초고압 변압기 글로벌 수요 폭발. 납기 18개월 이상.",
        },
        {
            "id": "hyosung_heavy", "label": "효성중공업", "type": "company",
            "sector": "power_infra", "country": "KR",
            "bottleneck_score": 0.72,
            "supply_risk": 0.22, "demand_pressure": 0.85, "policy_risk": 0.10,
            "note": "GIS·변압기 수출 급증. 미국 전력망 노후화 수혜.",
        },
        {
            "id": "hd_electric", "label": "HD현대일렉트릭", "type": "company",
            "sector": "power_infra", "country": "KR",
            "bottleneck_score": 0.68,
            "supply_risk": 0.25, "demand_pressure": 0.82, "policy_risk": 0.10,
            "note": "변압기·전력기기 오더북 사상 최대.",
        },
        # ── 데이터센터 부지·냉각 ────────────────────────────────────
        {
            "id": "naver_cloud", "label": "네이버 클라우드", "type": "company",
            "sector": "datacenter", "country": "KR",
            "bottleneck_score": 0.50,
            "supply_risk": 0.30, "demand_pressure": 0.70, "policy_risk": 0.20,
            "note": "세종 IDC 확장. 전력·용수 부지 확보 경쟁 심화.",
        },
        {
            "id": "vertiv", "label": "Vertiv", "type": "company",
            "sector": "cooling", "country": "US",
            "bottleneck_score": 0.65,
            "supply_risk": 0.30, "demand_pressure": 0.85, "policy_risk": 0.05,
            "note": "액침냉각·직접수냉(DLC) 수요 폭발. 리드타임 급증.",
        },
        # ── AI 수요처 ───────────────────────────────────────────────
        {
            "id": "meta", "label": "Meta", "type": "company",
            "sector": "ai_demand", "country": "US",
            "bottleneck_score": 0.30,
            "supply_risk": 0.05, "demand_pressure": 0.95, "policy_risk": 0.15,
            "note": "2026년 GPU CapEx $60B+. 자체 MTIA칩 병행.",
        },
        {
            "id": "microsoft", "label": "Microsoft", "type": "company",
            "sector": "ai_demand", "country": "US",
            "bottleneck_score": 0.25,
            "supply_risk": 0.05, "demand_pressure": 0.95, "policy_risk": 0.10,
            "note": "Azure AI 인프라 $80B CapEx 발표. Maia 자체칩 개발.",
        },
        # ── 정책 노드 ───────────────────────────────────────────────
        {
            "id": "kr_ai_act", "label": "한국 AI 기본법", "type": "policy",
            "sector": "regulation", "country": "KR",
            "bottleneck_score": 0.30,
            "supply_risk": 0.0, "demand_pressure": 0.0, "policy_risk": 0.60,
            "note": "2026년 시행 예정. 고위험 AI 규제·데이터 거버넌스 의무화.",
        },
        {
            "id": "us_chips_act", "label": "US CHIPS Act", "type": "policy",
            "sector": "regulation", "country": "US",
            "bottleneck_score": 0.40,
            "supply_risk": 0.0, "demand_pressure": 0.0, "policy_risk": 0.35,
            "note": "반도체 생산 보조금 $52B. 한국 기업 美 팹 투자 유인.",
        },
        {
            "id": "cn_export_ban", "label": "對中 수출 규제", "type": "policy",
            "sector": "regulation", "country": "US",
            "bottleneck_score": 0.60,
            "supply_risk": 0.0, "demand_pressure": 0.0, "policy_risk": 0.90,
            "note": "H100/A100 → H20 → 추가 규제 확대. ASML EUV 完禁.",
        },
        # ── 자원 노드 ───────────────────────────────────────────────
        {
            "id": "hbm_cowos", "label": "CoWoS 패키징 용량", "type": "resource",
            "sector": "hbm_memory", "country": "TW",
            "bottleneck_score": 0.95,
            "supply_risk": 0.90, "demand_pressure": 0.99, "policy_risk": 0.20,
            "note": "최대 병목. TSMC 독점. 2025년까지 수요의 60%만 충족 가능.",
        },
        {
            "id": "power_grid_kr", "label": "KR 전력망 용량", "type": "resource",
            "sector": "power_infra", "country": "KR",
            "bottleneck_score": 0.78,
            "supply_risk": 0.75, "demand_pressure": 0.88, "policy_risk": 0.30,
            "note": "AI DC 전력 수요 2028년까지 3배 증가 전망. 망 증설 속도 부족.",
        },
    ],
    "edges": [
        # HBM 공급망
        {"source": "sk_hynix",    "target": "nvidia",      "relation": "supplies",    "type": "hbm_memory",    "weight": 0.92, "bottleneck": True,  "evidence": "HBM3E 사실상 독점 공급. Blackwell GPU당 8스택."},
        {"source": "samsung_semi","target": "nvidia",      "relation": "supplies",    "type": "hbm_memory",    "weight": 0.30, "bottleneck": False, "evidence": "퀄 테스트 진행 중. 2025 하반기 양산 목표."},
        {"source": "micron",      "target": "nvidia",      "relation": "supplies",    "type": "hbm_memory",    "weight": 0.25, "bottleneck": False, "evidence": "HBM3E 3rd 공급자. 점유율 확대 중."},
        # CoWoS 패키징 병목
        {"source": "sk_hynix",    "target": "hbm_cowos",   "relation": "depends_on",  "type": "packaging",     "weight": 0.95, "bottleneck": True,  "evidence": "HBM 패키징 전량 TSMC CoWoS 의존."},
        {"source": "hbm_cowos",   "target": "tsmc",        "relation": "operated_by", "type": "packaging",     "weight": 1.00, "bottleneck": True,  "evidence": "CoWoS는 TSMC 독점 기술."},
        # 파운드리
        {"source": "tsmc",        "target": "nvidia",      "relation": "manufactures","type": "chip_fab",      "weight": 0.90, "bottleneck": True,  "evidence": "N3/N4P Blackwell GPU 전량 TSMC."},
        {"source": "asml",        "target": "tsmc",        "relation": "supplies",    "type": "euv_equipment", "weight": 0.85, "bottleneck": True,  "evidence": "EUV 독점 공급. 없으면 N3 불가."},
        # 전력
        {"source": "kepco",       "target": "sk_hynix",   "relation": "supplies",    "type": "power",         "weight": 0.80, "bottleneck": True,  "evidence": "이천/청주 팹 전력 공급. 용량 포화 리스크."},
        {"source": "ls_electric", "target": "kepco",      "relation": "supplies",    "type": "transformer",   "weight": 0.75, "bottleneck": True,  "evidence": "초고압 변압기 공급. 납기 18개월+."},
        {"source": "hyosung_heavy","target": "kepco",     "relation": "supplies",    "type": "transformer",   "weight": 0.65, "bottleneck": False, "evidence": "GIS·변압기 수출 병행."},
        {"source": "hd_electric", "target": "kepco",      "relation": "supplies",    "type": "transformer",   "weight": 0.60, "bottleneck": False, "evidence": "변압기 오더북 확대 중."},
        {"source": "power_grid_kr","target": "naver_cloud","relation": "constrains", "type": "power",         "weight": 0.70, "bottleneck": True,  "evidence": "KR IDC 전력 인허가 지연 심각."},
        # 냉각
        {"source": "vertiv",      "target": "naver_cloud", "relation": "supplies",    "type": "cooling",       "weight": 0.55, "bottleneck": False, "evidence": "DLC 시스템 공급."},
        # AI 수요
        {"source": "nvidia",      "target": "meta",        "relation": "supplies",    "type": "gpu",           "weight": 0.85, "bottleneck": False, "evidence": "H100/H200/B200 대량 공급."},
        {"source": "nvidia",      "target": "microsoft",   "relation": "supplies",    "type": "gpu",           "weight": 0.90, "bottleneck": False, "evidence": "Azure OpenAI 인프라 전용 GPU."},
        # 정책
        {"source": "cn_export_ban","target": "nvidia",    "relation": "constrains",  "type": "regulation",    "weight": 0.80, "bottleneck": True,  "evidence": "H20 추가 규제 가능성. 中 매출 20% 리스크."},
        {"source": "cn_export_ban","target": "asml",      "relation": "constrains",  "type": "regulation",    "weight": 0.95, "bottleneck": True,  "evidence": "EUV 對中 완전 금지. ASML 직접 매출 타격."},
        {"source": "us_chips_act", "target": "samsung_semi","relation": "incentivizes","type": "subsidy",     "weight": 0.60, "bottleneck": False, "evidence": "텍사스 팹 보조금 수혜."},
        {"source": "us_chips_act", "target": "micron",    "relation": "incentivizes","type": "subsidy",       "weight": 0.65, "bottleneck": False, "evidence": "$6.1B 보조금 확정."},
        {"source": "kr_ai_act",    "target": "naver_cloud","relation": "regulates",  "type": "regulation",    "weight": 0.50, "bottleneck": False, "evidence": "고위험 AI 서비스 규제 대상."},
    ],
}


def _load() -> dict:
    if _GRAPH_PATH.exists():
        return json.loads(_GRAPH_PATH.read_text())
    _GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GRAPH_PATH.write_text(json.dumps(_SEED, ensure_ascii=False, indent=2))
    return _SEED


def _save(g: dict) -> None:
    _GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GRAPH_PATH.write_text(json.dumps(g, ensure_ascii=False, indent=2))


# ── 스코어 이력 ───────────────────────────────────────────────────────────────
# 그래프 json은 현재 상태만 들고 있어서 "병목이 오르는 중인가"를 알 수 없다.
# 패치될 때마다 노드 스코어를 append-only로 남겨 /history/{node_id}가 추세로 읽는다.
_HISTORY_PATH = _GRAPH_PATH.parent / "graph_history.jsonl"
_HISTORY_FIELDS = ("bottleneck_score", "supply_risk", "demand_pressure", "policy_risk")


def _append_history(g: dict, ts: str) -> None:
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _HISTORY_PATH.open("a") as f:
        for n in g["nodes"]:
            row = {"ts": ts, "node_id": n["id"], **{k: n.get(k) for k in _HISTORY_FIELDS}}
            f.write(json.dumps(row) + "\n")


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get("")
def get_graph() -> dict:
    return _load()


@router.post("/patch")
def patch_graph(patch: dict) -> dict:
    """노드·엣지 부분 업데이트. AI 파이프라인이 호출."""
    g = _load()
    now = _dt.datetime.utcnow().isoformat()

    if "nodes" in patch:
        existing = {n["id"]: i for i, n in enumerate(g["nodes"])}
        required = {"label", "type", "sector"}
        for n in patch["nodes"]:
            if n["id"] in existing:
                g["nodes"][existing[n["id"]]].update(n)
                g["nodes"][existing[n["id"]]]["last_updated"] = now
            elif required <= n.keys():
                n["last_updated"] = now
                g["nodes"].append(n)
            else:
                _log.warning("ai-update: dropping new node %r missing %s", n.get("id"), required - n.keys())

    if "edges" in patch:
        key = lambda e: (e["source"], e["target"], e.get("type", ""))
        existing = {key(e): i for i, e in enumerate(g["edges"])}
        for e in patch["edges"]:
            k = key(e)
            if k in existing:
                g["edges"][existing[k]].update(e)
                g["edges"][existing[k]]["last_updated"] = now
            else:
                e["last_updated"] = now
                g["edges"].append(e)

    g["meta"]["last_updated"] = now
    g["meta"]["update_count"] = g["meta"].get("update_count", 0) + 1
    if "update_log" not in g["meta"]:
        g["meta"]["update_log"] = []
    g["meta"]["update_log"] = ([{"ts": now, "summary": patch.get("summary", "manual patch")}]
                                + g["meta"]["update_log"])[:50]
    _save(g)
    _append_history(g, now)
    return {"status": "ok", "update_count": g["meta"]["update_count"]}


@router.get("/history/{node_id}")
def get_node_history(node_id: str, limit: int = 200) -> dict:
    """노드 스코어 시계열(오래된 것 → 최신). 이력 없으면 빈 배열."""
    if not _HISTORY_PATH.exists():
        return {"node_id": node_id, "history": []}
    rows = [json.loads(ln) for ln in _HISTORY_PATH.read_text().splitlines() if ln.strip()]
    return {"node_id": node_id, "history": [r for r in rows if r["node_id"] == node_id][-limit:]}


# ── AI 업데이트 파이프라인 ────────────────────────────────────────────────────

# 모니터링 심볼 → 그래프 노드 id 매핑
_WATCH_TICKERS = {
    "NVDA": "nvidia", "TSM": "tsmc", "ASML": "asml",
    "MU": "micron", "AMD": "amd",
}
_WATCH_GENERAL_CATEGORIES = ["technology", "general"]

# AI 업데이트 중 중복 실행 방지
_update_running = False


def _claude_bin() -> str | None:
    return shutil.which("claude") or (
        os.path.expanduser("~/.local/bin/claude")
        if os.path.exists(os.path.expanduser("~/.local/bin/claude")) else None
    )


def _fetch_news_headlines(finnhub_key: str, max_per_ticker: int = 5) -> list[str]:
    """Finnhub에서 핵심 뉴스 헤드라인 수집."""
    headlines: list[str] = []
    now = _dt.datetime.utcnow()
    date_to = now.strftime("%Y-%m-%d")
    date_from = (now - _dt.timedelta(days=3)).strftime("%Y-%m-%d")

    # 기업별 뉴스
    for ticker in _WATCH_TICKERS:
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/company-news",
                params={"symbol": ticker, "from": date_from, "to": date_to, "token": finnhub_key},
                timeout=8,
            )
            for item in r.json()[:max_per_ticker]:
                h = item.get("headline", "").strip()
                if h:
                    headlines.append(f"[{ticker}] {h}")
        except Exception as e:
            _log.warning("finnhub company-news %s failed: %s", ticker, e)

    # 시장 일반 뉴스 (tech)
    for cat in _WATCH_GENERAL_CATEGORIES:
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/news",
                params={"category": cat, "token": finnhub_key},
                timeout=8,
            )
            for item in r.json()[:8]:
                h = item.get("headline", "").strip()
                if h and any(kw in h.lower() for kw in [
                    "nvidia", "tsmc", "hbm", "asml", "semiconductor", "gpu",
                    "datacenter", "data center", "ai chip", "power grid", "transformer",
                    "sk hynix", "samsung", "micron", "cowos", "blackwell",
                ]):
                    headlines.append(f"[market/{cat}] {h}")
        except Exception as e:
            _log.warning("finnhub market-news %s failed: %s", cat, e)

    return headlines[:40]


def _build_prompt(graph: dict, headlines: list[str]) -> str:
    """그래프 현황 + 뉴스 → Claude 프롬프트."""
    node_summary = "\n".join(
        f"  {n['id']}: {n['label']} | 병목={n['bottleneck_score']:.2f} | "
        f"공급리스크={n['supply_risk']:.2f} | 수요압박={n['demand_pressure']:.2f} | "
        f"정책리스크={n['policy_risk']:.2f} | note={n.get('note','')[:80]}"
        for n in graph["nodes"]
    )
    news_block = "\n".join(f"  - {h}" for h in headlines) if headlines else "  (뉴스 없음)"

    return f"""당신은 AI 인프라 공급망 분석 AI다.
아래 [현재 그래프 상태]와 [최신 뉴스]를 보고, 업데이트가 필요한 노드/엣지를 추출하라.

[현재 그래프 노드]
{node_summary}

[최신 뉴스 헤드라인 (최근 3일)]
{news_block}

[규칙]
1. 뉴스에서 공급망 관계 변화, 병목 심화/완화, 정책 변경을 감지하라.
2. 변화가 있는 노드만 패치하라. 변화 없으면 nodes/edges를 빈 배열로.
3. bottleneck_score/supply_risk/demand_pressure/policy_risk는 0.0~1.0.
4. note 필드에 뉴스 기반 근거 한 줄을 써라.
5. 새 엣지 추가 시 source/target은 기존 노드 id만 사용.

[출력] JSON 한 줄만. 설명 금지:
{{"nodes":[{{"id":"<기존id>","bottleneck_score":0.0,"supply_risk":0.0,"demand_pressure":0.0,"policy_risk":0.0,"note":"<근거>"}}],"edges":[{{"source":"<id>","target":"<id>","relation":"<supplies|depends_on|constrains|incentivizes>","type":"<타입>","weight":0.0,"bottleneck":false,"evidence":"<근거>"}}],"summary":"<변경 요약 한 줄>"}}"""


def run_ai_update(finnhub_key: str | None = None) -> dict:
    """AI 업데이트 파이프라인 실행 (동기, background task용)."""
    global _update_running
    if _update_running:
        return {"status": "already_running"}
    _update_running = True
    try:
        claude = _claude_bin()
        if claude is None:
            return {"status": "error", "detail": "claude CLI 없음"}

        key = finnhub_key or os.environ.get("FINNHUB_API_KEY", "")
        if not key:
            return {"status": "error", "detail": "FINNHUB_API_KEY 없음 — 뉴스 수집 불가"}

        headlines = _fetch_news_headlines(key)
        graph = _load()
        old_nodes = {n["id"]: dict(n) for n in graph["nodes"]}
        prompt = _build_prompt(graph, headlines)

        proc = subprocess.run(
            [claude, "--dangerously-skip-permissions", "--permission-mode",
             "bypassPermissions", "--print", prompt],
            capture_output=True, text=True, timeout=120,
        )
        raw = proc.stdout

        # JSON 추출 (마지막 {…} 블록)
        matches = re.findall(r"\{.*\}", raw, re.DOTALL)
        if not matches:
            return {"status": "error", "detail": "Claude 출력에 JSON 없음", "raw": raw[:300]}

        patch = json.loads(matches[-1])
        result = patch_graph(patch)
        result["headlines_used"] = len(headlines)
        result["summary"] = patch.get("summary", "")

        new_nodes = {n["id"]: dict(n) for n in _load()["nodes"]}
        signals = _generate_signals(old_nodes, new_nodes, key)
        result["paper_signals"] = len(signals)
        return result
    except Exception as e:
        _log.error("ai-update failed: %s", e)
        return {"status": "error", "detail": str(e)}
    finally:
        _update_running = False


@router.post("/ai-update")
def trigger_ai_update(background_tasks: BackgroundTasks) -> dict:
    """AI 파이프라인으로 그래프 업데이트 (비동기 실행)."""
    if _update_running:
        return {"status": "already_running", "message": "업데이트 이미 진행 중"}
    finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
    background_tasks.add_task(run_ai_update, finnhub_key)
    return {"status": "started", "message": "AI 업데이트 시작. /graph 폴링으로 결과 확인."}


@router.get("/update-status")
def get_update_status() -> dict:
    """업데이트 진행 상태 + 최근 로그."""
    g = _load()
    return {
        "running": _update_running,
        "last_updated": g["meta"].get("last_updated"),
        "update_count": g["meta"].get("update_count", 0),
        "recent_log": g["meta"].get("update_log", [])[:10],
    }


@router.post("/reset")
def reset_graph() -> dict:
    """시드 데이터로 초기화."""
    seed = dict(_SEED)
    seed["meta"] = dict(_SEED["meta"])
    seed["meta"]["last_updated"] = _dt.datetime.utcnow().isoformat()
    seed["meta"]["update_count"] = 0
    _save(seed)
    return {"status": "reset"}


# ── 페이퍼 트레이딩 ───────────────────────────────────────────────────────────

_TICKER_MAP: dict[str, dict] = {
    "sk_hynix":      {"symbol": "000660.KS", "name": "SK하이닉스"},
    "samsung_semi":  {"symbol": "005930.KS", "name": "삼성 반도체"},
    "micron":        {"symbol": "MU",         "name": "Micron"},
    "nvidia":        {"symbol": "NVDA",       "name": "NVIDIA"},
    "tsmc":          {"symbol": "TSM",        "name": "TSMC"},
    "asml":          {"symbol": "ASML",       "name": "ASML"},
    "kepco":         {"symbol": "015760.KS",  "name": "한국전력"},
    "ls_electric":   {"symbol": "010120.KS",  "name": "LS ELECTRIC"},
    "hyosung_heavy": {"symbol": "267270.KS",  "name": "효성중공업"},
    "hd_electric":   {"symbol": "267260.KS",  "name": "HD현대일렉트릭"},
    "vertiv":        {"symbol": "VRT",         "name": "Vertiv"},
}

_SECTOR_DIRECTION: dict[str, str] = {
    "hbm_memory": "LONG", "foundry": "LONG", "equipment": "LONG",
    "power_infra": "LONG", "datacenter": "LONG", "cooling": "LONG",
    "gpu_demand": "LONG", "ai_demand": "LONG",
    "regulation": "SKIP", "resource": "SKIP",
}

_PAPER_FILE = _GRAPH_PATH.parent / "lkg_paper.json"
_PAPER_INITIAL = 10_000.0
_MAX_POSITIONS = 5
_POSITION_PCT = 0.20
_SIGNAL_THRESHOLD = 0.05


def _load_paper() -> dict:
    if _PAPER_FILE.exists():
        return json.loads(_PAPER_FILE.read_text())
    state: dict = {"capital": _PAPER_INITIAL, "cash": _PAPER_INITIAL, "positions": [], "closed": [], "signals": []}
    _save_paper(state)
    return state


def _save_paper(state: dict) -> None:
    _PAPER_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PAPER_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _fetch_quote(symbol: str, key: str) -> float | None:
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol, "token": key},
            timeout=5,
        )
        price = float(r.json().get("c") or 0)
        return price if price > 0 else None
    except Exception:
        return None


def _generate_signals(old_nodes: dict, new_nodes: dict, finnhub_key: str) -> list[dict]:
    """bottleneck_score 변화 → 페이퍼 포지션 자동 집행."""
    paper = _load_paper()
    signals: list[dict] = []
    now = _dt.datetime.utcnow().isoformat()

    for node_id, new_node in new_nodes.items():
        old_node = old_nodes.get(node_id)
        if not old_node:
            continue
        old_score = old_node.get("bottleneck_score", 0.0)
        new_score = new_node.get("bottleneck_score", 0.0)
        delta = new_score - old_score
        if abs(delta) < _SIGNAL_THRESHOLD:
            continue
        ticker_info = _TICKER_MAP.get(node_id)
        if not ticker_info:
            continue
        direction = _SECTOR_DIRECTION.get(new_node.get("sector", ""), "SKIP")
        if direction == "SKIP":
            continue
        if len(paper["positions"]) >= _MAX_POSITIONS:
            continue
        if any(p["node_id"] == node_id for p in paper["positions"]):
            continue

        symbol = ticker_info["symbol"]
        price = _fetch_quote(symbol, finnhub_key)
        if not price:
            continue

        position_value = round(paper["cash"] * _POSITION_PCT, 2)
        if paper["cash"] < position_value or position_value < 1.0:
            continue

        qty = round(position_value / price, 4)
        actual_value = round(qty * price, 2)
        side = "BUY" if delta > 0 else "SELL"

        position = {
            "node_id": node_id, "symbol": symbol, "name": ticker_info["name"],
            "side": side, "qty": qty, "entry_price": price,
            "entry_score": round(old_score, 4), "current_score": round(new_score, 4),
            "score_delta": round(delta, 4), "entry_time": now, "value": actual_value,
        }
        paper["cash"] = round(paper["cash"] - actual_value, 2)
        paper["positions"].append(position)

        sig = {
            "ts": now, "node_id": node_id, "symbol": symbol, "name": ticker_info["name"],
            "side": side, "price": price, "score_delta": round(delta, 4),
            "summary": f"{ticker_info['name']} {side} @ ${price:.2f} — 병목 {old_score:.2f}→{new_score:.2f} (Δ{delta:+.2f})",
        }
        paper["signals"].insert(0, sig)
        signals.append(sig)

    paper["signals"] = paper["signals"][:50]
    _save_paper(paper)
    return signals


def _mark_to_market(paper: dict) -> dict:
    """오픈 포지션에 live quote 반영 — entry_price/value(원가)는 청산정산용이라 그대로 두고
    current_price/market_value/unrealized_pnl만 얹어서 반환(디스크엔 저장 안 함)."""
    finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
    positions = []
    for pos in paper["positions"]:
        price = _fetch_quote(pos["symbol"], finnhub_key)
        current_price = price if price else pos["entry_price"]
        market_value = round(pos["qty"] * current_price, 2)
        unrealized_pnl = round(
            (current_price - pos["entry_price"]) * pos["qty"] if pos["side"] == "BUY"
            else (pos["entry_price"] - current_price) * pos["qty"],
            2,
        )
        positions.append({**pos, "current_price": current_price,
                           "market_value": market_value, "unrealized_pnl": unrealized_pnl})
    return {**paper, "positions": positions}


@router.get("/paper")
def get_paper() -> dict:
    return _mark_to_market(_load_paper())


@router.post("/paper/reset")
def reset_paper() -> dict:
    state: dict = {"capital": _PAPER_INITIAL, "cash": _PAPER_INITIAL, "positions": [], "closed": [], "signals": []}
    _save_paper(state)
    return state


@router.post("/paper/close/{node_id}")
def close_position(node_id: str) -> dict:
    from fastapi import HTTPException
    paper = _load_paper()
    pos = next((p for p in paper["positions"] if p["node_id"] == node_id), None)
    if pos is None:
        raise HTTPException(404, f"Position {node_id} not found")

    finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
    exit_price = _fetch_quote(pos["symbol"], finnhub_key) or pos["entry_price"]
    pnl = round(
        (exit_price - pos["entry_price"]) * pos["qty"] if pos["side"] == "BUY"
        else (pos["entry_price"] - exit_price) * pos["qty"],
        2,
    )
    closed = {**pos, "exit_price": exit_price, "exit_time": _dt.datetime.utcnow().isoformat(), "pnl": pnl}
    paper["closed"].insert(0, closed)
    paper["positions"] = [p for p in paper["positions"] if p["node_id"] != node_id]
    paper["cash"] = round(paper["cash"] + pos["value"] + pnl, 2)
    paper["closed"] = paper["closed"][:50]
    _save_paper(paper)
    return closed
