# LAB ↔ Auto-Research 판정 통합(단일 진실원 + 배치 되먹임) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI LAB(라이브 단일가설 루프)과 Auto-Research(배치 BH-FDR 리더보드)의 서로 다른 판정 로직 두 벌을 단일 `classify()` 함수로 통합하고, LAB이 배치 BH-FDR 결과를 되먹임해 통계적으로 정직한 잠정/확정 판정을 내리게 한다.

**Architecture:** 공유 판정 함수 `research/scanner/verdict.py::classify()`를 신설해 두 시스템의 유일한 진실원으로 삼는다. classify는 이벤트 증거(net·percentile·p·wf) + 레드팀 verdict + `bh_survivor(True/False/None)`를 받아 canonical status를 낸다. `bh_survivor=None`(LAB 라이브, 배치 미확정)이면 `pending_bh`(잠정)만 주고 candidate 도장은 보류 — BH-FDR은 전체 배치가 있어야만 계산 가능하다는 통계적 사실을 코드로 강제한다. LAB은 `latest_bh_survivor(fam_id)`로 최신 배치 결과를 읽어 확정 여부를 판단한다.

**Tech Stack:** Python 3.14(FastAPI 백엔드), pytest(asyncio_mode=auto), Next.js/TypeScript 프론트.

## Global Constraints

- Python 인터프리터: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3` (정확히 이 경로).
- 테스트: `@pytest.mark.asyncio` **절대 금지**(asyncio_mode="auto").
- pre-existing 실패 4건 무시: `test_auth.py`×3, `test_backtest_happy_path`. 그 외 실패 0이어야 함.
- 브랜치: main 직접 커밋.
- 프론트 디자인 토큰만: `text-accent/pos/neg/warn/info`, `border-border`, `bg-panel`. `style={{}}` 금지.
- 커밋 메시지 Co-Authored-By: `Claude <noreply@anthropic.com>` (모델명·context 모드 금지).
- 순환 import 금지: `research/autoresearch/engine.py`는 `research/lab/*`를 import하지 않는다(단방향: lab → autoresearch만 허용).

---

## File Structure

- **Create** `research/scanner/verdict.py` — 단일 판정 함수 `classify()` + canonical status 상수 + `DISPLAY` 매핑. scanner에 두는 이유: `event_study`가 여기 있고 lab·autoresearch 둘 다 이미 `research.scanner`를 import함(중립 공유 지점, 순환 없음).
- **Modify** `research/autoresearch/engine.py` — `run_batch`의 인라인 verdict if/elif(L114-122)를 `classify()` 호출로 교체 + `latest_bh_survivor(fam_id)` 리더 신설.
- **Modify** `research/lab/evaluator.py` — `evaluate_real_event`의 인라인 verdict(L148-159 근방)를 `classify()` 호출로 교체 + 최신 배치 `bh_survivor` 읽어 전달.
- **Modify** `research/lab/pipeline.py` — `_finish`의 stats 버킷에 `pending` 추가, `pending_bh` status를 reject로 세지 않도록 분기.
- **Modify** `seokminal-dashboard/app/lab/page.tsx` — `verdictStyle`에 `pending_bh` 처리(info 톤 + "배치 대기") + stats 표시에 pending 반영.
- **Create** `tests/test_verdict_classify.py` — classify 단위 테스트.
- **Modify** `tests/test_lab_pipeline.py` — pending_bh 경로 테스트 추가(있으면).
- **Create** `tests/test_autoresearch_engine.py` — run_batch가 classify 사용 + latest_bh_survivor 왕복 테스트.

---

## Task 1: 단일 판정 함수 `classify()` (공유 진실원)

**Files:**
- Create: `research/scanner/verdict.py`
- Test: `tests/test_verdict_classify.py`

**Interfaces:**
- Produces:
  - `classify(*, net: float|None, percentile: float|None, p: float|None, wf_first: float|None, wf_second: float|None, redteam_verdict: str, bh_survivor: bool|None) -> tuple[str, str]` → `(status, verdict_text)`.
  - canonical status 문자열 상수: `"candidate"`, `"watchlist"`, `"pending_bh"`, `"reject_bh"`, `"reject_redteam"`, `"reject_stats"`.
  - `DISPLAY: dict[str, str]` — canonical status → autoresearch 리더보드 표시용 대문자 verdict(`candidate→"CANDIDATE"`, `reject_bh→"REJECT_BH"`, `reject_redteam→"REJECT_REDTEAM"`, `watchlist→"WATCHLIST"`, `pending_bh→"PENDING"`, `reject_stats→"REJECT_STATS"`).

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_verdict_classify.py`:

```python
"""단일 판정 함수 classify — lab·autoresearch 공유 진실원."""
from __future__ import annotations

from research.scanner.verdict import classify, DISPLAY


def _kw(**kw):
    base = dict(net=100.0, percentile=99.0, p=0.01, wf_first=1.0, wf_second=1.0,
                redteam_verdict="CLEARED", bh_survivor=True)
    base.update(kw)
    return base


def test_candidate_requires_bh_redteam_and_robust_stats():
    status, text = classify(**_kw())
    assert status == "candidate"
    assert "CANDIDATE" in text or "candidate" in text.lower()


def test_bh_survivor_but_redteam_fail_is_reject_redteam():
    status, _ = classify(**_kw(redteam_verdict="REJECTED"))
    assert status == "reject_redteam"


def test_not_bh_survivor_is_reject_bh_even_if_stats_strong():
    status, _ = classify(**_kw(bh_survivor=False))
    assert status == "reject_bh"


def test_bh_survivor_but_negative_wf_is_watchlist():
    # BH 생존 + 레드팀 통과지만 walk-forward 후반 음수 → robust 아님 → watchlist
    status, _ = classify(**_kw(wf_second=-0.5, percentile=85.0))
    assert status == "watchlist"


def test_live_unknown_bh_with_strong_stats_is_pending():
    # bh_survivor=None(라이브, 배치 미확정) → candidate 도장 보류, pending_bh
    status, text = classify(**_kw(bh_survivor=None))
    assert status == "pending_bh"
    assert "대기" in text or "PENDING" in text.upper()


def test_live_unknown_bh_redteam_fail_is_reject_redteam():
    status, _ = classify(**_kw(bh_survivor=None, redteam_verdict="REJECTED"))
    assert status == "reject_redteam"


def test_live_unknown_bh_weak_stats_is_reject_stats():
    status, _ = classify(**_kw(bh_survivor=None, net=-10.0, percentile=40.0))
    assert status == "reject_stats"


def test_display_maps_canonical_to_uppercase():
    assert DISPLAY["candidate"] == "CANDIDATE"
    assert DISPLAY["reject_bh"] == "REJECT_BH"
    assert DISPLAY["reject_redteam"] == "REJECT_REDTEAM"
```

- [ ] **Step 2: 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_verdict_classify.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.scanner.verdict'`

- [ ] **Step 3: 최소 구현**

`research/scanner/verdict.py`:

```python
"""단일 판정 함수 — LAB 라이브 루프와 Auto-Research 배치의 유일한 진실원.

두 시스템 장점 결합:
  - Auto-Research 강점: 배치 BH-FDR(다중검정 보정) → '몇 개 시도했는지' 반영.
  - LAB 강점: net>0 + walk-forward 양쪽 양수(강건성 게이트).
candidate = bh_survivor AND 레드팀 CLEARED AND net>0 AND wf 양쪽 양수.

bh_survivor 의미:
  True  — 최신 배치 BH-FDR 생존(확정).
  False — 배치서 탈락(우연 가능).
  None  — LAB 라이브: 아직 배치 미확정. BH-FDR은 전체 배치가 있어야만 계산 가능하므로
          개별 통계만 통과해도 candidate 도장 불가 → pending_bh(잠정). 통계적 정직성.
"""
from __future__ import annotations

# canonical status
CANDIDATE = "candidate"
WATCHLIST = "watchlist"
PENDING_BH = "pending_bh"
REJECT_BH = "reject_bh"
REJECT_REDTEAM = "reject_redteam"
REJECT_STATS = "reject_stats"

DISPLAY: dict[str, str] = {
    CANDIDATE: "CANDIDATE",
    WATCHLIST: "WATCHLIST",
    PENDING_BH: "PENDING",
    REJECT_BH: "REJECT_BH",
    REJECT_REDTEAM: "REJECT_REDTEAM",
    REJECT_STATS: "REJECT_STATS",
}


def _robust(net: float | None, wf_first: float | None, wf_second: float | None) -> bool:
    return (net or 0) > 0 and (wf_first or 0) > 0 and (wf_second or 0) > 0


def _weak(net: float | None, percentile: float | None) -> bool:
    return (net or 0) > 0 and (percentile or 0) >= 80


def classify(*, net, percentile, p, wf_first, wf_second, redteam_verdict, bh_survivor):
    """(status, verdict_text) — 두 시스템 공유. 위 docstring 규칙 적용."""
    redteam_ok = redteam_verdict == "CLEARED"
    robust = _robust(net, wf_first, wf_second)
    weak = _weak(net, percentile)

    if bh_survivor is None:                       # 라이브: 배치 BH 미확정
        if not redteam_ok:
            return REJECT_REDTEAM, "REJECT — 레드팀 통제 실패"
        if robust:
            return PENDING_BH, "PENDING — 개별 통계 통과, 배치 BH-FDR 확정 대기"
        if weak:
            return WATCHLIST, "WATCHLIST — 양수이나 walk-forward 불안정"
        return REJECT_STATS, "REJECT — 매칭 random·비용 못 넘음"

    if not bh_survivor:
        return REJECT_BH, "REJECT — 배치 BH-FDR 탈락(다중검정 우연 가능)"

    # bh_survivor True
    if not redteam_ok:
        return REJECT_REDTEAM, "REJECT — 레드팀 통제 실패"
    if robust:
        return CANDIDATE, "CANDIDATE — BH-FDR 생존 + 레드팀 + net·walk-forward 통과"
    if weak:
        return WATCHLIST, "WATCHLIST — BH 생존이나 walk-forward 불안정"
    return REJECT_STATS, "REJECT — net·walk-forward 미달"
```

- [ ] **Step 4: 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_verdict_classify.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: 커밋**

```bash
git add research/scanner/verdict.py tests/test_verdict_classify.py
git commit -m "feat: 단일 판정 함수 classify() — lab·autoresearch 공유 진실원

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: `latest_bh_survivor(fam_id)` 배치 결과 리더

**Files:**
- Modify: `research/autoresearch/engine.py` (신규 함수 추가, 파일 끝 `load_status` 근처)
- Test: `tests/test_autoresearch_engine.py` (신규)

**Interfaces:**
- Consumes: `research/autoresearch/engine.py`의 `STATUS`(status.json 경로), `load_status()`.
- Produces: `latest_bh_survivor(fam_id: str) -> bool | None` — 최신 배치 status.json 리더보드에서 `cid == f"ev_{fam_id}"` 항목의 `bh_survivor`를 반환. 배치 없음/해당 family 없음 → `None`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_autoresearch_engine.py`:

```python
"""Auto-Research 엔진 — latest_bh_survivor 리더 + classify 통합."""
from __future__ import annotations

import json

from research.autoresearch import engine


def test_latest_bh_survivor_reads_leaderboard(tmp_path, monkeypatch):
    status = tmp_path / "status.json"
    status.write_text(json.dumps({
        "leaderboard": [
            {"cid": "ev_buyback", "bh_survivor": True},
            {"cid": "ev_spinoff", "bh_survivor": False},
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(engine, "STATUS", str(status))
    assert engine.latest_bh_survivor("buyback") is True
    assert engine.latest_bh_survivor("spinoff") is False


def test_latest_bh_survivor_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "STATUS", str(tmp_path / "nope.json"))
    assert engine.latest_bh_survivor("buyback") is None


def test_latest_bh_survivor_family_absent_returns_none(tmp_path, monkeypatch):
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"leaderboard": [{"cid": "ev_other", "bh_survivor": True}]}),
                      encoding="utf-8")
    monkeypatch.setattr(engine, "STATUS", str(status))
    assert engine.latest_bh_survivor("buyback") is None
```

- [ ] **Step 2: 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_autoresearch_engine.py -q`
Expected: FAIL — `AttributeError: module 'research.autoresearch.engine' has no attribute 'latest_bh_survivor'`

- [ ] **Step 3: 최소 구현**

`research/autoresearch/engine.py` — `load_status` 함수 바로 위(또는 아래)에 추가:

```python
def latest_bh_survivor(fam_id: str) -> bool | None:
    """최신 배치 리더보드에서 이 family의 BH-FDR 생존 여부. 배치/항목 없으면 None(미확정)."""
    if not os.path.exists(STATUS):
        return None
    try:
        with open(STATUS) as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    for e in data.get("leaderboard", []):
        if e.get("cid") == f"ev_{fam_id}":
            return bool(e.get("bh_survivor"))
    return None
```

- [ ] **Step 4: 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_autoresearch_engine.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add research/autoresearch/engine.py tests/test_autoresearch_engine.py
git commit -m "feat: latest_bh_survivor() — 최신 배치 BH-FDR 결과 리더(lab 되먹임용)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Auto-Research `run_batch`가 `classify()` 사용

**Files:**
- Modify: `research/autoresearch/engine.py` (`run_batch` 내부 L114-146 근방)
- Test: `tests/test_autoresearch_engine.py` (Task 2 파일에 추가)

**Interfaces:**
- Consumes: `research.scanner.verdict.classify`, `DISPLAY` (Task 1). `benjamini_hochberg`(기존), `review_strategy`(기존).
- Produces: `run_batch()`의 leaderboard entry `verdict` 필드는 기존과 동일한 대문자 문자열(`"CANDIDATE"`/`"REJECT_BH"`/`"REJECT_REDTEAM"`/`"WATCHLIST"`)을 유지(프론트 호환). 내부 결정은 classify가 담당. **동작 변화(의도):** candidate에 net>0 + wf 양쪽 양수 게이트가 새로 적용 → bh 생존+레드팀 통과여도 wf 음수면 WATCHLIST.

- [ ] **Step 1: 실패 테스트 작성 (Task 2 파일에 append)**

`tests/test_autoresearch_engine.py` 끝에 추가:

```python
def test_run_batch_uses_classify_for_verdicts(monkeypatch, tmp_path):
    """run_batch가 classify 경유 — bh 생존+레드팀 CLEARED+robust면 CANDIDATE,
    wf 음수면 WATCHLIST로 강등(새 강건성 게이트)."""
    from research.scanner import verdict as V

    # 결정 로직만 검증: collect_candidates·permutation을 가짜로 대체
    class _C:
        cid = "ev_fake"; category = "event_family"; thesis = "t"; direction = "bullish"
        meta = {"fam_id": "fake", "n": 100}
        def run(self):
            return {"n": 100, "net": 5.0, "median": 0.1, "percentile": 99.0, "p": 0.001,
                    "wf_first": 1.0, "wf_second": -0.5,  # 후반 음수 → robust 실패
                    "top_tail_share": 0.2, "evidence": {}, "_spec": {"required": []}}

    monkeypatch.setattr(engine, "collect_candidates", lambda: ([_C()], {}))
    monkeypatch.setattr(engine, "benjamini_hochberg",
                        lambda pvals, alpha: {"survivors": [True], "threshold": 0.05, "n_survivors": 1})
    monkeypatch.setattr(engine, "review_strategy", lambda spec, ev: {"verdict": "CLEARED", "failed": [], "missing": []})
    monkeypatch.setattr(engine, "log_experiment", lambda rec: None)
    monkeypatch.setattr(engine, "STATUS", str(tmp_path / "s.json"))
    monkeypatch.setattr(engine, "RESULTS", str(tmp_path / "r.jsonl"))

    summary = engine.run_batch()
    entry = summary["leaderboard"][0]
    assert entry["verdict"] == "WATCHLIST"       # wf 음수라 강등
    assert entry["bh_survivor"] is True
```

- [ ] **Step 2: 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_autoresearch_engine.py::test_run_batch_uses_classify_for_verdicts -q`
Expected: FAIL — 기존 로직은 wf 무시하고 "CANDIDATE" 반환.

- [ ] **Step 3: 구현 — run_batch verdict 블록 교체**

`research/autoresearch/engine.py` 상단 import에 추가(L28 근처):

```python
from research.scanner.verdict import classify, DISPLAY
```

`run_batch` 내부, 기존 L114-122의 verdict 계산 블록을 교체. 기존:

```python
        rt = review_strategy(res["_spec"], res["evidence"]) if res.get("_spec") else {"verdict": "N/A", "failed": [], "missing": []}
        bh_survivor = bool(survivors[i]) if i < len(survivors) else False
        redteam_ok = rt["verdict"] == "CLEARED"
        if bh_survivor and redteam_ok:
            verdict = "CANDIDATE"
        elif not bh_survivor:
            verdict = "REJECT_BH"        # 배치 다중검정서 탈락(우연 가능)
        else:
            verdict = "REJECT_REDTEAM"   # BH는 넘었지만 통제 실패(confound 등)
```

교체 후:

```python
        rt = review_strategy(res["_spec"], res["evidence"]) if res.get("_spec") else {"verdict": "N/A", "failed": [], "missing": []}
        bh_survivor = bool(survivors[i]) if i < len(survivors) else False
        status, _text = classify(
            net=res.get("net"), percentile=res.get("percentile"), p=res.get("p"),
            wf_first=res.get("wf_first"), wf_second=res.get("wf_second"),
            redteam_verdict=rt["verdict"], bh_survivor=bh_survivor)
        verdict = DISPLAY.get(status, status.upper())
```

그리고 `log_experiment` 호출부(기존 L137)의 `"status": "candidate" if verdict == "CANDIDATE" else "rejected"`는 그대로 두되, watchlist도 후보로 남기려면 아래로 교체:

```python
            "status": "candidate" if status == "candidate" else ("watchlist" if status == "watchlist" else "rejected"),
```

정렬 order(기존 L145)에 watchlist 반영:

```python
    order = {"CANDIDATE": 0, "WATCHLIST": 1, "REJECT_REDTEAM": 2, "REJECT_BH": 3}
```

- [ ] **Step 4: 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_autoresearch_engine.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add research/autoresearch/engine.py tests/test_autoresearch_engine.py
git commit -m "refactor: autoresearch run_batch가 classify() 사용 + wf 강건성 게이트

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: LAB `evaluate_real_event`가 `classify()` + 배치 되먹임 사용

**Files:**
- Modify: `research/lab/evaluator.py` (`evaluate_real_event` 하단 verdict 블록 L148-159 근방)
- Test: `tests/test_lab_pipeline.py` (evaluator 섹션에 추가)

**Interfaces:**
- Consumes: `research.scanner.verdict.classify` (Task 1), `research.autoresearch.engine.latest_bh_survivor` (Task 2).
- Produces: `evaluate_real_event(h)` 반환 dict의 `status`가 canonical 값(`candidate`/`watchlist`/`pending_bh`/`reject_bh`/`reject_redteam`/`reject_stats`). 배치 미확정 family는 `pending_bh`. `redteam`/`redteam_failed` 키 유지.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_lab_pipeline.py`의 evaluator 섹션(`test_underpowered_flag` 아래)에 추가:

```python
def test_real_event_pending_when_no_batch(monkeypatch):
    """배치 미확정(bh_survivor=None) + 강한 통계 → pending_bh(candidate 도장 보류)."""
    from research.lab import evaluator as ev
    from research.lab.hypotheses import Hypothesis

    monkeypatch.setattr(ev, "load_events_for_test", None, raising=False)
    # event_study·load_series·load_events·redteam·bh를 가짜로 대체
    monkeypatch.setattr(ev, "_lab_bh_survivor", lambda fam_id: None, raising=False)

    h = Hypothesis(id="real_x", name="x", family="event", market="KR", thesis="t", kill="k",
                   entry="", hold="", universe="", cost_bps=40.0, data_mode="real_event",
                   precomputed_id="buyback")

    import research.data.kr_dart_events as kde
    import research.scanner.event_study as es
    import research.scanner.families as fam
    import jarvis.redteam.review as rv
    monkeypatch.setattr(kde, "load_events", lambda fid: [{}] * 100)
    monkeypatch.setattr(es, "load_series", lambda: {"X": {}})
    monkeypatch.setattr(es, "event_study", lambda ev_, s_, d_: {
        "n": 100, "net": 5.0, "median": 0.1, "percentile": 99.0, "p": 0.001,
        "wf_first": 1.0, "wf_second": 1.0, "top_tail_share": 0.2, "evidence": {}, "verdict": "OK"})
    monkeypatch.setattr(fam, "FAMILIES", {"buyback": {"direction": "bullish", "thesis": "t"}})
    monkeypatch.setattr(fam, "redteam_spec", lambda fid, f: {"required": []})
    monkeypatch.setattr(rv, "review_strategy", lambda spec, evid: {"verdict": "CLEARED", "failed": []})

    r = ev.evaluate_real_event(h)
    assert r["status"] == "pending_bh"


def test_real_event_candidate_when_bh_survivor(monkeypatch):
    """배치 확정 생존(bh_survivor=True) + 레드팀 CLEARED + robust → candidate."""
    from research.lab import evaluator as ev
    from research.lab.hypotheses import Hypothesis
    import research.data.kr_dart_events as kde
    import research.scanner.event_study as es
    import research.scanner.families as fam
    import jarvis.redteam.review as rv

    monkeypatch.setattr(ev, "_lab_bh_survivor", lambda fam_id: True, raising=False)
    monkeypatch.setattr(kde, "load_events", lambda fid: [{}] * 100)
    monkeypatch.setattr(es, "load_series", lambda: {"X": {}})
    monkeypatch.setattr(es, "event_study", lambda ev_, s_, d_: {
        "n": 100, "net": 5.0, "median": 0.1, "percentile": 99.0, "p": 0.001,
        "wf_first": 1.0, "wf_second": 1.0, "top_tail_share": 0.2, "evidence": {}, "verdict": "OK"})
    monkeypatch.setattr(fam, "FAMILIES", {"buyback": {"direction": "bullish", "thesis": "t"}})
    monkeypatch.setattr(fam, "redteam_spec", lambda fid, f: {"required": []})
    monkeypatch.setattr(rv, "review_strategy", lambda spec, evid: {"verdict": "CLEARED", "failed": []})

    h = Hypothesis(id="real_x", name="x", family="event", market="KR", thesis="t", kill="k",
                   entry="", hold="", universe="", cost_bps=40.0, data_mode="real_event",
                   precomputed_id="buyback")
    r = ev.evaluate_real_event(h)
    assert r["status"] == "candidate"
```

- [ ] **Step 2: 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_pipeline.py::test_real_event_pending_when_no_batch tests/test_lab_pipeline.py::test_real_event_candidate_when_bh_survivor -q`
Expected: FAIL — 현재 `evaluate_real_event`는 `candidate_real`/`watchlist_real`를 반환하고 `_lab_bh_survivor` 없음.

- [ ] **Step 3: 구현 — evaluate_real_event verdict 블록 교체**

`research/lab/evaluator.py`, `evaluate_real_event` 함수 내부. 기존 import 블록(함수 상단)에 추가:

```python
    from research.scanner.verdict import classify
```

그리고 배치 되먹임 헬퍼를 모듈 레벨에 추가(파일 상단, `evaluate` 함수 위):

```python
def _lab_bh_survivor(fam_id: str) -> bool | None:
    """최신 Auto-Research 배치서 이 family의 BH-FDR 생존 여부. 미확정이면 None.
    (테스트에서 monkeypatch 가능하도록 얇은 래퍼)."""
    try:
        from research.autoresearch.engine import latest_bh_survivor
        return latest_bh_survivor(fam_id)
    except Exception:  # noqa: BLE001
        return None
```

`evaluate_real_event` 내부 기존 verdict 블록(L148-159):

```python
    rt = review_strategy(redteam_spec(fam_id, fam), res["evidence"])
    net, pct, p = res["net"], res["percentile"], res["p"]
    wf1, wf2 = res["wf_first"], res["wf_second"]
    redteam_ok = rt["verdict"] == "CLEARED"
    if not redteam_ok:
        status, verdict = "reject_real", f"REJECT — 레드팀 통제 실패: {','.join(rt.get('failed', []))}"
    elif net > 0 and (pct or 0) >= 95 and (p or 1) < 0.05 and wf1 > 0 and wf2 > 0:
        status, verdict = "candidate_real", "CANDIDATE — random·비용·WF·레드팀 전부 통과 (실데이터)"
    elif net > 0 and (pct or 0) >= 80:
        status, verdict = "watchlist_real", f"WATCHLIST — 양수·pct {pct}, 확신 부족(옐로)"
    else:
        status, verdict = "reject_real", "REJECT — 매칭 random·비용 못 넘음"
```

교체 후:

```python
    rt = review_strategy(redteam_spec(fam_id, fam), res["evidence"])
    net, pct, p = res["net"], res["percentile"], res["p"]
    wf1, wf2 = res["wf_first"], res["wf_second"]
    bh_survivor = _lab_bh_survivor(fam_id)   # 배치 되먹임: 확정 True/False, 미확정 None
    status, verdict = classify(
        net=net, percentile=pct, p=p, wf_first=wf1, wf_second=wf2,
        redteam_verdict=rt["verdict"], bh_survivor=bh_survivor)
```

- [ ] **Step 4: 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_pipeline.py -q`
Expected: PASS (기존 lab 테스트 + 신규 2개 모두 통과)

- [ ] **Step 5: 커밋**

```bash
git add research/lab/evaluator.py tests/test_lab_pipeline.py
git commit -m "feat: lab evaluate_real_event가 classify() + 배치 BH 되먹임 → pending_bh/candidate

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: LAB 파이프라인 `_finish`가 `pending_bh` 버킷 처리

**Files:**
- Modify: `research/lab/pipeline.py` (`_finish` L174-209, stats 초기화 L40)
- Test: `tests/test_lab_pipeline.py`

**Interfaces:**
- Consumes: canonical status(`pending_bh` 등) from Task 4.
- Produces: `stats` dict에 `"pending"` 키 추가. `pending_bh` status는 reject로 세지 않고 pending 버킷 + edge 표시(양성). snapshot의 `stats`는 `{processed, edges, rejects, blocked, pending}`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_lab_pipeline.py` pipeline 섹션에 추가:

```python
def test_pending_bh_counts_as_pending_not_reject(monkeypatch):
    monkeypatch.setattr(pl.time, "sleep", lambda *a, **k: None)
    eng = pl.LabEngine()
    # evaluate를 가짜로: pending_bh 결과 반환
    fake = {"data_mode": "real_event", "status": "pending_bh",
            "verdict": "PENDING — 배치 대기", "powered": True,
            "audit": {"ok": True, "note": "n", "n_bars": 100, "events": 100},
            "backtest": {"strategy_net": 5.0, "n_trades": 100, "cost_bps": 40.0},
            "random": {"percentile": 99.0, "p_value": 0.001, "random_median": 0.0, "n_runs": "perm"},
            "walk_forward": {"first": 1.0, "second": 1.0, "both_positive": True}}
    monkeypatch.setattr(pl, "evaluate", lambda h: fake)
    _seed_fast(eng, [_hb("plumb_pending")])
    eng.start(hid="plumb_pending")
    _drain(eng)
    assert eng.stats["pending"] == 1
    assert eng.stats["rejects"] == 0
```

- [ ] **Step 2: 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_pipeline.py::test_pending_bh_counts_as_pending_not_reject -q`
Expected: FAIL — `KeyError: 'pending'` (stats에 pending 키 없음).

- [ ] **Step 3: 구현**

`research/lab/pipeline.py` L40 stats 초기화:

```python
        self.stats = {"processed": 0, "edges": 0, "rejects": 0, "blocked": 0, "pending": 0}
```

`_finish` 내부 stats 분류(L195-200)를 교체. 기존:

```python
            self.stats["processed"] += 1
            if status.startswith(("watchlist", "candidate", "paper")):
                self.stats["edges"] += 1
            elif status.startswith("blocked"):
                self.stats["blocked"] += 1
            else:
                self.stats["rejects"] += 1
```

교체 후:

```python
            self.stats["processed"] += 1
            if status == "pending_bh":
                self.stats["pending"] += 1
            elif status.startswith(("watchlist", "candidate", "paper")):
                self.stats["edges"] += 1
            elif status.startswith("blocked"):
                self.stats["blocked"] += 1
            else:
                self.stats["rejects"] += 1
```

또한 `_finish` 상단 EXECUTE 로그 색상(L178-180)의 pos 조건에 pending 반영:

```python
        self._log_line("execute", f"판정: {res['verdict']}",
                       "pos" if status.startswith(("watchlist", "candidate", "paper")) else
                       "accent" if status == "pending_bh" else
                       "warn" if status.startswith("blocked") else "neg")
```

- [ ] **Step 4: 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_pipeline.py -q`
Expected: PASS (전체 lab 테스트 통과)

- [ ] **Step 5: 커밋**

```bash
git add research/lab/pipeline.py tests/test_lab_pipeline.py
git commit -m "feat: lab 파이프라인 pending_bh 버킷 — 배치 대기는 reject 아님

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: 프론트 — LAB 페이지 `pending_bh` 표시

**Files:**
- Modify: `seokminal-dashboard/app/lab/page.tsx` (`verdictStyle` L28-30, StatsBar 표시 L474-485 근방)

**Interfaces:**
- Consumes: 백엔드 snapshot의 canonical status(`pending_bh`) + `stats.pending`(Task 5).
- Produces: pending_bh verdict 칩 = info 톤 + "배치 대기" 의미. StatsBar에 pending 카운트.

- [ ] **Step 1: verdictStyle에 pending 처리 추가**

`seokminal-dashboard/app/lab/page.tsx` `verdictStyle` 교체. 기존:

```tsx
function verdictStyle(s: string): string {
  if (s.startsWith("watchlist") || s.startsWith("candidate") || s.startsWith("paper")) return "border-pos/40 text-pos bg-pos/10";
```

교체 후(첫 줄 뒤에 pending 분기 추가):

```tsx
function verdictStyle(s: string): string {
  if (s === "pending_bh") return "border-info/40 text-info bg-info/10";
  if (s.startsWith("watchlist") || s.startsWith("candidate") || s.startsWith("paper")) return "border-pos/40 text-pos bg-pos/10";
```

(기존 나머지 줄 유지)

- [ ] **Step 2: StatsBar에 pending 카운트 추가**

`seokminal-dashboard/app/lab/page.tsx` StatsBar(L474 근방). 기존:

```tsx
  const s = st?.stats ?? { processed: 0, edges: 0, rejects: 0, blocked: 0 };
```

교체:

```tsx
  const s = st?.stats ?? { processed: 0, edges: 0, rejects: 0, blocked: 0, pending: 0 };
```

그리고 item 목록(L485 `{item("기각", s.rejects, "text-neg")}` 근처)에 pending 추가:

```tsx
      {item("배치대기", s.pending ?? 0, "text-info")}
```

lib/api.ts의 `LabState`/stats 타입에 `pending?: number` 추가(있는 경우). 없으면 스킵.

- [ ] **Step 3: 타입체크**

Run: `cd seokminal-dashboard && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 4: 커밋**

```bash
git add seokminal-dashboard/app/lab/page.tsx seokminal-dashboard/lib/api.ts
git commit -m "feat: lab UI pending_bh 표시(info 톤 + 배치대기 카운트)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: 전체 회귀 검증 + progress.md 기록

**Files:**
- Modify: `seokminal-dashboard/docs/progress.md`
- Modify: `/Users/seokhun/.claude/projects/-Users-seokhun-Desktop-claude-test-seokminal/memory/` (해당 메모리 갱신, 선택)

- [ ] **Step 1: 백엔드 전체 스위트**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: `X passed, 4 failed` — 실패는 정확히 `test_auth`×3 + `test_backtest_happy_path`만. 그 외 실패 있으면 STOP·수정.

- [ ] **Step 2: 프론트 타입체크**

Run: `cd seokminal-dashboard && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 3: 통합 스모크 — lab이 배치 결과 되먹임하는지 수동 확인**

Run:
```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "
from research.scanner.verdict import classify
print('pending:', classify(net=5,percentile=99,p=0.01,wf_first=1,wf_second=1,redteam_verdict='CLEARED',bh_survivor=None)[0])
print('candidate:', classify(net=5,percentile=99,p=0.01,wf_first=1,wf_second=1,redteam_verdict='CLEARED',bh_survivor=True)[0])
print('reject_bh:', classify(net=5,percentile=99,p=0.01,wf_first=1,wf_second=1,redteam_verdict='CLEARED',bh_survivor=False)[0])
"
```
Expected: `pending: pending_bh` / `candidate: candidate` / `reject_bh: reject_bh`.

- [ ] **Step 4: progress.md에 Phase 129 기록**

`seokminal-dashboard/docs/progress.md` 최상단에 추가:

```markdown
## Phase 129 — LAB↔Auto-Research 판정 통합(단일 진실원 + 배치 되먹임) (2026-07-03) ✅ SHIPPED

판정 로직 두 벌 → `classify()` 한 벌. lab이 배치 BH 되먹임.
- `research/scanner/verdict.py` classify() 신설 — 두 시스템 유일 진실원. candidate = bh_survivor+레드팀 CLEARED+net>0+wf 양쪽 양수(양 강점 결합).
- `autoresearch.latest_bh_survivor(fam_id)` — 최신 배치 리더보드 리더.
- autoresearch run_batch → classify 사용(verdict 대문자 유지, FE 무변경). **wf 강건성 게이트 신규 적용.**
- lab evaluate_real_event → classify + `_lab_bh_survivor` 되먹임. 배치 미확정 = `pending_bh`(candidate 도장 보류 = 통계적 정직). 확정 생존 = candidate.
- lab 파이프라인 pending 버킷 + UI info 톤.
- 테스트: verdict 8 + autoresearch 4 + lab pending/candidate 3 신규. 전체 회귀 0.

### 미결
- 진짜 되먹임 순환 완성: service가 배치 후 lab 재평가 트리거(지금은 lab이 배치 status.json 읽기만 = pull).
```

- [ ] **Step 5: 커밋**

```bash
git add seokminal-dashboard/docs/progress.md
git commit -m "docs: Phase 129 판정 통합 기록

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review 노트

- **Spec coverage:** 단일 classify(Task1) ✓ / 배치 되먹임 리더(Task2) ✓ / autoresearch 통합(Task3) ✓ / lab 통합+pending(Task4) ✓ / 파이프라인 버킷(Task5) ✓ / UI(Task6) ✓ / 검증(Task7) ✓.
- **Type 일관성:** classify 시그니처(keyword-only, `bh_survivor: bool|None`)를 Task3·4에서 동일 호출. status 문자열 canonical 집합 6종을 verdict.py 상수로 고정, DISPLAY 매핑으로 FE 대문자 호환.
- **알려진 동작 변화(의도):** autoresearch candidate에 wf 게이트 신규 적용 → 기존 배치는 candidate 0이라 실질 회귀 없음, 게이트만 엄격해짐. 문서화 완료.
- **순환 import 확인:** lab → autoresearch(latest_bh_survivor) 단방향. autoresearch는 lab import 안 함. verdict.py는 scanner(양쪽이 이미 의존)에 위치.
