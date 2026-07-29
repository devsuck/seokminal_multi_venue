# Contribution Guide

Contributions to the Autonomous Quant Research OS must preserve its two defining
properties: the system is **additive** and it is **read-only**. Every change is
reviewed against those properties before it lands.

## Branch workflow

- Branch off the main line; never commit directly to it.
- Use a descriptive branch name, e.g. `feat/<layer>-<summary>` or `fix/<layer>-<summary>`.
- Keep a branch scoped to one layer or one concern where possible.

```bash
git checkout -b feat/research_manager-summary-export
```

## The additive + backward-compatible mandate

- New behavior is added as new layers, new records, or new events — not by mutating
  or removing existing public APIs.
- Do not change the meaning of existing ledger fields or ID formats; that would
  break replay and invalidate historical audit trails.
- Nothing you add may trade, order, deploy, allocate capital, promote models, or
  change permissions.

If a change cannot be made additively and backward-compatibly, discuss it before
writing code.

## Pre-commit checklist

Run all of the following and confirm they pass before committing:

```bash
python -m pytest jarvis -q
python -m jarvis.documentation validate
python -m jarvis.documentation gen
```

For the layer you touched, also run the fast isolated suite:

```bash
python -m pytest jarvis/<layer>/tests -q --no-header --noconftest -p no:cacheprovider
```

## Security scans

The per-layer forbidden-import and forbidden-execution AST tests are part of the
regression and must stay green — they enforce the read-only guarantee. The P15
security & compliance layers (`security`, `compliance`, `integrity`, `sbom`,
`dependency`, `license`, `threat_model`) provide additional checks; do not disable
or weaken them to make a change pass.

## Commit message discipline

- Write a concise imperative subject line, e.g. `Add summary export to research_manager`.
- In the body, state which layer changed and confirm the change is additive and
  read-only.
- Reference the tests and docs commands you ran.
- Keep unrelated changes out of the commit; one logical change per commit.

## Before opening a review

Confirm the full suite is green, docs validate and regenerate cleanly, and no file
outside your intended scope was modified. Reviewers will reject changes that touch
execution paths or break replay determinism.
