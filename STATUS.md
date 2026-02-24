# Cloakroom Status Report

## Snapshot
- Date: 2026-02-24
- Repo: `GreggBerretta/cloakroom`
- Branch: `feature/rename-to-cloakroom`
- Scope Baseline: `HANDOFF_B.md`
- Execution Layer: HANDOFF_B core + Phase 2 v11 launch-prep additions
- Performance Baseline Revision: post-optimization detection pipeline (regex prefilter + batched detection + canonicalized NER caching)

## Executive Status
The repository is in a strong validation state with hardened fail-closed behavior and expanded governance/monetization controls.

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
- native menu-bar shell Swift target scaffold (`cloakroom-menubar`)
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
- `workspace close <name>` creates encrypted snapshot under `~/.cloakroom/backups/<workspace_id>/`
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
  - `wrapper/CloakroomWrapper/Sources/CloakroomMenuBar/main.swift`
  - status item, workspace switching, clipboard actions, login toggle, UI launch hooks
- Sparkle updater path is currently a safe fallback (release page open) pending full Sparkle linking

## Validation Results

### Python Test Suite
- Command: `uv run pytest -q`
- Result: **297 passed, 0 failed**

### Swift Wrapper Build
- Command: `swift build` (in `wrapper/CloakroomWrapper`)
- Result: **PASS**

### Wrapper Invariant Harness
- Command: `swift run wrapper-invariant-checks`
- Result: **PASS**

## Performance Baselines (Revised)

### Prior Baseline (Pre-Optimization)
- English 10k CSV anonymize: **48.95s** (FAIL)
- Hebrew 10k CSV anonymize: **20.00s** (FAIL)
- 10k CSV restore: **0.14-0.16s** (PASS)
- Clipboard round-trip: **0.17-0.18s** (PASS)

### Current Baseline (Post-Optimization, 2026-02-24)
Benchmark command used:
- `uv run cloakroom benchmark-performance -w perf-opt2-en-balanced --rows 10000 --language en --detection-mode balanced -o /tmp/cloakroom_perf2_en_balanced.json`
- `uv run cloakroom benchmark-performance -w perf-opt2-en-speed --rows 10000 --language en --detection-mode speed -o /tmp/cloakroom_perf2_en_speed.json`
- `uv run cloakroom benchmark-performance -w perf-opt2-he-balanced --rows 10000 --language he --detection-mode balanced -o /tmp/cloakroom_perf2_he_balanced.json`
- `uv run cloakroom benchmark-performance -w perf-opt2-he-speed --rows 10000 --language he --detection-mode speed -o /tmp/cloakroom_perf2_he_speed.json`

Measured:
- English 10k CSV anonymize (balanced): **1.96s** (target <= 8s) -> PASS
- English 10k CSV anonymize (speed): **1.95s** (target <= 8s) -> PASS
- Hebrew 10k CSV anonymize (balanced): **1.71s** (target <= 8s) -> PASS
- Hebrew 10k CSV anonymize (speed): **1.60s** (target <= 8s) -> PASS
- 10k CSV restore: **0.19-0.22s** (target <= 2s) -> PASS
- Clipboard round-trip: **0.14-0.23s** (target <= 1.5s) -> PASS

Delta vs prior baseline:
- English anonymize: **48.95s -> 1.96s** (~96.0% faster)
- Hebrew anonymize: **20.00s -> 1.71s** (~91.4% faster)

## Key Paths Updated in This Pass
- `src/cloakroom/cli.py`
- `src/cloakroom/licensing.py`
- `src/cloakroom/workspace/manager.py`
- `src/cloakroom/pipeline/anonymize.py`
- `src/cloakroom/pipeline/restore.py`
- `src/cloakroom/clipboard/operations.py`
- `src/cloakroom/governance/reporting.py`
- `src/cloakroom/handlers/csv_handler.py`
- `src/cloakroom/handlers/xlsx.py`
- `src/cloakroom/performance/benchmark.py`
- `wrapper/CloakroomWrapper/Package.swift`
- `wrapper/CloakroomWrapper/Sources/CloakroomMenuBar/main.swift`
- `.github/workflows/performance-gate.yml`
- `INSTALL.md`
- `TROUBLESHOOTING.md`
- `PERFORMANCE.md`

## Overall
Trust, recoverability, and performance controls are strong and test-backed.
Current build meets the Phase 2 v11 launch performance budgets for CSV anonymize/restore and clipboard round-trip.
