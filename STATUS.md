# CoWork Shield Fork Status Report

## Snapshot
- Date: 2026-02-24
- Repo: `GreggBerretta/cowork-shield-fork`
- Branch: `codex/handoff-b-status-doc-clean`
- Scope Baseline: `HANDOFF_B.md`
- Execution Layer: HANDOFF_B core + Phase 2 v11 launch-prep additions

## Executive Status
The fork is in a strong validation state with hardened fail-closed behavior and expanded governance/monetization controls.

Implemented and validated in this branch:
- deterministic replay + model hash lock
- fail-closed restore with hallucination/mutation blocking
- column-selective spreadsheet anonymization
- Hebrew support (auto/spacy/stanza/transformers pathways)
- PDF input-only conversion pipeline (PDF -> MD/DOCX)
- hybrid IPC core (Mode A stdio, Mode B AF_UNIX)
- Textual TUI + Gradio UI
- EC-15 state integrity harness
- logging/observability guardrails (sanitized logs, signed audit events)

New v11 launch-prep additions in this update:
- Free TTL policy hardening (`24h` fixed) + Pro TTL cap (`<= 30 days`)
- workspace governance commands: close/recover/purge + self-destruct-on-restore toggle
- auditor-safe sanitization reports after operations
- Pro-gated report export (JSON/PDF)
- benchmark command + CI performance gate workflow
- native menu-bar shell Swift target scaffold (`cowork-shield-menubar`)
- opt-in local crash-report capture for handled wrapper failures

## Feature Coverage

### Core File Support
- `.txt`: anonymize/restore
- `.md`: anonymize/restore
- `.csv`: anonymize/restore + column-selective mode
- `.xlsx`: anonymize/restore + formula preservation + lossy chart/image gate
- `.docx`: anonymize/restore
- `.pdf`: anonymize only (input-only), output to `.md`/`.docx`

### Spreadsheet Selective Controls
- `--columns` supports letters and headers
- `inspect-columns` preflight available
- `--detect-pii/--no-detect-pii` interaction enforced
- column token namespace separated from PII token namespace

### Governance v1
- `workspace close <name>` creates encrypted snapshot under `~/.safeai/backups/<workspace_id>/`
- `workspace recover --workspace <name> <backup-path>` restores vault snapshot
- `workspace purge <name>` performs mandatory backup then clears mappings/records
- `workspace set-governance <name> --self-destruct-on-restore` supported
- `workspace report show` and Pro-gated `workspace report export --format json|pdf`

### Licensing / Monetization Policy
- license key validation available in CLI/UI/IPC paths
- free-tier restore quota tracking with visible counters
- Pro gates enforced for:
  - column-selective mode
  - advanced Hebrew backends
  - long TTL
  - report export

### Wrapper / Native Shell
- Wrapper core remains state-machine based with protocol validation
- New Swift executable target:
  - `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldMenuBar/main.swift`
  - status item, workspace switching, clipboard actions, login toggle, UI launch hooks
- Sparkle updater path is currently a safe fallback (release page open) pending full Sparkle linking

## Validation Results

### Python Test Suite
- Command: `uv run pytest -q`
- Result: **296 passed, 0 failed**

### Swift Wrapper Build
- Command: `swift build` (in `wrapper/CoWorkShieldWrapper`)
- Result: **PASS**

### Wrapper Invariant Harness
- Command: `swift run wrapper-invariant-checks`
- Result: **PASS**

## Performance Gate Results (Current Build)

Benchmark command used:
- `uv run cowork-shield benchmark-performance --rows 10000 --language en --output /tmp/cws_perf_en.json`
- `uv run cowork-shield benchmark-performance --rows 10000 --language he --output /tmp/cws_perf_he.json`

Measured:
- English 10k CSV anonymize: **48.95s** (target <= 8s) -> FAIL
- Hebrew 10k CSV anonymize: **20.00s** (target <= 8s) -> FAIL
- English 10k CSV restore: **0.16s** (target <= 2s) -> PASS
- Hebrew 10k CSV restore: **0.14s** (target <= 2s) -> PASS
- Clipboard round-trip: **0.17-0.18s** (target <= 1.5s) -> PASS

## Critical Remaining Gap
The remaining launch-blocking technical gap is large-file CSV anonymize latency.

What is done already:
- row-batched detector invocation in CSV/XLSX handlers
- restore fast-path skips for non-token cells
- benchmark tooling + CI gate added

What still needs focused engine work:
- deeper detector batching beyond row-level
- regex-first short-circuit for high-confidence entities
- optional accuracy/performance profile selection for large structured sheets

## Key Paths Updated in This Pass
- `src/cowork_shield/cli.py`
- `src/cowork_shield/licensing.py`
- `src/cowork_shield/workspace/manager.py`
- `src/cowork_shield/pipeline/anonymize.py`
- `src/cowork_shield/pipeline/restore.py`
- `src/cowork_shield/clipboard/operations.py`
- `src/cowork_shield/governance/reporting.py`
- `src/cowork_shield/handlers/csv_handler.py`
- `src/cowork_shield/handlers/xlsx.py`
- `src/cowork_shield/performance/benchmark.py`
- `wrapper/CoWorkShieldWrapper/Package.swift`
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldMenuBar/main.swift`
- `.github/workflows/performance-gate.yml`
- `INSTALL.md`
- `TROUBLESHOOTING.md`
- `PERFORMANCE.md`

## Overall
Trust and recoverability controls are strong and test-backed.
The main unresolved commercialization risk is anonymize throughput on 10k-row CSV full-detection workflows.
