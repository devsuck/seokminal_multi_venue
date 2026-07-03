# S1 이벤트 family 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 경제적 근거 있는 새 이벤트 family 4개(treasury_disposal·control_change·asset_transfer·rights_issue)를 사전등록해 검증 파이프(event_study → BH-FDR → 레드팀 → classify)에 태우고 정직하게 판정한다.

**Architecture:** `autoresearch.run_batch()`가 이미 `FAMILIES` 전체를 순회한다. FAMILIES에 4개를 추가하면 배치·BH-FDR·레드팀·registry·lab reconcile·UI가 전부 자동 편입. 신규 코드는 (1) family 정의 + 키워드 필터 테스트, (2) 배치 편입 결정적 테스트, (3) 실 DART pull + 정직한 커버리지·판정 기록뿐이다.

**Tech Stack:** Python 3.14, pytest(asyncio_mode="auto"), OpenDART API, KRX PIT series.

## Global Constraints

- Python 인터프리터: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3` (정확히 이 경로).
- 테스트: `@pytest.mark.asyncio` **절대 금지**(asyncio_mode="auto").
- pre-existing 실패 4건 무시: `test_auth.py`×3, `test_backtest_happy_path`. 그 외 실패 0.
- 브랜치: main 직접 커밋.
- 커밋 메시지 Co-Authored-By: `Claude <noreply@anthropic.com>` (모델명·context 모드 정보 금지).
- **사전등록·동결:** 4 family 키워드·exclude·방향·비용(40bps)·보유(20거래일)는 고정. 결과 본 뒤 튜닝 금지.
- **BH-FDR 규율:** family 4개로 제한(더 넣으면 다중검정 임계 빡세짐). 죽은연못 자동생성 금지.
- **정직성:** 커버리지 n<30 = UNDERPOWERED로 표기(억지 판정 금지). 전부 REJECT여도 유효 결과.
- 4 family 확정 스펙(spec에서 verbatim):
  - `treasury_disposal`: keywords `[자기주식처분]` exclude `[취득]` pblntf_ty `B` direction `bearish`
  - `control_change`: keywords `[최대주주변경, 경영권]` exclude `[]` pblntf_ty `B` direction `bullish`
  - `asset_transfer`: keywords `[자산양수도, 영업양수도]` exclude `[]` pblntf_ty `B` direction `research`
  - `rights_issue`: keywords `[유상증자]` exclude `[무상]` pblntf_ty `B` direction `bearish`

---

## File Structure

- **Modify** `research/data/kr_dart_events.py` — `report_matches(nm, include, exclude)` 순수 predicate 추출 + `_fetch_window`가 그것을 사용하도록 리팩터(키워드 필터를 테스트 가능하게).
- **Modify** `research/scanner/families.py` — `FAMILIES`에 4 family 추가.
- **Create** `tests/test_event_families_s1.py` — report_matches predicate 테스트 + 4 family 스키마 테스트 + 배치 편입(engine `_event_family_candidates`) 결정적 테스트.
- **Create** `docs/superpowers/results/2026-07-03-s1-coverage-verdicts.md` — 실 pull 커버리지 + 배치 판정 정직 기록(Task 3).

---

## Task 1: 키워드 필터 predicate 추출 + 4 family 정의

**Files:**
- Modify: `research/data/kr_dart_events.py` (`_fetch_window` 내부 필터 L61 근방 + 신규 predicate)
- Modify: `research/scanner/families.py` (`FAMILIES` dict)
- Test: `tests/test_event_families_s1.py`

**Interfaces:**
- Produces:
  - `report_matches(nm: str, include: list[str], exclude: list[str]) -> bool` in `research/data/kr_dart_events.py` — include 중 하나라도 nm에 있고 exclude는 하나도 없으면 True.
  - `FAMILIES` dict에 키 `treasury_disposal`·`control_change`·`asset_transfer`·`rights_issue` 추가. 각 값 = `{"keywords": [...], "exclude": [...], "direction": ..., "pblntf_ty": "B", "event_type": None, "thesis": "..."}`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_event_families_s1.py`:

```python
"""S1 이벤트 family 확장 — 키워드 필터 predicate + family 스키마 + 배치 편입."""
from __future__ import annotations

from research.data.kr_dart_events import report_matches
from research.scanner.families import FAMILIES

S1_FAMILIES = ["treasury_disposal", "control_change", "asset_transfer", "rights_issue"]


# ── report_matches predicate ──────────────────────────────────
def test_report_matches_include_hit():
    assert report_matches("자기주식처분결정", ["자기주식처분"], ["취득"]) is True


def test_report_matches_exclude_blocks():
    # 취득 공시는 처분 family에서 제외
    assert report_matches("자기주식취득결정", ["자기주식처분"], ["취득"]) is False


def test_report_matches_rights_excludes_bonus():
    assert report_matches("유상증자결정", ["유상증자"], ["무상"]) is True
    assert report_matches("무상증자결정", ["유상증자"], ["무상"]) is False


def test_report_matches_no_include_is_false():
    assert report_matches("배당결정", ["유상증자"], []) is False


# ── FAMILIES 스키마 ───────────────────────────────────────────
def test_s1_families_present():
    for fid in S1_FAMILIES:
        assert fid in FAMILIES, f"{fid} 누락"


def test_s1_families_schema():
    expected = {
        "treasury_disposal": ("bearish", ["자기주식처분"], ["취득"]),
        "control_change": ("bullish", ["최대주주변경", "경영권"], []),
        "asset_transfer": ("research", ["자산양수도", "영업양수도"], []),
        "rights_issue": ("bearish", ["유상증자"], ["무상"]),
    }
    for fid, (direction, kw, ex) in expected.items():
        fam = FAMILIES[fid]
        assert fam["direction"] == direction
        assert fam["keywords"] == kw
        assert fam["exclude"] == ex
        assert fam.get("pblntf_ty") == "B"
        assert fam.get("thesis")
```

- [ ] **Step 2: 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_event_families_s1.py -q`
Expected: FAIL — `ImportError: cannot import name 'report_matches'` (그리고 FAMILIES 키 없음).

- [ ] **Step 3: report_matches 추출 + _fetch_window 리팩터**

`research/data/kr_dart_events.py`, `EVENT_DEFS` 정의 아래(L40 근방)에 추가:

```python
def report_matches(nm: str, include: list[str], exclude: list[str]) -> bool:
    """report_nm이 include 중 하나 포함 && exclude 전무 → True."""
    return any(k in nm for k in include) and not any(k in nm for k in exclude)
```

그리고 `_fetch_window` 내부 기존 필터(L61):

```python
            if not sc or not any(k in nm for k in d["include"]) or any(k in nm for k in d["exclude"]):
                continue
```

교체:

```python
            if not sc or not report_matches(nm, d["include"], d["exclude"]):
                continue
```

- [ ] **Step 4: FAMILIES에 4 family 추가**

`research/scanner/families.py`, `FAMILIES` dict의 `treasury_trust` 항목 뒤(닫는 `}` 앞)에 추가:

```python
    # ── S1 확장(사전등록·동결) ──────────────────────────────
    "treasury_disposal": {"keywords": ["자기주식처분"], "exclude": ["취득"], "direction": "bearish", "pblntf_ty": "B",
                          "event_type": None, "thesis": "자사주 처분=공급↑(buyback 거울, 공급/수요 방향축 확증)"},
    "control_change": {"keywords": ["최대주주변경", "경영권"], "exclude": [], "direction": "bullish", "pblntf_ty": "B",
                       "event_type": None, "thesis": "최대주주 변경=인수/경영권 프리미엄 기대"},
    "asset_transfer": {"keywords": ["자산양수도", "영업양수도"], "exclude": [], "direction": "research", "pblntf_ty": "B",
                       "event_type": None, "thesis": "자산·영업 양수도=구조조정 재평가(방향 불명 → research)"},
    "rights_issue": {"keywords": ["유상증자"], "exclude": ["무상"], "direction": "bearish", "pblntf_ty": "B",
                     "event_type": None, "thesis": "유상증자=신주 희석 악재(회피신호 확증)"},
```

- [ ] **Step 5: 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_event_families_s1.py -q`
Expected: PASS (7 passed).

- [ ] **Step 6: 전체 회귀 (필터 리팩터가 기존 pull 안 깨는지)**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: `X passed, 4 failed` — 실패는 정확히 pre-existing 4건(test_auth×3 + backtest_happy)만.

- [ ] **Step 7: 커밋**

```bash
git add research/data/kr_dart_events.py research/scanner/families.py tests/test_event_families_s1.py
git commit -m "feat: S1 이벤트 family 4개 추가(자사주처분·최대주주변경·양수도·유상증자) + report_matches predicate

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: 배치 편입 결정적 테스트

**Files:**
- Test: `tests/test_event_families_s1.py` (Task 1 파일에 append)

**Interfaces:**
- Consumes: `research.autoresearch.engine._event_family_candidates(series: dict) -> list[Candidate]` (기존). Candidate에 `.cid`(=`f"ev_{fam_id}"`), `.meta`(dict, 데이터 부족 시 `{"underpowered": True}`).
- Produces: 없음(테스트만).

**참고(기존 코드 동작):** `engine._event_family_candidates`는 `FAMILIES`를 순회하며 각 fam_id에 `load_events(fam_id)`를 호출한다. 이벤트 ≥30이면 실행 가능한 Candidate, <30이면 `meta["underpowered"]=True`인 Candidate를 만든다. 이 태스크는 신규 4 family가 이 경로에 올바로 편입되는지 실데이터 없이(load_events monkeypatch) 검증한다.

- [ ] **Step 1: 실패 테스트 작성 (Task 1 파일 끝에 append)**

```python
# ── 배치 편입 (engine) ────────────────────────────────────────
def test_new_families_enter_batch_when_powered(monkeypatch):
    import research.autoresearch.engine as eng
    # 모든 family에 이벤트 100건 있는 것처럼 → 전부 실행 가능 Candidate
    monkeypatch.setattr(eng, "load_events", lambda fid: [{}] * 100)
    cands = eng._event_family_candidates({"X": {}})
    cids = {c.cid for c in cands}
    for fid in S1_FAMILIES:
        assert f"ev_{fid}" in cids, f"ev_{fid} 배치 미편입"
        c = next(c for c in cands if c.cid == f"ev_{fid}")
        assert not c.meta.get("underpowered")


def test_new_families_underpowered_when_no_data(monkeypatch):
    import research.autoresearch.engine as eng
    monkeypatch.setattr(eng, "load_events", lambda fid: [])   # 커버리지 0
    cands = eng._event_family_candidates({"X": {}})
    for fid in S1_FAMILIES:
        c = next(c for c in cands if c.cid == f"ev_{fid}")
        assert c.meta.get("underpowered") is True
```

- [ ] **Step 2: 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_event_families_s1.py -k batch -q`
Expected: 두 테스트 중 하나 이상 FAIL이면 안 됨 — 실제로는 Task 1에서 FAMILIES에 이미 추가됐으므로 **PASS 가능성 있음**. PASS면 이 태스크는 "회귀 방지 테스트 추가"로 유효(코드 변경 없음). FAIL이면(예: load_events가 engine 네임스페이스에 없음) monkeypatch 대상 경로를 `research.data.kr_dart_events.load_events`로 조정.

> 참고: `engine.py`가 `from research.data.kr_dart_events import load_events`로 가져오면 `eng.load_events` monkeypatch가 맞다. `import ... as` 형태면 실제 참조 경로로 조정. 구현자는 engine.py의 import 라인을 확인해 monkeypatch 대상을 맞춘다.

- [ ] **Step 3: (필요 시) monkeypatch 경로 조정**

`research/autoresearch/engine.py`의 load_events import 형태를 확인:
```bash
grep -n "load_events" research/autoresearch/engine.py
```
`from research.data.kr_dart_events import load_events`(L25)이면 `eng.load_events` 패치가 맞다(코드 변경 불필요). 테스트가 그대로 통과하면 Step 3 스킵.

- [ ] **Step 4: 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_event_families_s1.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: 커밋**

```bash
git add tests/test_event_families_s1.py
git commit -m "test: S1 신규 family 배치 편입 결정적 검증(powered/underpowered)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: 실 DART pull + 커버리지·판정 정직 기록

**Files:**
- Create: `docs/superpowers/results/2026-07-03-s1-coverage-verdicts.md`

**전제:** 이 태스크는 실 OpenDART API를 호출한다. `.env`에 `DART_API_KEY`(또는 코드가 읽는 키)가 있어야 하고, 네트워크·수 분 소요. 실데이터라 CI 단위테스트 불가 — 실행+정직한 기록이 산출물이다.

- [ ] **Step 1: 신규 family 데이터 pull**

Run:
```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
PYTHONPATH=. /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 research/run_scanner.py --pull 2>&1 | tee /tmp/s1_scan.log
```
동작: `run_scanner`가 FAMILIES 전체를 순회하며 캐시 없는 신규 4 family를 EVENT_DEFS에 동적 등록 후 `pull_events(fam_id, years=6.5)`로 pull·저장한다. 기존 family는 캐시 재사용.
Expected: 각 family별 `[fam_id] n=... net=... 레드팀 ...` 또는 `UNDERPOWERED` 라인 출력. 4 신규 family가 로그에 등장해야 함.

- [ ] **Step 2: 커버리지 확인**

Run:
```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
for f in treasury_disposal control_change asset_transfer rights_issue; do
  n=$(/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "from research.data.kr_dart_events import load_events; print(len(load_events('$f')))")
  echo "$f: n=$n"
done
```
Expected: 각 family 이벤트 수. n≥30 = powered, n<30 = UNDERPOWERED(정직 표기). `control_change`는 B피드에 없으면 낮을 수 있음(spec 예상 — 정직한 결과, S3 이관 후보).

- [ ] **Step 3: 배치 실행 → 신규 family 판정 확인**

Run:
```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "
from research.autoresearch.engine import run_batch
s = run_batch()
print('n_tested', s['n_tested'], 'n_candidates', s['n_candidates'], 'BH', s.get('bh_threshold'))
for e in s['leaderboard']:
    print(f\"  {e['cid']:<26} {e['verdict']:<16} bh={e['bh_survivor']} pct={e['percentile']} p={e['p']} redteam={e['redteam']}\")
for u in s.get('underpowered', []):
    print(f\"  {u['cid']:<26} UNDERPOWERED n={u['n']}\")
"
```
Expected: leaderboard에 4 신규 family가 verdict와 함께(또는 underpowered 목록에) 등장. `treasury_disposal`은 bearish 방향이 확증되는지, `rights_issue`는 음드리프트 확증되는지 관찰.

- [ ] **Step 4: 정직한 결과 기록**

`docs/superpowers/results/2026-07-03-s1-coverage-verdicts.md`를 작성. 실제 Step 2·3 출력을 채운다(아래는 형식 — 값은 실측으로 대체):

```markdown
# S1 이벤트 family 확장 — 커버리지 & 판정 (2026-07-03)

## 커버리지 (실 DART pull, 6.5년)
| family | n | powered? |
|---|---|---|
| treasury_disposal | <실측> | <n≥30?> |
| control_change | <실측> | <> |
| asset_transfer | <실측> | <> |
| rights_issue | <실측> | <> |

## 배치 판정 (BH-FDR threshold <실측>)
| family | verdict | bh_survivor | pct | p | redteam |
|---|---|---|---|---|---|
| ev_treasury_disposal | <> | <> | <> | <> | <> |
| ev_control_change | <> | ... |
| ev_asset_transfer | <> | ... |
| ev_rights_issue | <> | ... |

## 판정 요약 (정직)
- 생존(candidate/watchlist): <목록 또는 "없음">
- treasury_disposal 방향 확증: <bearish 드리프트 관찰됐나? buyback 공급/수요 축 검증 결과>
- rights_issue 음드리프트 확증: <>
- UNDERPOWERED(데이터 부족 → S3 이관 후보): <목록>
- 결론: <1개라도 생존이면 S2 forward 후보 / 전부 REJECT면 메커니즘 학습 기록. 튜닝 없음>
```

- [ ] **Step 5: 커밋**

```bash
git add docs/superpowers/results/2026-07-03-s1-coverage-verdicts.md
git commit -m "docs: S1 이벤트 family 커버리지·판정 실측 기록

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review 노트

- **Spec 커버리지:** 4 family 정의(Task1) ✓ / 키워드 필터 테스트(Task1) ✓ / 배치 편입 자동+검증(Task2) ✓ / 커버리지 n≥30 정직 처리(Task3 Step2) ✓ / BH-FDR·레드팀(기존 파이프 재사용, Task3 Step3서 관찰) ✓ / 정직한 성공기준 기록(Task3 Step4) ✓ / rights_issue 기존 EVENT_DEFS 재사용(run_scanner 캐시 우선 로직이 처리) ✓.
- **동결 준수:** 키워드·방향은 Global Constraints에 verbatim, Task1 코드에 고정. 튜닝 스텝 없음.
- **Type 일관성:** `report_matches(nm, include, exclude)` 시그니처 Task1 정의 = Task1 테스트 호출 일치. `_event_family_candidates`/`.cid`/`.meta` Task2에서 기존 engine 시그니처대로 사용.
- **미결 처리:** 실 report_nm 키워드 정합성·control_change 피드 소재는 Task3(실 pull)에서 커버리지로 드러남 — 코드 문제 아니라 데이터 결과. underpowered면 정직 기록 후 S3 이관(계획대로).
- **YAGNI:** 곁가지 UI 정리·S2~S4 미포함. 라이브 집행 없음.
