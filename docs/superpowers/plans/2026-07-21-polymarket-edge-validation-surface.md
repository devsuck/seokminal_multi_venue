# Polymarket 엣지 검증 노출 — Implementation Plan

> 스펙: `docs/superpowers/specs/2026-07-21-polymarket-edge-validation-surface-design.md` (승인됨).

**Goal:** sharp-wallet / whale validate 러너의 p-value·BH-FDR 결과를 대시보드에서
읽기 전용으로 볼 수 있게 한다. 계산-프린트 분리 리팩터 + 백그라운드-웜 캐시 엔드포인트
+ `/validation` 페이지 섹션.

**Architecture:** 각 validate 러너에 순수 `compute_report(trades, dates) -> dict`와
disk-loading `load_and_report() -> dict` 추가, `main()`은 후자를 호출해 프린트(CLI 불변).
`lab_api.py`에 모듈 캐시 + `GET /lab/edge-validation` + `POST /lab/edge-validation/refresh`
(`_task_forward` 백그라운드-웜 선례). 프론트 `getEdgeValidation`/`refreshEdgeValidation`
+ `/validation` 섹션.

**Tech Stack:** Python 3.11+, pandas, pytest(`--noconftest`로 순수 검증), Next.js/TS.

## Global Constraints
- 신규 통계 계산 없음 — 기존 `run_bucket`/`run_score_tercile`/`run_family`/`benjamini_hochberg`
  재사용. `compute_report`는 이들을 호출해 dict로 담기만.
- 기존 `main()` CLI 출력은 크래시 없이 유지(`test_main_*` 회귀 없음). 출력은 report dict에서 생성(DRY).
- 엔드포인트는 절대 블록 안 함 — 캐시 스냅샷 즉시 반환, stale시 백그라운드 스레드 워밍.
- report dict 공통 스키마(스펙 §3.1): `{hypothesis, cost_bps, dates, n_anchors, groups[], pools[], verdict}`.
  `verdict` = pools의 n_survivors 합 >0 이면 `"candidate"`, ==0 이면 `"no_edge"`, anchors 0 이면 `"no_data"`.
- BH-FDR 풀은 축별 분리 유지(sharp-wallet: bucket / score_tercile 2풀, whale: 1풀). 섞지 않음.

---

### Task 1: `compute_report()` 추출 (두 러너) + 테스트

**Files:**
- Modify: `research/run_polymarket_sharp_wallet_validate.py` (compute_report/load_and_report 추가, main 리라이트)
- Modify: `research/run_polymarket_whale_validate.py` (동일)
- Test: `tests/test_run_polymarket_sharp_wallet_validate.py`, `tests/test_run_polymarket_whale_validate.py` (append)

**공통 헬퍼(각 파일 내):**
```python
def _group_to_dict(gname: str, r: dict) -> tuple[dict, list[float], list[str]]:
    if r["blocked"]:
        return {"group": gname, "blocked": True, "reason": r.get("reason", "")}, [], []
    horizons, pvals, keys = [], [], []
    for hk, hv in r["horizons"].items():
        horizons.append({"horizon": hk, "n_events": hv["n_events"],
                         "total_pnl": hv["strategy"]["total_pnl"],
                         "p_value": hv["random"]["p_value"], "percentile": hv["random"]["percentile"]})
        pvals.append(hv["random"]["p_value"]); keys.append(f"{gname}:{hk}")
    return {"group": gname, "blocked": False, "horizons": horizons}, pvals, keys

def _pool_dict(name: str, pvals: list[float], keys: list[str]) -> dict:
    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1}
    survivors = [k for k, s in zip(keys, bh["survivors"]) if s]
    return {"name": name, "alpha": bh["alpha"], "n_tested": len(pvals),
            "n_survivors": bh["n_survivors"], "survivors": survivors, "threshold": bh.get("threshold")}
```

**sharp-wallet `compute_report(trades, dates)`:** anchors 비면 `verdict:"no_data"` 조기반환.
아니면 build_convergence_score → price_by_condition → build_labels_multi_horizon → add_score_tercile,
bucket 3개(`_group_to_dict(f"bucket{b}", run_bucket(b, labels))`) → `_pool_dict("bucket", ...)`,
tercile 3개(`run_score_tercile`) → `_pool_dict("score_tercile", ...)`. verdict = survivors 합 기준.

**whale `compute_report(trades, dates)`:** family loop(`run_family`) → 1개 `_pool_dict("whale", ...)`.
`build_convergence_count` 없음 — n_anchors 대신 `n_events` 총합 또는 스파이크 수. whale은 anchor 개념이
family별 스파이크라, `n_anchors`를 "총 라벨 수"로 기록(0이면 no_data).

**`load_and_report()`(양쪽):** `_available_dates()` + `load_*_trades()` → `compute_report(trades, dates)`.
**`main()`(양쪽):** `rep = load_and_report()` 후 rep에서 프린트(기존과 유사 포맷).

**Tests (append, `--noconftest`로 실행):**
- sharp-wallet: `compute_report`가 빈 trades→`verdict:"no_data"`, groups/pools 빈; 합성 라벨링 가능한
  trades로 2풀 존재(name "bucket"/"score_tercile") + 스키마 키 검증; verdict "no_edge"(생존자 0 합성).
- whale: 빈→no_data; 합성 스파이크로 1풀("whale") + verdict.
- 기존 `test_main_*`·`run_bucket`/`run_score_tercile`/`run_family` 테스트 전부 통과(회귀 없음).

- [ ] Step 1: 실패 테스트 작성 → Step 2: 실패 확인(`--noconftest`) → Step 3: 구현 → Step 4: 통과 → Step 5: 커밋

---

### Task 2: `lab_api.py` 캐시 + 엔드포인트

**Files:** Modify `api_server/lab_api.py`

**추가:**
```python
_EDGE_VAL_RUNNERS = {
    "polymarket_sharp_wallet": "research.run_polymarket_sharp_wallet_validate",
    "polymarket_whale": "research.run_polymarket_whale_validate",
}
_edge_val_cache: dict = {"ts": 0.0, "reports": {}, "warming": False}
_EDGE_VAL_TTL_S = 600

def _warm_edge_validation() -> None:
    import importlib, time
    try:
        for hyp, mod_path in _EDGE_VAL_RUNNERS.items():
            try:
                mod = importlib.import_module(mod_path)
                _edge_val_cache["reports"][hyp] = mod.load_and_report()
            except Exception as exc:  # noqa: BLE001
                _edge_val_cache["reports"][hyp] = {"hypothesis": hyp, "error": str(exc)[:200]}
    finally:
        _edge_val_cache["ts"] = time.time(); _edge_val_cache["warming"] = False

def _maybe_warm_edge(force: bool = False) -> None:
    import threading, time
    if _edge_val_cache["warming"]:
        return
    stale = (time.time() - _edge_val_cache["ts"]) > _EDGE_VAL_TTL_S
    if force or stale or not _edge_val_cache["reports"]:
        _edge_val_cache["warming"] = True
        threading.Thread(target=_warm_edge_validation, daemon=True).start()

@router.get("/edge-validation")
def edge_validation() -> dict:
    """폴리마켓 엣지 검증(p-value/BH-FDR) 스냅샷 — 읽기전용. stale시 백그라운드 워밍(요청 비블록)."""
    import time
    _maybe_warm_edge()
    return {"reports": _edge_val_cache["reports"], "ts": _edge_val_cache["ts"],
            "warming": _edge_val_cache["warming"],
            "age_sec": round(time.time() - _edge_val_cache["ts"], 1) if _edge_val_cache["ts"] else None}

@router.post("/edge-validation/refresh")
def edge_validation_refresh() -> dict:
    _maybe_warm_edge(force=True)
    return {"warming": True}
```
- [ ] py_compile 검증(런타임은 맥 스모크). 커밋.

---

### Task 3: 프론트 `/validation` 섹션

**Files:** Modify `seokminal-dashboard/lib/api.ts`, `seokminal-dashboard/app/validation/page.tsx`

**api.ts:** 타입(`EdgeValidationReport`/`EdgeGroup`/`EdgePool`/`EdgeValidationResponse`) + `getEdgeValidation()`
+ `refreshEdgeValidation()`.

**page.tsx:** experiment-registry 섹션 아래 "Polymarket 엣지 검증" 섹션:
- 상시 배너: "스크리닝 결과일 뿐 실집행 근거 아님. walk-forward 생략, 표본 미달."
- 가설별 카드: 커버리지(dates, n_anchors — 작으면 경고), p-value 테이블(group×horizon: n_events/total_pnl/
  p_value/percentile, BLOCKED는 사유), BH-FDR 풀 요약(`n_survivors/n_tested`, 생존자 리스트,
  **0이면 "확인된 엣지 없음(정직한 결과)" 명시**), "지금 다시 계산" 버튼(refresh, warming 스피너).
- 블룸버그 톤: 기존 Panel/PanelHeader/토큰 재사용.
- [ ] `npx tsc --noEmit` 클린. 커밋.

---

### Task 4: 맥 런타임 스모크(유저)
- `curl localhost:8000/lab/edge-validation` (첫 호출 warming:true → 잠시 후 reports 채워짐)
- `/validation` 페이지 하단 섹션 렌더 확인.

## Self-Review Notes
- Spec §3.1 스키마 ↔ Task 1 compute_report 반환 ↔ Task 3 타입 일치.
- 신규 통계 없음(재사용). CLI 불변(main은 report에서 프린트). 엔드포인트 비블록(스레드 워밍).
- 검증경계: Task 1 `--noconftest`로 완전검증, Task 3 tsc, Task 2 compile-only(맥 스모크).
