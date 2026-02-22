# CoWork Shield — PRD (HANDOFF B Validation)

**Version**: B-PRD v1  
**Date**: February 22, 2026  
**Scope**: Internal validation of trust-critical CLI core

## 1) Product Goal
Validate the internal production readiness of a reversible anonymization engine where recoverability is guaranteed and safety checks are fail-closed by default.

## 2) Positioning
Primary promise for this phase:
> Use AI on real client data without manual rewrite risk, while preserving deterministic recoverability.

## 3) Phase Scope
### Included
- CLI engine (Python only, pinned `uv` environment).
- File workflows: CSV/XLSX/DOCX/TXT.
- Clipboard workflows.
- Deterministic replay enforcement.
- Model version lock enforcement.
- Token ABI v2 bracket format with backward-compatible restore.
- Hallucination detection and restore abort behavior.

### Excluded
- Swift wrapper, IPC service, GUI/menu bar app.
- External telemetry/cloud sync.
- Enterprise policy/admin features.

## 4) Non-Negotiable Invariants
1. Workspace must be restorable or explicitly invalidated; never silently unrecoverable.
2. Restore never commits partial output.
3. Replay mismatch for identical input/model/workspace aborts.
4. Model hash mismatch aborts unless audited override.
5. XLSX lossy risk is blocked unless explicit acknowledgment.

## 5) Exit Criteria (Internal Validation)
- Incorrect restores: **0**
- Unflagged mutated tokens: **0**
- Hallucinated token flagging: **100% for detected token-shaped anomalies**
- Replay mismatch handling: **100% fail-closed**
- Model lock mismatch handling: **100% fail-closed unless override**
- Clipboard round-trip latency target path available and operational
- Full automated suite green

## 6) Release-Blocking Test Matrix (Summary)
### A. Core Correctness
- Round-trip CSV/XLSX/DOCX/TXT.
- Formula preservation checks and XLSX functional open/validation.

### B. Determinism & Version Lock
- Same input replay hash match.
- Hash mismatch abort.
- Model hash mismatch abort.
- Audited override path records reason/user/timestamp/events.

### C. Hallucination Safety
- Mutated token detection.
- Hallucinated token detection.
- Dropped token detection when expected token set is available.
- Restore abort on any flagged anomaly.

### D. State Integrity & Recovery (Mandatory Gate)
- Crash consistency: anonymize/restore/vault write interruption.
- Filesystem hostility: rename/move/encoding churn.
- Concurrency safety: parallel operations and clipboard burst.
- Vault integrity: corruption, partial metadata loss, TTL edge handling.
- Environment edge: sleep/wake, clock skew, disk full.
Implementation harness:
- `tests/test_state_integrity/test_ec15_state_integrity.py` (EC-15 block)

### E. Enterprise-Sales Critical Additions
- Audit export schema validation (`user_id`, `workspace_id`, `timestamp`, attestation decision).
- Model hash verification startup enforcement.
- Passive trust signal logic validation.
- Excel formula validity (functional, not only byte compare).

## 7) Weekly Red Team Execution (Required)
- Deterministic snapshot drift detection:
  - golden input hash
  - golden anonymized hash
  - golden restored hash
  - golden vault snapshot hash
  - golden behavioral classification snapshot
- Dependency drift sentinel:
  - log Presidio/spaCy/model hash/macOS/Python runtime footprints.
  - auto-expand to full core waves on any drift.
- Time-to-failure/perf deltas:
  - total runtime, peak memory, clipboard p95, vault write latency, restore latency.
  - >10% WoW deviation triggers investigation.
- Randomized fuzz pass:
  - randomized entities/unicode/whitespace/token mutations.
- Long-run stability:
  - 500 anonymize->restore cycles on one workspace.
  - 100 open/close cycles.
  - 100 clipboard burst cycles.
- Trust perception injection:
  - force one flagged hallucination in success path; verify warning + export trail.

## 8) Milestones
1. Core hardening complete (current state).
2. State-integrity gauntlet automation complete.
3. Weekly red-team sentinel running with artifacts.
4. Internal acceptance review and go/no-go for broader beta surface.

## 9) Risks
- Keychain key loss -> unrecoverable vault (explicitly documented).
- Dependency drift undermining determinism if lock checks are bypassed.
- Concurrency/crash edges causing irreversible trust events if untested.

## 10) Success Definition
Handoff B is successful only if recoverability and fail-closed behavior remain true under normal use and adversarial state-integrity scenarios, not only happy-path correctness tests.
