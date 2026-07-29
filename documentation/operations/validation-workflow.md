# Validation Workflow

This is the ordered pre-release checklist for the Autonomous Quant Research OS.
Run the steps in sequence; a failure at any step blocks release until resolved.
Nothing here deploys or trades — the workflow validates recorded research only.

## 1. Full regression

```bash
python -m pytest jarvis -q
```

All tests must pass, including the forbidden-import scans that enforce the
research-only boundary.

## 2. Documentation validation

```bash
python -m jarvis.documentation gen
python -m jarvis.documentation validate
```

Regenerate the API reference, then validate format rules across the docs tree.

## 3. Ledger integrity

```python
from jarvis.integrity import verify_ledger
```

Verify the SHA256 hash chain of each `_state/` ledger. A broken chain means a
record was altered or truncated; investigate before continuing.

## 4. Replay verification

```bash
python -m jarvis.research_manager replay
```

Every layer must report `deterministic: true`. See
`documentation/operations/running-replay.md` if it does not.

## 5. Security scan

```python
from jarvis.security import scan_files, scan_source
from jarvis.compliance import run_compliance
```

Scan source and files for policy violations; there must be no unresolved
findings.

## 6. Dependency and license audit

```python
from jarvis.dependency import scan_dependencies, build_report
from jarvis.license import build_inventory
```

Confirm dependencies are known and licenses are acceptable.

## 7. SBOM verification

```python
from jarvis.sbom import sbom_from_dependencies, verify_sbom
```

Build the SBOM from the audited dependencies and assert `verify_sbom` returns
`True`.

## 8. Compliance checklist

```python
from jarvis.compliance import run_compliance
from jarvis.threat_model import build_threat_model
```

Run compliance and review the threat model. All reports are non-binding; a green
checklist certifies documentation quality, not deployment.
