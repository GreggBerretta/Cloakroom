# CoWork Shield — HANDOFF B Status (Engineer Transfer)

**Status Date:** February 23, 2026  
**Status Basis:** `HANDOFF_B.md` + `PRD_HANDOFF_B.md`  
**Scope:** Internal validation track + Phase 2+ wrapper core/protocol implementation

## 1) Snapshot Context
- Source repo: [GreggBerretta/cowork-shield](https://github.com/GreggBerretta/cowork-shield)
- Fork repo: [GreggBerretta/cowork-shield-fork](https://github.com/GreggBerretta/cowork-shield-fork)
- Active integration branch: `codex/handoff-b-status-doc-clean`
- Snapshot commit: `3368ba8` (fork + local branch head)
- Pilot kickoff issue: [#1](https://github.com/GreggBerretta/cowork-shield/issues/1)
- Pilot milestone: `Pilot Kickoff Week (2026-02-23)`

This document is intended to be sufficient for another engineer to continue without additional tribal context.

## 2) Current Delivery Status
### Completed
- Deterministic replay enforcement is default (fail-closed).
- Detection model hash lock enforcement is default.
- Token ABI v2 (`[TYPE_00001]`) is active; legacy token restore compatibility is retained.
- XLSX lossy-content risk (charts/images) is blocked unless explicitly acknowledged.
- Auditable safety overrides are implemented (`--force-reanonymize --reason ...`).
- Hallucination/mutation/dropped-token checks run before restore commit (fail-closed).
- TXT handler and clipboard shield/restore workflows are implemented.
- Markdown (`.md`) anonymize/restore is implemented and tested end-to-end.
- EC-15 state integrity harness is implemented.
- CI workflows and weekly trust gate workflows are present.
- Operational docs are present (`INSTALL.md`, `TROUBLESHOOTING.md`).
- Encrypted key recovery export/import commands are implemented.
- Textual TUI and Gradio Web UI frontends are implemented.
- UI risky operations now require explicit confirmation gates (lossy XLSX + force re-anonymize).
- UI error handling is sanitized to avoid echoing sensitive payloads/tokens.
- Multi-language detection is implemented (`auto`, `en`, `he`) with Hebrew model fallback support.
- Hebrew enhancement backends are implemented (`spacy`, `stanza`, `transformers`) with GolemPII model override support.
- PDF support is implemented as input-only (PDF -> extracted Markdown/DOCX -> anonymize/restore on text outputs).
- Direct PDF restore is explicitly blocked with fail-closed error messaging.
- Column-selective spreadsheet anonymization is implemented for CSV/XLSX.
- Column selection supports letters (`A,C,F`) and header names (`"Client Name,Deal ID"`).
- `inspect-columns` command is implemented for preflight selector discovery.
- Column-only mode and combined mode (`--detect-pii`) are both supported.
- TUI and Gradio now expose spreadsheet column selection workflows.
- Column inspection now surfaces lightweight type hints and sample values for safer selection.
- Hybrid IPC is implemented (Mode A stdio default + Mode B AF_UNIX).
- Wrapper-oriented IPC operations (HELLO/HEARTBEAT/file/clipboard/workspace/key/stats/inspect) are implemented.
- Swift wrapper core package is implemented (`wrapper/CoWorkShieldWrapper`) with FSM, protocol validation, framing, clipboard guard, and anti-false-success gate.
- Wrapper launcher/transport modules are implemented for mode selection and child-process UI bridge launch.
- Engine-side wrapper license checks are implemented (`license_key` payload support + feature/limit enforcement).
- Wrapper invariant harness (`swift run wrapper-invariant-checks`) is implemented and passing.

### Validation
- Full test suite: **259 passed**.
- EC-15 suite: **14 passed**.
- Fork-only bootstrap validation (Feb 22, 2026):
  - `en_core_web_lg` installed in local fork clone.
  - `tests/test_detection/test_engine.py` + `tests/test_state_integrity/test_ec15_state_integrity.py`: **29 passed**.
  - Full suite in a fresh clone still requires Hebrew model install (`he_core_news_sm` or `xx_ent_wiki_sm`).

## 3) Where Everything Sits
### Product/Scope Docs
- `HANDOFF.md` (full commercial path)
- `HANDOFF_B.md` (lean internal path)
- `PRD_HANDOFF_B.md` (validation PRD)
- `HANDOFF_B_STATUS.md` (this document)
- `PILOT_KICKOFF.md` (kickoff plan and agenda)

### Operational Docs
- `INSTALL.md` (installation + onboarding)
- `TROUBLESHOOTING.md` (support runbook + escalation)
- `PERFORMANCE.md` (one-time pilot baseline metrics)

### Core Engine (Source)
- CLI commands: `src/cowork_shield/cli.py`
- Anonymize orchestration: `src/cowork_shield/pipeline/anonymize.py`
- Restore orchestration: `src/cowork_shield/pipeline/restore.py`
- Workspace lifecycle + locks + TTL checks: `src/cowork_shield/workspace/manager.py`
- Token generation (ABI v2): `src/cowork_shield/tokenizer/generator.py`
- Token replacement and legacy compatibility: `src/cowork_shield/tokenizer/replacer.py`
- Token regex contract: `src/cowork_shield/tokenizer/patterns.py`
- Verification scanner: `src/cowork_shield/verification/verifier.py`
- Detection engine + model hash: `src/cowork_shield/detection/engine.py`
- PDF extractor abstraction: `src/cowork_shield/extractors/pdf_markdown.py`

### New Feature Modules
- Clipboard workflows: `src/cowork_shield/clipboard/operations.py`
- Hallucination detection: `src/cowork_shield/hallucination/detector.py`
- Hallucination formatting: `src/cowork_shield/hallucination/formatter.py`
- TXT handler: `src/cowork_shield/handlers/text_handler.py`
- Recovery key export/import crypto: `src/cowork_shield/vault/recovery.py`
- UI pipeline wrapper API: `src/cowork_shield/pipeline/ui_api.py`
- Textual UI: `src/cowork_shield/tui/app.py`
- Gradio UI: `src/cowork_shield/ui/gradio_app.py`
- PDF input-only handler: `src/cowork_shield/handlers/pdf_handler.py`

### CI / Automation
- Main CI: `.github/workflows/ci.yml`
- EC-15 per-push gate: `.github/workflows/ec15-gate.yml`
- Weekly trust gate: `.github/workflows/weekly-trust-gate.yml`

## 4) Command Surface (Current)
### Core Commands
- `cowork-shield anonymize FILE -w WORKSPACE`
- `cowork-shield anonymize FILE -w WORKSPACE --columns ...`
- `cowork-shield inspect-columns FILE`
- `cowork-shield ipc-stdio`
- `cowork-shield ipc-server --socket-path ...`
- `cowork-shield restore FILE -w WORKSPACE`
- `cowork-shield shield-clipboard -w WORKSPACE`
- `cowork-shield restore-clipboard -w WORKSPACE`
- `cowork-shield workspace list`
- `cowork-shield workspace show WORKSPACE`
- `cowork-shield workspace delete WORKSPACE`
- `cowork-shield workspace cleanup`
- `cowork-shield-tui` (Textual terminal UI)
- `cowork-shield-gradio` (Gradio web UI)
- `swift run wrapper-invariant-checks` (wrapper invariant harness)

### Safety / Recovery Commands
- `cowork-shield workspace export-key --workspace NAME --output FILE`
- `cowork-shield workspace import-key --workspace NAME --input FILE`

### Important Flags
- `--columns A,C,F` or `--columns "Name,Deal ID"` (CSV/XLSX column-selective anonymization)
- `--detect-pii` (combine Presidio with selected columns)
- `--force-reanonymize --reason "..."` (audited override)
- `--allow-lossy-xlsx` (explicit XLSX lossy-content acknowledgment)
- `--pdf-output-format md|docx` (required choice when input is PDF)
- `--language auto|en|he` (detection language selection)
- `--hebrew-backend auto|spacy|stanza|transformers` (Hebrew NLP backend selection)
- `--hebrew-transformer-model MODEL_ID` (override specialized Hebrew transformers model)

## 5) Test Inventory and Execution
### Primary Commands
- `uv run pytest -q`
- `uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py`

### Key Test Areas
- Core pipeline: `tests/test_pipeline/`
- Token ABI/generation/restore behavior: `tests/test_tokenizer/`
- Handlers (PDF/CSV/XLSX/DOCX/TXT/MD): `tests/test_handlers/`
- Hallucination detection: `tests/test_hallucination/`
- Clipboard operations: `tests/test_clipboard/`
- Vault/recovery crypto and persistence: `tests/test_vault/`
- EC-15 (release-blocking state integrity): `tests/test_state_integrity/test_ec15_state_integrity.py`
- UI API helper coverage: `tests/test_ui/`
- IPC protocol/framing/server: `tests/test_ipc/`

### EC-15 Coverage (Current)
- Crash consistency
- Filesystem hostility (rename/move/encoding churn)
- Concurrency safety
- Vault integrity failure modes
- Environment edges (sleep/wake interruption simulation, clock skew, disk full)

## 6) Pilot Operations Status
### Installation and Onboarding
- Install flow documented in `INSTALL.md` (uv sync path).
- Prereqs include model install:
  - `uv run python -m spacy download en_core_web_lg`
  - `uv run python -m spacy download he_core_news_sm || uv run python -m spacy download xx_ent_wiki_sm`
- UI launch instructions documented for both `cowork-shield-tui` and `cowork-shield-gradio`.

### Support Model
- Support/error-code handling documented in `TROUBLESHOOTING.md`.
- Error code = exception class (e.g., `IntegrityError`, `ReplayMismatchError`, `RecoveryKeyError`).

### Pilot Kickoff
- Scheduled for **Wednesday, February 25, 2026 at 10:00 AM PT**.
- Agenda and prep are in `PILOT_KICKOFF.md`.
- Tracked issue: [#1](https://github.com/GreggBerretta/cowork-shield/issues/1).

## 7) Security and Recoverability Posture
### Enforced
- Fail-closed restore path.
- Deterministic replay checks.
- Model lock checks.
- HMAC integrity checks for mappings.
- Auditable safety overrides.
- Workspace operation serialization via lock.
- Gradio launcher is pinned to localhost binding (`127.0.0.1`).

### Recovery
- If Keychain entry is lost, recovery requires prior encrypted export.
- Recovery key exports are passphrase-encrypted and file permissions are set to `0600`.

## 8) Remaining Work (Not Yet Implemented)
1. Deterministic snapshot baseline drift detection with golden hashes.
2. Conditional full-wave expansion based on dependency drift deltas.
3. Week-over-week performance regression thresholds and alerting.
4. Randomized fuzz pass for offset/unicode mutation edge cases.
5. Long-run stability campaigns (hundreds of repeated cycles).

## 9) Handoff Checklist for Incoming Engineer
1. Check out `codex/handoff-b-status-doc-clean`.
2. Run `uv sync --extra dev`.
3. Run `uv run python -m ensurepip`.
4. Run `uv run python -m spacy download en_core_web_lg`.
5. Run `uv run python -m spacy download he_core_news_sm || uv run python -m spacy download xx_ent_wiki_sm`.
6. Run `uv run pytest -q` and confirm green.
7. Run `uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py`.
8. Review docs in this order: `HANDOFF_B.md`, `PRD_HANDOFF_B.md`, `HANDOFF_B_STATUS.md`, `INSTALL.md`, `TROUBLESHOOTING.md`.
9. Continue next on weekly drift + performance sentinel implementation.

## 10) Go/No-Go Matrix (Current)
| Criterion | Status | Evidence |
| --- | --- | --- |
| Full Test Suite | ✅ | `259 passed` |
| Fork-Only English Bootstrap | ✅ | `en_core_web_lg` installed; detection + EC-15 smoke = `29 passed` |
| Fork-Only Full Suite Prereq | ⚠️ | Hebrew model still required for full suite (`he_core_news_sm` or fallback) |
| EC-15 State Integrity | ✅ | `14 passed` |
| CI Automation | ✅ | `ci.yml`, `ec15-gate.yml`, `weekly-trust-gate.yml` |
| Install Path | ✅ | `INSTALL.md` |
| UI Frontends | ✅ | `cowork-shield-tui`, `cowork-shield-gradio` |
| Support Runbook | ✅ | `TROUBLESHOOTING.md` |
| Key Recovery Path | ✅ | `workspace export-key/import-key` |
| Weekly Drift Sentinel | ⚠️ Partial | dependency snapshot artifact only |
| Performance Drift Sentinel | ❌ | not yet implemented |
| Long-run Stability Campaign | ❌ | not yet implemented |
