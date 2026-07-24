# ADR 0009 — Security Architecture

## Status

Accepted.

## Context

A production research OS handles code, dependencies, and generated artifacts. It needs defenses
against hardcoded secrets, unsafe code patterns, supply-chain risk, tampering, and license
issues — implemented additively, without changing the layers it protects.

## Decision

Security is a set of **read-only, additive analysis tools** (P15):

- `security` — secret scanning (AWS/OpenAI/GitHub/Slack/JWT/SSH/API-key/password) with masking
  and `# pragma: allowlist secret` suppression, plus AST static analysis (eval/exec/pickle/
  subprocess-shell/os.system/path-traversal/unsafe-deserialization).
- `integrity` — hash-chain, tamper, duplicate-ID, timestamp, lineage, and replay verification,
  plus artifact validation.
- `sbom`, `dependency`, `license` — SBOM generation/verification, dependency audit, and license
  compatibility.
- `compliance`, `threat_model` — checklists and a full threat model.

## Consequences

- **Defense without disruption:** these tools import nothing from the execution boundary and
  modify no ledgers; they observe and report.
- **Self-clean:** the security package's own source passes its own secret and static scans (its
  pattern literals are neutralized and allowlisted).
- **Actionable posture:** deterministic reports feed the compliance checklists and the release
  validation workflow.
- **Scope:** these tools raise assurance; they are not a substitute for external audits or OS-
  level hardening.
