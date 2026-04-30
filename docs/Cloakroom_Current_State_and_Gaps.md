# Cloakroom Current State and Gap Catalog

Date: 2026-04-29

Scope: Step 1 assessment of the final PRD/status documents against the local Cloakroom checkout and the GitHub repository.

## Sources Reviewed

- Final PRD: `/Users/greggberretta/Downloads/Cloakroom_Master_PRD.docx`
- Final status/gates doc: `/Users/greggberretta/Downloads/Cloakroom_Status_Testing_and_Release_Gates.docx`
- Local repo: `/Users/greggberretta/Documents/New project/Cloakroom`
- GitHub repo: `https://github.com/GreggBerretta/Cloakroom`
- Current local branch assessed: `feature/rename-to-cloakroom`
- Validation run locally during this assessment:
  - `uv run pytest -q` -> 297 passed, 1 warning
  - `swift build` in `wrapper/CloakroomWrapper` -> pass
  - `swift run wrapper-invariant-checks` -> pass

## Bottom Line

Cloakroom is not just a concept or a shell. The local repo contains a substantial, test-backed local anonymization engine with reversible tokenization, encrypted local vaults, CLI workflows, spreadsheet/document handlers, IPC, governance commands, benchmark tooling, and a Swift wrapper scaffold.

The strongest part of the product today is the local Python engine and CLI. The weakest part is "presentable software solution" readiness: the GitHub default branch is not the current Cloakroom branch, the native Mac app is still closer to a scaffold than a polished app, several PRD-level security/governance invariants are only partially implemented, and the business/customer packaging story is not finished.

For internal engineering, the right conclusion is: continue from `feature/rename-to-cloakroom`, but do not treat the GitHub default branch or current packaging as beta-ready without cleanup and hardening.

## Repository State

| Area | Current state | Assessment |
| --- | --- | --- |
| GitHub visibility | Repo is public: `GreggBerretta/Cloakroom` | Good to know for anything security/commercial. Confirm this is intentional before customer data or proprietary docs land in the repo. |
| GitHub default branch | `codex/handoff-b-status-doc` | Problem. The default branch is not `main` and not the current `feature/rename-to-cloakroom` branch. New clones land on an older/diverged branch. |
| Local branch | `feature/rename-to-cloakroom` | Clean working tree and in sync with `origin/feature/rename-to-cloakroom`. |
| Open PRs/issues | None found on GitHub | No tracked engineering backlog in GitHub issues/PRs. |
| Current branch CI on GitHub | Latest visible runs on `feature/rename-to-cloakroom` are EC-15 only | Local full tests are green, but GitHub full CI/security/performance gates are not clearly running on the current feature branch because workflow push triggers mostly target `main` and `codex/**`. |
| Version metadata | `src/cloakroom/__init__.py` says `0.2.0`; `pyproject.toml` exposes `0.1.0`; CLI reports `0.1.0` | Needs cleanup before release. |

## What Is Built

### Core Engine

Implemented and locally validated:

- Python package under `src/cloakroom`.
- CLI entry point: `cloakroom`.
- Reversible anonymize/restore pipeline.
- Deterministic token generation with bracketed tokens like `[PERSON_00001]`.
- HMAC-backed token verification.
- Fail-closed restore behavior for corrupted HMACs, hallucinated tokens, mutated tokens, dropped tokens, and incomplete restoration.
- Workspace-scoped shared identity mappings across files.
- Detection model hash lock and replay mismatch protections.
- Operation locking for workspace operations.
- Local sanitized logging and signed audit events.

Main evidence:

- `src/cloakroom/pipeline/anonymize.py`
- `src/cloakroom/pipeline/restore.py`
- `src/cloakroom/tokenizer/generator.py`
- `src/cloakroom/verification/verifier.py`
- `tests/test_pipeline/`
- `tests/test_state_integrity/test_ec15_state_integrity.py`

### Supported Formats

Implemented:

- TXT and Markdown anonymize/restore.
- CSV anonymize/restore with dialect preservation.
- XLSX anonymize/restore with formula skipping/preservation.
- XLSX backup creation and lossy chart/image warning gate.
- DOCX anonymize/restore with run redistribution.
- Clipboard anonymize/restore through Python CLI commands.
- PDF input-only flow to Markdown or DOCX.

Important nuance:

- PDF support exceeds the final PRD's "not native PDF parsing" scope, but it is still input-only. Restore from PDF is intentionally rejected.

### Detection

Implemented:

- Presidio/spaCy-backed detection.
- Language choices: `auto`, `en`, `he`.
- Hebrew backend choices: `auto`, `spacy`, `stanza`, `transformers`.
- Regex prefilter for high-confidence entities like email, phone, credit card, US SSN, and Israeli 9-digit ID patterns.
- Detection modes: `speed`, `balanced`, `accurate`.
- Entity count reporting can distinguish Hebrew-script values in report summaries.

Partial:

- The final PRD names first-class Hebrew/Israeli classes such as `HE_PERSON`, `TEUDAT_ZEHUT`, `IL_PHONE`, `IL_ADDRESS`, and `IL_BANK_ACCOUNT`.
- Current code maps Hebrew model labels into the generic `EntityType` enum. For example, `TEUDAT_ZEHUT` maps to `US_SSN`, and there are no distinct `IL_PHONE`, `IL_ADDRESS`, or `IL_BANK_ACCOUNT` entity types in `EntityType`.

### Vault And Recovery

Implemented:

- AES-256-GCM encrypted vault files.
- macOS Keychain-backed master key storage.
- Key derivation separation for vault encryption and token HMACs.
- Atomic vault writes.
- Workspace TTL enforcement.
- Workspace close, recover, purge, cleanup, export-key, import-key, and security verification commands.
- Encrypted vault backup snapshots under `~/.cloakroom/backups/<workspace_id>/`.
- Self-destruct-on-restore governance toggle.

Main evidence:

- `src/cloakroom/vault/`
- `src/cloakroom/workspace/manager.py`
- `src/cloakroom/vault/recovery.py`
- `tests/test_vault/`
- `tests/test_workspace/test_manager_governance.py`

### Governance, Audit, And Reporting

Implemented:

- Signed audit log entries with HMAC verification.
- Sanitization report JSONL generation.
- Report viewing/export in JSON and basic PDF form.
- Pro gating for report export.
- Entity count summaries that handle column-specific and Hebrew-script values.

Partial:

- Audit events are signed, but there is no hash chain across events.
- Sanitization reports are not signed or hash chained.
- Sanitization reports store `file_path` directly. The final PRD calls for hashed filenames only, not unhashed paths.
- Report append writes are not fully atomic and report failures are logged as warnings rather than treated as release-blocking acknowledgement failures.

### Licensing / Edition Gates

Implemented:

- Free vs Pro policy checks in CLI/UI/IPC paths.
- Free TTL fixed at 24 hours.
- Pro TTL cap at 30 days.
- Pro gating for column-selective anonymization, advanced Hebrew backends, and audit/report export.
- Free restore quota tracking.

Partial:

- Pro validation is local and pattern/env-var based (`pro_...` keys), not a production-grade entitlement system.
- No purchase, license provisioning, revocation, customer account, or offline enterprise licensing workflow is present.
- No legal/model-weight license review artifact was found in the repo.

### UI Surfaces

Implemented:

- CLI with anonymize, restore, clipboard, logs, onboarding, benchmark, workspace, report, and recovery-key commands.
- Textual TUI scaffold.
- Gradio local web UI bound to `127.0.0.1`.
- Entity preview/table rendering through UI helper code.
- Risk confirmations for lossy XLSX/PDF/force re-anonymize flows in the web UI.

Partial:

- The UI is functional/internal, not yet a polished business-customer product UI.
- The final PRD's human-in-the-loop ingest dialog and durable attestation capture are not fully implemented. `AttestationRecord` exists in the data model, but the workflow does not appear to write real attestation records during anonymization.
- Behavioral prompt fields exist in the vault model, but no prompt engine/workflow was found.

### Swift Wrapper / Native Menu Bar

Implemented:

- Swift package under `wrapper/CloakroomWrapper`.
- Library target plus executables:
  - `wrapper-invariant-checks`
  - `cloakroom-menubar`
- Wrapper state machine with `UNINITIALIZED`, `ENGINE_HANDSHAKE`, `READY`, `BUSY`, `HARD_FAIL`, and `SHUTDOWN`.
- Protocol envelope validation.
- Hybrid IPC client supporting subprocess stdio and UNIX domain socket modes.
- Stdio and UNIX socket transports.
- Anti-false-success result gate.
- Clipboard guard implementation with zeroing buffer and changeCount checks.
- Sleep/wake handling logic in the controller.

Partial:

- The menu bar action path currently calls engine clipboard operations through IPC and passes `clipboardVerified: true`; it does not visibly use the Swift `ClipboardGuard` in the production menu flow.
- Heartbeat primitives exist, but no active heartbeat timer/loop was found in the menu bar app.
- Wake handling currently passes hardcoded `healthCheckPassed: true` and `vaultIntegrityPassed: true`, rather than performing real engine/vault checks.
- Explicit recovery from `HARD_FAIL` exists in the state machine but is not surfaced as a polished recovery UX.
- Sparkle updater is a fallback that opens GitHub releases, not a linked updater.
- There is no signed/notarized `.app`, installer, launch agent packaging, or deployment artifact in the repo.

### Testing And Gates

Implemented and currently green locally:

- Python unit/integration/state tests: 297 passed.
- Swift build: passed.
- Swift wrapper invariant harness: passed.
- GitHub workflows exist for CI, EC-15, performance, security scan, and weekly trust gate.

Partial:

- Current branch GitHub runs show EC-15 success, but not a full current-branch CI/security/performance run.
- Performance gate exists, but I did not rerun the benchmark during this assessment because it touches the system clipboard. The repo's own status docs report revised 10k CSV performance as passing.
- No real LLM multi-pass mutation harness was found. Existing hallucination/mutation tests are synthetic and valuable, but not the full external LLM acceptance gate described in the status doc.

## Gaps Against The Final PRD

| PRD area | Status | What is left |
| --- | --- | --- |
| Source of truth | Partial | Make `feature/rename-to-cloakroom` or its successor the default branch, merge needed changes to `main`, and align repo docs with the final PRD/status docs. |
| Product naming | Mostly built | Code is rebranded, but branch/default-branch state and older handoff docs still create confusion. Version metadata also needs alignment. |
| Presentable Mac product | Partial | Package the menu bar app as a real macOS app, sign/notarize it, provide install/update flow, and make it usable without developer commands. |
| Core reversible engine | Strong | Keep hardening, but the core engine is the strongest part of the repo. |
| Crash atomicity | Partial | The code rolls back on handled exceptions, but crash-at-any-point consistency between output files and vault commit is not fully proven. Consider staging output plus transaction markers or recovery reconciliation. |
| Vault governance | Partial | Add startup/background cleanup cadence, harden destructive workflows, avoid raw paths in reports, and make report/audit acknowledgement rules match the PRD. |
| Audit safety | Partial | Replace raw `file_path` in reports with hashes or safe display names, add hash-chain/tamper evidence to reports, and add tests that filenames containing PII cannot leak. |
| Clipboard security | Partial | Wire Swift `ClipboardGuard` into actual menu-bar operations, clear visible clipboard during processing, verify changeCount in production, and scrub previous-session signatures on launch. |
| Wrapper hard-fail behavior | Partial | Add active heartbeat checks, real wake health/vault checks, a recovery UI, and end-to-end tests against a running engine. |
| Hebrew/Israeli entity coverage | Partial | Add first-class Israeli entity taxonomy and tests for `TEUDAT_ZEHUT`, `IL_PHONE`, `IL_ADDRESS`, `IL_BANK_ACCOUNT`, and Hebrew-person reporting semantics. |
| Human review/attestation | Partial | Build the ingest review dialog as a real required workflow for sensitive operations and persist zero-PII attestation records. |
| Behavioral metrics | Mostly schema only | Implement prompt/response workflows or explicitly remove them from current release scope. |
| Commercial packaging | Partial | Replace local regex license checks with a real entitlement strategy or document an offline-license model. Complete third-party model/license review. |
| Confidential information beyond PII | Missing/undefined | Decide whether v1 promises only PII/structured identifiers or also configurable confidential business terms. If the latter, add custom dictionaries, per-customer patterns, and review UX. |
| LLM mutation acceptance | Partial | Build real multi-pass LLM mutation tests using representative outputs and define the release threshold as a repeatable gate. |
| CI/release gates | Partial | Ensure full CI/security/performance gates run on the release branch and default branch. Fix the branch filters that skip `feature/rename-to-cloakroom` pushes. |
| Support/release docs | Partial | `INSTALL.md`, `TROUBLESHOOTING.md`, and pilot docs exist, but need a final beta runbook tied to the actual packaged app and final branch. |

## Suggested Engineering Backlog

### P0 - Make The Repo Usable As A Source Of Truth

- Choose the release branch strategy: likely promote `feature/rename-to-cloakroom` into `main`.
- Set GitHub default branch to the chosen branch.
- Update workflow branch filters so CI/security/performance gates run on the release branch.
- Align versions: `pyproject.toml`, `src/cloakroom/__init__.py`, wrapper expected engine version, docs, and tags.
- Add the final PRD/status docs or derived markdown summaries to the repo.

### P1 - Close Security/Governance Gaps Before Beta

- Remove raw `file_path` from sanitization reports; use file hash and safe metadata only.
- Add tamper evidence to sanitization reports, not only audit logs.
- Add tests for file paths containing names, emails, client names, and Hebrew text.
- Implement real crash recovery/reconciliation for anonymized-output-without-vault and vault-without-output cases.
- Define whether report write failures must abort operations or be retried in a release-safe queue.

### P1 - Make Clipboard And Wrapper Match The PRD

- Integrate `ClipboardGuard` into the actual menu-bar clipboard flow.
- Add real active heartbeat scheduling in the menu bar app.
- Replace hardcoded wake health checks with live engine/vault checks.
- Surface explicit recovery after `HARD_FAIL`.
- Add end-to-end wrapper tests against the Python engine in both stdio and socket modes.

### P1 - Build The Presentable Local Product

- Turn the Swift executable into a signed/notarized `.app`.
- Add app icon, first-run onboarding, workspace selection, license entry, and clear success/failure states.
- Decide whether Gradio remains internal-only or is removed from customer-facing packaging.
- Add update/install strategy: Sparkle, Homebrew, MDM-friendly package, or another agreed path.

### P2 - Complete Product Promise Around Detection

- Add first-class Israeli entity types and tests.
- Add configurable confidential-term dictionaries/patterns if the business promise includes more than standard PII.
- Finish attestation capture and durable zero-PII review records.
- Add real LLM mutation and multi-pass restore acceptance tests.

### P2 - Commercial/Legal Readiness

- Complete model-weight/license review for spaCy, Presidio, Hebrew models, Stanza, Transformers, pdfplumber, reportlab, Gradio, Textual, and Swift dependencies. PyMuPDF was removed in favor of pdfplumber (MIT) + reportlab (BSD) to avoid the AGPL/commercial licensing decision.
- Decide on offline vs online license entitlement.
- Create a beta support runbook with recovery-key, vault purge/recover, audit export, and escalation procedures.

## Rough Effort To Presentable

These are planning estimates, not commitments:

| Outcome | Rough effort |
| --- | ---: |
| Clean source-of-truth branch, versioning, and CI gates | 1-2 days |
| Governance/report/audit hardening | 3-6 days |
| Clipboard/wrapper hardening | 1-2 weeks |
| Packaged Mac menu bar beta app | 1-2 weeks |
| Attestation and review UX | 3-7 days |
| Israeli entity taxonomy and tests | 3-7 days |
| Real LLM mutation gate | 3-5 days for first harness, longer with real customer corpora |
| Commercial/legal/license readiness | 1-2 weeks cross-functional |

My practical read: Cloakroom can likely become a presentable closed-pilot tool in about 3-5 focused engineering weeks after branch cleanup. A commercially credible business-customer release is more likely 6-10 weeks, mainly because packaging, wrapper hardening, audit guarantees, licensing, and legal review matter as much as core anonymization code.

