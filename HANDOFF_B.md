# Cloakroom — HANDOFF B (Internal Validation Build)

**Version**: B.1  
**Date**: February 22, 2026  
**Status**: Active internal validation scope  
**Repo**: [GreggBerretta/cloakroom](https://github.com/GreggBerretta/cloakroom)

## 1) Purpose
HANDOFF B defines the lean internal build focused on trust invariants, deterministic replay, and practical consultant workflows.  
This build intentionally removes product-layer surface area (Swift/IPC/GUI) and hardens the reversible core.
For Phase 2+ wrapper reintegration, see `WRAPPER_ARCHITECTURE_ADDENDUM.md` (which supersedes the Swift/IPC out-of-scope lines in this document for wrapper workstreams).

## 2) Scope (In)
- Python CLI only (`uv`-managed environment).
- Formats: CSV, XLSX, DOCX, TXT.
- Clipboard commands: `shield-clipboard`, `restore-clipboard`.
- Deterministic replay enforcement (always on).
- Detection model hash lock enforcement.
- Bracketed token ABI v2: `[PERSON_00001]`.
- Hallucination/mutation/dropped-token fail-closed checks on restore.
- Auditable overrides for forced re-anonymization.
- XLSX chart/image lossy-risk block unless explicitly acknowledged.

## 3) Scope (Out)
- Swift wrapper, menu bar app, AppKit/SwiftUI.
- IPC protocol/daemon/socket service.
- External telemetry/cloud sync.
- Enterprise export/reporting productization beyond internal JSON-ready metadata.

## 4) Core Invariants (Release Blocking)
1. Same input + same workspace + same model hash -> identical anonymized SHA-256 output.
2. Restore is fail-closed: no partial commit on any verification error.
3. Model drift cannot run silently (lock mismatch fails unless explicit audited override).
4. Token ABI collisions are mitigated via bracketed format v2.
5. XLSX lossy structures are blocked unless explicit `--allow-lossy-xlsx`.
6. Any safety override requires explicit reason and is persisted in `FileRecord`.

## 5) Implemented Decisions
- **Deterministic replay** is mandatory in anonymize pipeline; optional replay flag removed.
- **Model lock** is enforced against `vault_data.model_hashes["en_core_web_lg"]`.
- **Override policy** uses `--force-reanonymize --reason "..."`
  - Audit fields recorded: `reanonymize_override`, `override_reason`, `override_user`, `override_timestamp`, `override_events`, `previous_output_hash`.
- **XLSX risk policy**:
  - Default: fail with `XLSXContentLossRiskError` when chart/image risk is present.
  - Override: `--allow-lossy-xlsx`.
- **Clipboard** workflows are first-class CLI commands.

## 6) Commands
```bash
uv run cloakroom anonymize FILE -w WORKSPACE
uv run cloakroom restore FILE -w WORKSPACE
uv run cloakroom shield-clipboard -w WORKSPACE
uv run cloakroom restore-clipboard -w WORKSPACE
uv run cloakroom workspace list
uv run cloakroom workspace show WORKSPACE
```

## 7) Validation Status
- Full test suite passing: **242 passed**.
- EC-15 state integrity harness added:
  - `tests/test_state_integrity/test_ec15_state_integrity.py`
  - Run directly: `uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py`
- New coverage added for:
  - deterministic replay mismatch fail,
  - model lock mismatch fail,
  - audited override path,
  - TXT handler round-trip,
  - hallucination detector classes,
  - restore fail-closed on mutated/dropped tokens,
  - clipboard shield/restore behavior,
  - XLSX lossy-risk gating,
  - crash consistency, filesystem hostility, concurrency safety, vault integrity, and environment-edge recovery checks.

## 8) Remaining Work (Handoff B Validation)
- Run expanded state-integrity gauntlet (crash consistency, filesystem hostility, concurrency, TTL edges).
- Add deterministic weekly snapshot drift checks.
- Add dependency drift sentinel and conditional full-wave expansion.
- Add weekly performance delta monitoring and long-run cycle stability tests.
- Add random fuzz pass for offset/Unicode mutation edge cases.

## 9) Known Limits
- If Keychain entry is deleted, workspace decryption is unrecoverable (explicit by design).
- Clipboard operations rely on macOS `pbpaste`/`pbcopy`.
- Model hash lock is environment-derived and should be pinned in release packaging.

## 10) Changelog (Pre-Handoff -> HANDOFF B.1)
- Removed Swift/IPC assumptions from internal scope.
- Added TXT handler and `.txt` pipeline support.
- Enforced bracketed token ABI v2 generation.
- Added backward-compatible legacy token restore handling.
- Added deterministic replay enforcement in anonymize flow.
- Added detection model hash lock checks with fail-closed behavior.
- Added auditable override fields and CLI override reason enforcement.
- Added XLSX lossy-content blocking with explicit acknowledgment flag.
- Added hallucination detector module (hallucinated/mutated/dropped classification).
- Integrated hallucination checks into restore pipeline before commit.
- Added clipboard shield/restore commands with vault-integrated metadata updates.
