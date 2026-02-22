# CoWork Shield Fork Status Report

## Snapshot
- Date: 2026-02-22 23:47:00 UTC
- Repository: `GreggBerretta/cowork-shield-fork`
- Branch: `codex/handoff-b-status-doc`
- Scope baseline: `HANDOFF_B.md` and `PRD_HANDOFF_B.md`
- Product mode: Internal validation engine + Phase 2+ wrapper core/protocol implementation

## Executive Summary
The fork currently has a hardened local anonymize/restore engine with fail-closed recovery behavior, deterministic replay controls, model hash locking, auditable overrides, Hebrew support, PDF input-only conversion support, spreadsheet column-selective anonymization, clipboard workflows, and two frontends (Textual TUI and Gradio web UI). It now also includes a strict AF_UNIX IPC daemon and a Swift wrapper core package implementing state-machine, framing, protocol-validation, clipboard-guard, and anti-false-success invariants.

Current validation status is green:
- `uv run ruff check src tests` passes.
- `uv run pytest -q` passes with **242 passed**.
- `uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py` passes with **14 passed**.
- `swift run wrapper-invariant-checks` passes in `wrapper/CoWorkShieldWrapper`.

## Implemented Baseline Functionality

### Core Engine and Trust Invariants
- Deterministic tokenization with HMAC integrity (`src/cowork_shield/tokenizer/generator.py`).
- Token ABI v2 (`[TYPE_00001]`) with legacy restore compatibility (`src/cowork_shield/tokenizer/patterns.py`, `src/cowork_shield/tokenizer/replacer.py`).
- Fail-closed restore with integrity verification and no partial commit (`src/cowork_shield/pipeline/restore.py`).
- Deterministic replay checks + model version lock on anonymize (`src/cowork_shield/pipeline/anonymize.py`, `src/cowork_shield/detection/engine.py`).
- Auditable override path for forced re-anonymization (`--force-reanonymize --reason`, persisted in `FileRecord`).
- Hallucination/mutation/dropped token detection before restore commit (`src/cowork_shield/hallucination/detector.py`).

### Workspace, Vault, and Recovery
- Encrypted local vault with operation lock and TTL handling.
- Keychain-backed key management.
- Recovery key export/import commands implemented:
  - `workspace export-key`
  - `workspace import-key`
- Key-loss irrecoverability remains explicit unless a recovery key was exported beforehand.

## File Format Support Matrix

| Format | Anonymize | Restore | Notes |
| --- | --- | --- | --- |
| `.txt` | Yes | Yes | Single-body text handler |
| `.md` | Yes | Yes | Single-body markdown/text handler |
| `.csv` | Yes | Yes | Dialect-preserving handler + column-selective mode |
| `.xlsx` | Yes | Yes | Formula-preserving; chart/image lossy-risk gate |
| `.docx` | Yes | Yes | Paragraph/table/header/footer handling |
| `.pdf` | Yes (input-only) | No direct PDF restore | Converts to `.md`/`.docx`, restore those outputs |

PDF policy is intentionally non-reconstructive:
- No attempt to rebuild original PDF binary or layout.
- Pipeline: PDF extract -> anonymize extracted text -> restore tokenized text output.

## Spreadsheet Status (PII + Column-Selective)

### Automatic PII Detection
- Existing Presidio-based detection still works for CSV/XLSX.
- Formula cells are preserved in XLSX and not tokenized.

### Manual Column-Selective Anonymization (New)
Implemented in:
- `src/cowork_shield/handlers/column_select.py`
- `src/cowork_shield/handlers/csv_handler.py`
- `src/cowork_shield/handlers/xlsx.py`
- `src/cowork_shield/pipeline/columns.py`
- `src/cowork_shield/pipeline/anonymize.py`
- `src/cowork_shield/cli.py`
- UI integration in TUI and Gradio

Capabilities:
- Select columns by letter (`A,C,F`) or name (`"Client Name,Deal ID"`).
- `inspect-columns` command for preflight discovery.
- Column metadata includes:
  - index
  - letter
  - header name
  - lightweight type hint (`text`, `number`, `date`, `mixed`, `unknown`)
  - sample values (first 3 non-empty examples, truncated)
- Column-only mode supported.
- Combined mode supported (`--columns ... --detect-pii`) for selected columns + normal detection on non-selected columns.
- Validation errors are fail-fast (`ColumnSelectionError`) with available-column feedback.

Token behavior:
- Letter-based selection token prefix example: `[COL_A_00001]`.
- Name-based selection token prefix example: `[CLIENTNAME_00001]`.
- Column tokens are typed as internal `EntityType.COLUMN` and are excluded from Presidio entity requests.

## Hebrew Support Status
Implemented in `src/cowork_shield/detection/engine.py`.

Language support:
- `auto`, `en`, `he`

Hebrew backend options:
- `spacy` (default runtime behavior when auto-resolving)
- `stanza` (optional extra dependency)
- `transformers` (optional extra dependency; supports specialized model override)

CLI flags:
- `--hebrew-backend auto|spacy|stanza|transformers`
- `--hebrew-stanza-model`
- `--hebrew-transformer-model`

Environment variables:
- `CWS_HEBREW_NLP_ENGINE`
- `CWS_HEBREW_STANZA_MODEL`
- `CWS_HEBREW_TRANSFORMER_MODEL`
- `CWS_HEBREW_TRANSFORMER_SPACY_MODEL`

Current model behavior:
- English model: `en_core_web_lg`.
- Hebrew spaCy resolution prefers `he_core_news_sm`, falls back to `xx_ent_wiki_sm`.
- Advanced backends are optional via extras and model install.

## PDF Conversion Status
Implemented across:
- `src/cowork_shield/extractors/pdf_markdown.py`
- `src/cowork_shield/handlers/pdf_handler.py`

Behavior:
- Extractor strategy: Docling first, fallback to PyMuPDF.
- Output format options for anonymize: `md` or `docx` (`--pdf-output-format`).
- Direct `.pdf` restore is blocked with explicit error (`PdfInputOnlyError`).

## UI Status

### CLI
Implemented in `src/cowork_shield/cli.py`:
- Core file anonymize/restore commands.
- Spreadsheet inspection command (`inspect-columns`).
- Clipboard commands.
- Workspace and recovery key commands.
- Column-selective and detect-pii controls.

### Textual TUI
Implemented in `src/cowork_shield/tui/app.py`:
- Workspace selector
- File input
- Language selector
- PDF output-format selector
- Spreadsheet column load/select flow
- Detect-PII toggle for non-selected columns
- Risk confirmations for lossy XLSX and forced re-anonymize
- Entity preview table

### Gradio Web UI
Implemented in `src/cowork_shield/ui/gradio_app.py`:
- Shield and Restore tabs
- Workspace selection + refresh
- Language + PDF output-format controls
- Spreadsheet column multi-select (with type/sample label)
- Detect-PII toggle for selected-column workflows
- Risk confirmations and sanitized error messaging
- Bound to localhost in launcher (`127.0.0.1`)

## Wrapper / IPC Status (Phase 2+)
Implemented components:
- AF_UNIX socket daemon with 8-byte length-prefixed JSON framing:
  - `src/cowork_shield/ipc/framing.py`
  - `src/cowork_shield/ipc/server.py`
- Envelope/schema/version contract:
  - `src/cowork_shield/ipc/protocol.py`
- IPC CLI daemon entrypoint:
  - `uv run cowork-shield ipc-server --socket-path ~/.cowork-shield/ipc/engine.sock`
- Swift wrapper core package:
  - `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/WrapperStateMachine.swift`
  - `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/WrapperController.swift`
  - `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/IPCEnvelope.swift`
  - `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/LengthPrefixedCodec.swift`
  - `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/ClipboardGuard.swift`
  - `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/UnixDomainSocketTransport.swift`
- Swift invariant harness:
  - `wrapper/CoWorkShieldWrapper/Sources/WrapperInvariantChecks/main.swift`
  - Run with: `swift run wrapper-invariant-checks`

Implemented wrapper-facing operations in daemon:
- `HELLO`, `HEARTBEAT`, `WORKSPACE_SWITCH`
- `ANONYMIZE_FILE`, `RESTORE_FILE`
- `CLIPBOARD_ANONYMIZE`, `CLIPBOARD_RESTORE`
- `VAULT_EXPORT_KEY`, `VAULT_IMPORT_KEY`
- `STATS_QUERY`, `INSPECT_COLUMNS`
- `SHUTDOWN`

## Testing and Validation Results

### Latest Local Validation
Executed on this branch:

```bash
uv run ruff check src tests
# All checks passed

uv run pytest -q
# 242 passed, 1 warning

uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py
# 14 passed, 1 warning

cd wrapper/CoWorkShieldWrapper
swift run wrapper-invariant-checks
# PASS
```

### State Integrity (EC-15)
Covered tests include:
- Crash consistency
- Filesystem hostility (rename/move/encoding churn)
- Concurrency and multi-actor safety
- Vault integrity corruption/deletion handling
- Environment edge scenarios (sleep/wake, clock skew, disk full)

### Added Test Coverage for Column Selective Feature
New or expanded tests include:
- Column selection parser/resolution helpers
- CSV and XLSX column-only and combined-mode anonymization
- Invalid column handling
- `inspect-columns` coverage
- UI API and Gradio integration tests for column metadata and selection flow
- Round-trip restoration validation after selective anonymization

### Added Test Coverage for Wrapper Protocol / IPC
New tests include:
- `tests/test_ipc/test_protocol.py`
- `tests/test_ipc/test_framing.py`
- `tests/test_ipc/test_server.py`
- CLI coverage for IPC daemon command in `tests/test_cli.py`

## Performance Baseline (Current Reference)
From `PERFORMANCE.md`:
- 10k-row CSV anonymize: **95.74s**
- 10k-row CSV restore: **11.49s**
- Clipboard shield median: **1.07s**
- Clipboard restore median: **0.50s**
- Clipboard round-trip median: **1.57s**

## CI / Automation Status
Workflows in `.github/workflows`:
- `ci.yml` -> lint + full test suite
- `ec15-gate.yml` -> EC-15 gate on push
- `weekly-trust-gate.yml` -> scheduled weekly run with dependency snapshot artifact + full tests + EC-15

## Operational Docs Present
- `INSTALL.md`
- `TROUBLESHOOTING.md`
- `PERFORMANCE.md`
- `PILOT_KICKOFF.md`
- `HANDOFF_B.md`
- `PRD_HANDOFF_B.md`
- `HANDOFF_B_STATUS.md`
- `WRAPPER_ARCHITECTURE_ADDENDUM.md`

## Known Constraints and Current Gaps
- PDF is input-only by design; original PDF binary reconstruction is not supported.
- Full macOS app-shell integration (menu bar UX + hotkeys + lifecycle UX) is still separate from this core wrapper package.
- Weekly dependency drift currently captures snapshots and runs tests, but does not yet enforce automatic threshold-based fail policies for performance deltas.
- Long-run stability campaign automation (high-cycle soak tests) is not yet fully operationalized as a separate CI gate.

## Overall Readiness (Internal Validation)
Current branch status supports controlled internal validation with strong fail-closed and recoverability posture:
- Core reliability controls: implemented
- Security/trust controls: implemented
- Hebrew and PDF pathways: implemented with documented constraints
- Spreadsheet selective anonymization: implemented
- UI surfaces: implemented
- Test baseline: green
