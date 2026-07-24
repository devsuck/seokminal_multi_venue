# Operational Procedures

- **Run validation:** `python -m jarvis.system_integration validate`
- **Run security audit:** `python -m jarvis.security_audit audit`
- **Assess readiness:** `python -m jarvis.production_review assess`
- **Regenerate docs:** `python -m jarvis.architecture_docs generate`
- Every layer CLI is read-only; none can execute, trade, deploy, or allocate.
- **Escalation:** all layers are observation/record-only; no automated action fires.
