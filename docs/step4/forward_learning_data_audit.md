# STEP4-A — Forward Learning Data Source Audit

**No code changed in this commit.** Read-only audit of existing data flow, per STEP4-A
instruction: "새로운 schema를 만들지 말고 현재 구조 분석."

## Headline finding

Most of what STEP4-A/B/C ask for **already exists**, built and wired to `console_api`,
but with **zero dashboard consumer**. The Phase1 cleanup (STEP1-3) removed unconnected
placeholder scaffolding named like this work; the real engines were hiding in plain
sight inside the protected `research_workflow` package the whole time. Concretely:

| Ask | Already exists | Wired to console_api | Dashboard UI |
|---|---|---|---|
| STEP4-B Validation Score | `research_workflow/research_validation_score.py` (P205) | `GET /console/data-connection` | none |
| STEP4-C Prediction Coverage | `research_workflow/prediction_coverage_audit.py` (P204.5) | `GET /console/data-connection` | none |
| Batting avg / calibration / edge score / lifecycle | `research_workflow/research_accountability.py` | `GET /console/research-accountability` | none |
| Backtest-vs-paper deep comparison (findings, learning feedback) | `research_workflow/forward_testing.py` (P94) | **not wired** | none |

This changes the shape of the remaining STEP4 work: STEP4-B and STEP4-C are mostly a
**dashboard wiring problem**, not an engine-building problem. STEP4-A's genuine gap is
narrower than it first reads — see "What's actually missing" below.

## STEP4-A Question 1 — Where does strategy lifecycle live?

`jarvis/registry/lifecycle.py` — `StrategyRegistry`, backed by `jarvis/_state/registry.jsonl`
(append-only event log, folded to current state per `strategy_id`).

Full FSM, deterministic, human-approval-gated on the live side:

```
draft → data_audit_passed → backtested → watchlist → paper_candidate
      → paper_candidate_forward_test_required → paper_active
      → live_candidate → micro_live → constrained_live
(rejected is terminal-except-retired; no revival into paper/live)
```

Live counts today (2026-07-31): `draft` 61, `data_audit_passed` 40, `backtested` 40,
`rejected` 35, `blocked_by_data` 6, `watchlist` 5, `paper_candidate` 4, `paper_active` 4.

`config_hash` freezes at `paper_candidate`; further changes require `ADMIN_HUMAN_ONLY`.
This **is** the candidate→paper→forward→approved/rejected flow the question asked
about — it's real, populated, and load-bearing (protected, out of scope for deletion).

## STEP4-A Question 2 — Does thesis/evidence/invalidation data already exist?

Yes, in two places, both pre-existing:

1. **`research/agents/experiment_registry.jsonl`** (3252 rows) — one row per backtest run.
   Carries `hypothesis_id`, `verdict`, `note`, `caveats`, `sharpe`, `p`, `random_percentile`,
   `wf_first_sharpe`/`wf_second_sharpe` (walk-forward), `cost_robust`/`cost_stress`,
   `n_markets`, `status`. This is the "why do we believe this" evidence base — already
   the source `registry.seed_from_experiment_registry()` reads to populate
   `registry.jsonl`'s `evidence` field (`random_pct`, `p`) at the `paper_candidate` transition.

2. **`jarvis/research_workflow/prediction_registry.py`** (P201) — purpose-built for exactly
   this: `capture_prediction(thesis=..., invalidation_condition=..., evidence_used=...,
   expected_horizon=..., confidence=...)`. Pre-registers belief *before* grading (blocks
   post-hoc bias), freezes `evaluation_framework`/`success_rule` at capture time, scores
   into `RIGHT`/`WRONG`/`INVALIDATED`/`INCONCLUSIVE` (`INVALIDATED` = prior risk
   management working, not failure). Persists through the existing `rmi_` ledger
   (`research_memory_intelligence`) — **no new store**, per its own P201 constraint #7.

   Live state today: **5 predictions captured, all source=committee, all pending
   (0 evaluated), 100% missing `expected_horizon`.** `research_capture.py` (P201-ops) is
   the runbook that walks `paper_active`/`watchlist`/`paper_candidate` strategies into
   this registry — it exists but is thin on real usage so far.

Per-strategy forward-vs-backtest comparison (the "does current behavior match thesis"
question) also already exists as **`jarvis/research_workflow/forward_testing.py`**
(P94): `analyze(backtest, paper)` returns performance gap, slippage/cost-assumption
error, regime mismatch, data-leakage suspicion, and a `learning_feedback` string. It
reuses `PaperTradingFeedback.compare` (P63) and writes learning back to the same `rmi_`
ledger via `record_learning()`. **This function is never called from `console_api.py`
today** — confirmed via grep, zero hits.

Separately, three strategy-specific forward-test runners already do a narrower version
of the same comparison, standalone: `research/paper/tsmom_forward.py`,
`tom_forward.py`, `buyback_forward.py`, `congress_forward.py`, `form4_forward.py`.
Each runs a frozen config against fresh data monthly, computes a `backtest_envelope`
(Sharpe, maxDD, monthly P10/P90), and flags each forward month `in_envelope` /
`BELOW_P10` / `ABOVE_P90` — appending to its own `*_forward_ledger.jsonl` and writing a
`*_forward_report.md`. These are the concrete "expected_behavior vs current_behavior"
data points for the 2-4 strategies that have them; not all `paper_active` strategies
have a matching runner.

## STEP4-A Question 3 — Can a Forward Learning Record be built from existing data alone?

Yes, as a read-only projection — no new schema, no new ledger, no new store. Proposed
field mapping (all fields are joins over what already exists, keyed by `strategy_id`):

| `ForwardLearningRecord` field | Source (existing, unmodified) |
|---|---|
| `strategy_id` | `registry.jsonl` |
| `thesis` | `prediction_registry.list_predictions()` → `thesis` (if captured), else `experiment_registry` `note`/`verdict` |
| `evidence_used` | `experiment_registry.jsonl` row(s) for `hypothesis_id == strategy_id`: `sharpe`, `p`, `random_percentile`, `wf_first_sharpe`, `wf_second_sharpe`, `cost_robust` |
| `validation_status` | `registry.StrategyRegistry().state(strategy_id)["status"]` (FSM fold) |
| `paper_start_date` | `forward_deployments.jsonl` → `deployed_at` for that `strategy_id`, if deployed |
| `forward_period` | count of months in the matching `*_forward_ledger.jsonl` (where one exists) |
| `expected_behavior` | matching `*_forward_forward.py` runner's `backtest_envelope` (Sharpe/maxDD/P10/P90), where one exists; else `forward_testing.analyze()`'s `backtest` side |
| `current_behavior` | matching `*_forward_ledger.jsonl` latest entry / `envelope_deviation`, where one exists; else `forward_testing.analyze()`'s `paper` side + `findings` |
| `invalidation_condition` | `prediction_registry` capture, if one exists for this strategy; else none captured yet (a real gap — see below) |
| `decision_history` | `registry.jsonl` events for this `strategy_id` (`from`/`to`/`reason`/`approver`/`timestamp`) |

Every source field is read-only; no mutation, no new file. This satisfies STEP4-A's
"생성 목표" section exactly: "필요하다면 기존 registry/audit/paper 데이터를 조합한
읽기 모델만 추가."

## What's actually missing (the real gap, honestly stated)

1. **No dashboard consumer** for `research-accountability` or `data-connection` — both
   endpoints exist and return real data (verified live above) but zero `.tsx` file
   references them (`grep` confirmed). This is STEP4-B/C's actual remaining work:
   wire existing endpoints, don't build new score logic.
2. **`forward_testing.analyze()` is not wired to any endpoint.** It's the one genuine
   "needs a new read model" case in STEP4-A — a small `console_api` endpoint (or
   inclusion inside the proposed `ForwardLearningRecord` projection) that calls
   `analyze()` per strategy that has both a backtest envelope and paper/forward data.
3. **Coverage is real and thin.** Only 5 predictions ever captured, 100% from
   `committee`, 0% evaluated, 100% missing `expected_horizon`. This is not a dashboard
   problem — it's an input problem. `research_capture.py`'s runbook exists but hasn't
   been run broadly across `paper_active`/`watchlist`/`paper_candidate` strategies.
   STEP4-C's job is to **surface this gap**, not fabricate more predictions (per its
   own "새 prediction generator 만들지 않는다" constraint) — the dashboard should show
   "5 captured, 4 paper_active + 5 watchlist strategies exist, coverage thin" honestly.
4. Not every `paper_active`/`watchlist` strategy has a per-strategy forward runner
   (`tsmom`/`tom`/`buyback`/`congress`/`form4` do; others don't). The
   `ForwardLearningRecord` projection must degrade gracefully — `forward_testing.analyze()`
   as fallback where no dedicated runner ledger exists, and honest `null`s where neither
   exists yet, not synthesized numbers.

## Recommendation for Commit 2

Add one new read-only module — `jarvis/investment_os/forward_learning.py` (lives under
the already-protected `investment_os` consumption layer, consistent with its existing
role: "연구 지식 소비, Research OS 무변경") — exposing `build_forward_learning_records()`
that performs the join in the table above. No new files under `research_workflow` (stays
protected/untouched), no new ledger, no new schema on disk — pure in-memory projection
over the sources listed. One new `console_api` endpoint (`GET /console/forward-learning`)
returns it. Verification after: `pytest tests/ -q`, `registry_hash` unchanged, governance
`validate_all()` unchanged, `console_api` import clean.
