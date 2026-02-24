# Cloakroom — Project Handoff Document

**Version**: 0.2.0
**Date**: February 22, 2026
**Repo**: https://github.com/GreggBerretta/cloakroom (private)

---

## What Is This?

Cloakroom is a reversible document anonymization tool. It replaces personally identifiable information (PII) in documents with deterministic tokens (e.g., "John Smith" becomes `PERSON_00001`), lets you safely send the anonymized document through an LLM, then restores the original values afterward.

Key guarantees:
- **Deterministic**: Same person always gets the same token within a workspace
- **Reversible**: Every anonymization can be perfectly undone
- **Fail-closed**: If anything looks wrong during restoration, the entire operation aborts — no partial results
- **Encrypted at rest**: All mappings stored in AES-256-GCM encrypted vault, keys in macOS Keychain

---

## Tech Stack

- **Python 3.12** (managed with `uv`)
- **Presidio** + **spaCy** (`en_core_web_lg`) for PII detection
- **cryptography** library for AES-256-GCM encryption + HKDF key derivation
- **Click** for CLI, **Rich** for terminal UI
- **openpyxl** for Excel, **python-docx** for Word
- **keyring** for macOS Keychain integration
- **pytest** for testing, **ruff** for linting

---

## Project Structure

```
src/cloakroom/
  __init__.py              # Version 0.2.0
  cli.py                   # Click CLI (anonymize, restore, workspace commands)
  models.py                # All dataclasses (VaultData v2.0, Token, EntityMapping, etc.)
  exceptions.py            # Exception hierarchy (11 exception types)
  detection/
    engine.py              # Presidio wrapper for PII detection
    entity_types.py        # Entity type registry, normalization, mapping keys
  tokenizer/
    generator.py           # Deterministic HMAC-tagged token generation
    replacer.py            # Offset-aware text replacement engine
  vault/
    vault.py               # Encrypted vault manager
    crypto.py              # AES-256-GCM encrypt/decrypt, HKDF derivation
    atomic.py              # Atomic file writes (write-to-temp + rename)
    keychain.py            # macOS Keychain wrapper
    migration.py           # Vault version migration (1.0 -> 2.0)
  verification/
    verifier.py            # HMAC verification + remaining-token scanner
  handlers/
    base.py                # FileHandler protocol
    csv_handler.py         # CSV anonymization/restoration
    xlsx.py                # Excel handler (preserves formulas)
    docx.py                # Word handler (paragraph detection + run redistribution)
  pipeline/
    anonymize.py           # Anonymization orchestration
    restore.py             # Fail-closed restoration pipeline
  workspace/
    manager.py             # Workspace lifecycle management

tests/                     # 123 tests, all passing
  conftest.py              # Shared fixtures
  test_models.py           # Model serialization + v2 fields
  test_exceptions.py       # Exception hierarchy
  test_detection/          # PII detection tests
  test_tokenizer/          # Token generation + text replacement tests
  test_vault/              # Crypto, vault persistence, migration tests
  test_verification/       # HMAC verification + token scanning tests
  test_handlers/           # CSV, XLSX, DOCX handler tests
  test_pipeline/           # End-to-end anonymize/restore tests
```

**By the numbers**: 28 source files (2,458 LOC), 23 test files (1,695 LOC), 123 tests passing.

---

## What's Done

### Phase 1 — Core Engine (Complete)

Everything needed for file-based anonymization and restoration via CLI:

1. **PII Detection** — Presidio-based detection for 10 entity types (person, org, email, phone, SSN, credit card, date, IP, URL, location). Configurable score threshold (default 0.7). Overlap resolution keeps highest-scored entity.

2. **Token System** — Deterministic tokens (`PERSON_00001`, `ORG_00002`) with HMAC-SHA256 integrity tags. Same value + same type = same token across all files in a workspace. 5-digit zero-padded counters (supports 99,999 entities per type).

3. **Format Handlers**:
   - **CSV**: Auto-detects dialect, processes cell-by-cell, preserves dialect on write
   - **XLSX**: Preserves formulas (skips formula cells), skips numeric cells, creates backup before processing
   - **DOCX**: Paragraph-level detection with run-level redistribution to preserve formatting. Handles body paragraphs, tables, and headers/footers

4. **Encrypted Vault** — AES-256-GCM encrypted JSON vault with atomic writes. Master key stored in macOS Keychain. HKDF-derived separate keys for HMAC and vault encryption.

5. **Fail-Closed Restoration** — Pre-flight HMAC verification of all mappings, restoration to temporary file, post-flight scan for remaining tokens. Only commits if all checks pass.

6. **Workspace Management** — Named workspaces with TTL expiry. Multiple files share token mappings within a workspace. CLI commands: `anonymize`, `restore`, `workspace list/show/delete/cleanup`.

### Phase 2, Sprint 1 — Foundation (Complete)

Laying groundwork for Phase 2 features:

1. **Token Counter Overflow Fix** — Widened from 3-digit (`_001`) to 5-digit (`_00001`). Regex patterns updated to `\d{3,5}` for backward compatibility with any existing v1 tokens.

2. **Docx Header/Footer Bug Fix** — Inverted logic was processing linked headers (which inherit content and have nothing unique) instead of unlinked ones (which have their own content).

3. **VaultData v2.0** — 15 new fields added to `VaultData` for observability, behavioral prompts, attestation tracking, detection model hashing, and token ABI versioning. Full `to_dict()`/`from_dict()` support with safe defaults for backward compatibility.

4. **New Dataclasses** — `AttestationRecord` (tracks user review of detected entities before anonymization) and `HallucinationFlag` (tracks AI-generated or mutated tokens found in restored text).

5. **Vault Migration** — `vault/migration.py` automatically upgrades v1.0 vaults to v2.0 on load. Infers `anonymize_count` from existing file records. All new fields get safe defaults.

6. **New Exceptions** — `HallucinationDetectedError`, `AttestationAbortedError`, `BackupError`, `ModelHashMismatchError`, `IPCError`.

---

## What's Left

### Sprint 2 — Deterministic Replay & Detection Version Lock (~1 week)

**Goal**: Guarantee byte-identical anonymization output across runs and pin detection model versions.

- **Clock abstraction**: Replace global `now_iso()` with a `Clock` protocol. Add `FrozenClock` for deterministic replay testing. Backward-compatible — existing callers unchanged.
- **Replay flag**: `--replay` CLI flag that sets a frozen clock using the timestamp from the previous run's `FileRecord`, then verifies SHA-256 of output matches the recorded hash.
- **Model hash computation**: Hash spaCy model weights, store in `vault_data.model_hashes`. On subsequent runs, verify the model hasn't changed (raise `ModelHashMismatchError` on mismatch, `--force` to override).

**Key files to modify**: `models.py` (Clock protocol), `detection/engine.py` (model hash), `pipeline/anonymize.py` (hash check + replay), `cli.py` (--replay flag).

### Sprint 3 — Observability & Behavioral Prompts (~1 week)

**Goal**: Instrument pipelines with usage counters and implement a local-only behavioral prompt system.

- **Counter instrumentation**: Increment `anonymize_count`, `restore_count`, `abort_count` in the pipeline after each operation. Update `last_used` timestamp.
- **Behavioral prompts**: A `PromptEngine` that shows dismissible prompts at specific triggers (post-restore, daily, weekly). Records responses in vault data. Three initial prompts: trust-flip, rewrite-avoidance, pre-LLM-capture.
- **Validity filters**: Filter out exploratory/testing usage data (< 3 operations, repeated same-file hashing).
- **Stats CLI**: Add `--stats` and `--behavior` flags to `workspace show`.

**New files**: `observability/prompts.py`, `observability/filters.py`, `observability/metadata.py`.

### Sprint 4 — Hallucination Detection & Flagging (~1 week)

**Goal**: Detect AI-hallucinated, mutated, and dropped tokens during restoration.

- **Hallucination detector**: Scan restored text for token-shaped strings not in the vault. Classify as "hallucinated" (valid format, not in vault), "mutated" (close match to a real token via `difflib`), or "dropped" (token in anonymized input missing from output).
- **Inline formatter**: Replace flagged tokens with `[WARNING AI GENERATED: PERSON_99999]` or `[WARNING MUTATED: PERSN_00001 -> PERSON_00001?]`.
- **Pipeline integration**: Run hallucination detection between restoration and commit in `restore.py`. Extend `RestoreResult` with `hallucination_flags` list.

**New files**: `hallucination/detector.py`, `hallucination/formatter.py`.

### Sprint 5 — Clipboard Operations & Interactive Attestation (~1 week)

**Goal**: Shield/restore clipboard text and add a TUI-based entity review before anonymization.

- **Plain text handler**: New `TextHandler` for raw text (no file format overhead).
- **Clipboard operations**: Read via `pbpaste`, anonymize, write via `pbcopy`. Reverse for restore. New `clipboard shield` and `clipboard restore` CLI commands.
- **Attestation TUI**: Rich-based interactive review showing detected entities in a table. User confirms before anonymization proceeds. Records `AttestationRecord` in vault. Triggered by `--attest` flag on `anonymize` command.

**New files**: `handlers/text_handler.py`, `clipboard/operations.py`, `attestation/interactive.py`.

### Sprint 6 — Vault Backup/Recovery & Audit Export (~1 week)

**Goal**: Workspace close with encrypted backup, recovery from backup, and PII-free audit export.

- **Backup**: Copy encrypted vault to `~/.cloakroom/backups/<workspace_id>/` with non-PII metadata.
- **Recovery**: Load vault from backup directory using Keychain key (key must still be present).
- **Audit export**: Generate JSON or CSV summary with operation counts, attestation events, and file records — no PII included. New CLI commands: `workspace close`, `workspace recover`, `workspace export --audit-summary`.

**New files**: `vault/backup.py`, `audit/export.py`.

### Sprint 7 — IPC Protocol (Python Side) (~1 week)

**Goal**: Build the JSON-line stdin/stdout protocol that the Swift menu bar app will use to talk to the Python engine.

- **Protocol**: `IPCRequest`/`IPCResponse` dataclasses with JSON-line serialization.
- **Command registry**: Decorator-based handler registration. Initial commands: `shield_clipboard`, `restore_clipboard`, `list_workspaces`, `workspace_stats`.
- **Server loop**: Reads from stdin, dispatches commands, writes responses to stdout. Signals readiness on startup.
- **Entry point**: New `cloakroom-ipc` script in pyproject.toml.

**New files**: `ipc/protocol.py`, `ipc/commands.py`, `ipc/server.py`.

### Sprint 8 — Swift Menu Bar App (~2 weeks)

**Goal**: Native macOS menu bar app for one-click clipboard anonymization.

- **StatusBar controller**: NSStatusItem with shield icon. Menu items for shield/restore clipboard, workspace selection, preferences, quit.
- **PythonBridge**: Spawns the Python IPC server as a subprocess. Sends JSON-line requests, receives responses. Async/await Swift concurrency.
- **Keyboard shortcuts**: Global hotkeys (Cmd+Shift+S to shield, Cmd+Shift+R to restore) via the KeyboardShortcuts SPM package.
- **Review dialog**: SwiftUI popover showing detected entities for attestation before anonymization.
- **Packaging**: PyInstaller bundles the Python engine into a standalone binary. Swift app looks for it in the app bundle, `~/.local/bin/`, or falls back to `python3 -m`.

**New directory**: `CloakroomMenuBar/` (Xcode project, separate from the Python source).

### Sprint 9 — Performance Benchmarks & LLM Mutation Testing (~1 week)

**Goal**: Verify performance gates and build the LLM mutation test harness.

- **Performance benchmarks**: 10k-row CSV in < 10s, clipboard operation in < 1.5s. Benchmark runner with pass/fail thresholds.
- **LLM mutation protocol**: Multi-pass test (anonymize -> LLM -> restore, 3 cycles). Criteria: 0 dropped tokens, 0 un-flagged mutations, 100% hallucinations flagged, >= 99.5% single-pass restore success.

**New files**: `benchmarks/runner.py`, `tests/mutation/llm_mutation_test.py`.

---

## Estimated Remaining Effort

| Sprint | Scope | Duration |
|--------|-------|----------|
| 2 | Deterministic replay, model version lock | ~1 week |
| 3 | Observability counters, behavioral prompts | ~1 week |
| 4 | Hallucination detection and flagging | ~1 week |
| 5 | Clipboard operations, attestation TUI | ~1 week |
| 6 | Vault backup/recovery, audit export | ~1 week |
| 7 | IPC protocol (Python side) | ~1 week |
| 8 | Swift menu bar app | ~2 weeks |
| 9 | Performance benchmarks, LLM mutation tests | ~1 week |
| **Total** | | **~10 weeks** |

Sprints 2-7 are pure Python and can be done by anyone comfortable with the existing codebase. Sprint 8 requires Swift/SwiftUI/AppKit experience. Sprint 9 requires access to an LLM API for the mutation testing harness.

---

## How to Get Running

```bash
# Clone and set up
git clone https://github.com/GreggBerretta/cloakroom.git
cd cloakroom
uv sync

# Download the spaCy model (required for PII detection)
uv run python -m spacy download en_core_web_lg

# Run tests
uv run pytest

# Try the CLI
uv run cloakroom anonymize path/to/file.csv -w my-workspace
uv run cloakroom restore path/to/file.anonymized.csv -w my-workspace
uv run cloakroom workspace list
```

---

## Architecture Decisions Worth Knowing

1. **No Presidio AnonymizerEngine** — We only use Presidio for detection. Token replacement is entirely ours (deterministic, HMAC-tagged, reversible). Presidio's anonymizer is lossy and non-deterministic.

2. **Right-to-left replacement** — Entities are replaced from the end of the string backward to preserve earlier character offsets. This is critical for correct offset handling.

3. **Paragraph-level detection, run-level redistribution (DOCX)** — Word splits text across runs unpredictably. We concatenate all runs in a paragraph for detection, then redistribute the modified text back across runs to preserve formatting.

4. **Fail-closed restoration** — Restoration always goes to a temp file first. If any HMAC fails or any token remains unreplaced, the temp file is deleted and the operation aborts. The output file is never in a partial state.

5. **Vault migration on load** — The vault automatically upgrades on read. There is no separate migration command. The `migrate_vault_data()` function is additive (never removes fields) and idempotent.

6. **Keychain-based key management** — Master keys are never written to disk. They live in macOS Keychain, indexed by workspace ID. If the Keychain entry is lost, the vault is unrecoverable. This is by design.

---

## Known Issues / Technical Debt

- **Pre-existing lint warnings**: ~15 ruff warnings in Phase 1 code (unused imports, unused variables). Non-blocking but should be cleaned up.
- **No plain text (.txt) handler**: Currently only CSV, XLSX, DOCX. The text handler planned for Sprint 5 will add this.
- **openpyxl chart/image risk**: openpyxl may drop charts or images when saving. The backup is created automatically, but there's no explicit warning to the user yet.
- **No stdin/pipe support**: CSV anonymization currently requires a file path. Pipe mode is planned for Sprint 5.
- **Token format in documents**: Tokens like `PERSON_00001` could theoretically collide with natural document content. A bracket-wrapped format (`[PERSON_00001]`) is a possible future enhancement.
