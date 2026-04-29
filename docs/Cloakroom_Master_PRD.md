# Cloakroom

## Master Product & Architecture PRD

Authoritative consolidation of prior CoWork Shield product, vault, wrapper, and commercialization drafts.

Status: Working master document for forward development.
Scope: macOS CLI + native menu bar app in heavily firewalled corporate environments.
Prepared from pasted PRDs, wrapper addenda, performance review, and gap analyses.

This document replaces overlapping prior drafts by defining a single source of truth for product scope, architecture, security invariants, vault governance, wrapper requirements, and edition boundaries.

Naming decision: CoWork Shield is retired as the working name. The master product name is Cloakroom. All future requirements, engineering specs, status notes, and test artifacts should inherit that name.

## 1. Product Definition

### Mission

Cloakroom is a professional anonymizer/de-anonymizer software package that lets corporate users safely send sensitive content to LLMs by replacing protected information with deterministic, human-readable tokens and then restoring the original values with fail-closed verification.

### What the product is

Cloakroom is a reversible semantic transformation layer, not a simple redaction utility and not a general-purpose DLP policy engine. It exists to preserve reasoning utility while preventing uncontrolled disclosure outside the corporate boundary.

### Primary value

Use AI on real corporate or client data without rewriting the output afterward, while maintaining zero-tolerance standards for corruption on restore.

## 2. Product Principles

- Deterministic restoration is the core promise. A single incorrect restore is a product-level failure.
- Local-first processing is mandatory. Raw source data and reversible mappings stay on managed local infrastructure unless a future enterprise key-management mode is explicitly enabled.
- Structure preservation beats destructive export/import. Files should remain usable in their native form whenever possible.
- Automation is allowed only when it remains visible, reversible, and audit-safe.
- The wrapper is a security boundary. It must not pretend success when the engine or protocol state is uncertain.
- Cloakroom must work in heavily firewalled corporate environments with minimal external dependencies at runtime.

## 3. Target Users and Core Jobs

### Initial target users

- Consultants, analysts, operators, accountants, legal-adjacent knowledge workers, and internal corporate teams handling sensitive documents.
- Users who routinely copy data into LLMs, compare documents with AI assistance, or draft deliverables that must later be restored to original names, identifiers, dates, and financial references.

### Core jobs to be done

1. Analyze sensitive spreadsheets and reports with external or internal LLMs without exposing raw protected information.
2. Draft final customer-facing or management-facing documents using tokenized content and then restore the original facts deterministically.
3. Maintain shared identity consistency across multiple files inside a workspace so the same entity maps to the same token everywhere.
4. Generate auditor-safe evidence that sanitization happened, without creating a second toxic data store in logs.

## 4. Deployment Scope and Editions

### Primary deployment profile

- macOS is the primary supported platform.
- CLI is the foundational interface.
- A native Swift menu bar app is the primary local GUI.
- Embedded Python engine remains the transformation core.

### Edition boundaries

- Free tier: core CLI, basic local use, 24-hour vault TTL, view-only reporting where applicable.
- Pro tier: configurable TTL, audit export, advanced Hebrew backends, column-selective spreadsheet controls, longer-lived workspaces, and related commercial features.
- Enterprise tier is future scope only: centralized KMS, shared workspaces, broader policy administration, and deeper compliance packaging.

## 5. System Architecture

### End-to-end flow

`User file or clipboard -> detection -> deterministic tokenization -> anonymized output -> LLM processing -> HMAC-verified reverse lookup -> deterministic restoration -> original file or clipboard`

### Core components

- Detection engine: Presidio-backed entity detection with configurable language/back-end support.
- Tokenization layer: deterministic, human-readable tokens such as `PERSON_001` or `HE_PERSON_001`, with HMAC verification per mapping.
- Encrypted vault: AES-256-GCM protected local mapping store with key material in macOS Keychain only.
- Workspace manager: shared token namespace across related files, with lifecycle controls and TTL enforcement.
- Verification layer: pre-flight integrity checks, leftover-token scans, and atomic temp-file commit rules.
- Swift wrapper: protocol client, OS integration layer, clipboard lifecycle controller, and release-blocking security boundary.

## 6. Supported Formats and Content Classes

### Supported inputs

- CSV with dialect preservation.
- XLSX with cell-level handling, formula preservation, and explicit chart/image loss warnings where library limitations apply.
- DOCX with paragraph-level detection and run redistribution to preserve formatting.
- Plain text and clipboard flows.

### Current limitations

- Native PDF parsing is not in current scope; PDF support should rely on conversion pipelines where needed.
- Spreadsheet formulas must never be modified. PII embedded inside formulas remains a known limitation until separately designed.
- Third-party library limitations that can alter non-text workbook objects must trigger explicit warnings and backup creation.

## 7. Detection Coverage

### Baseline entities

- `PERSON`, `ORGANIZATION`, `LOCATION`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `US_SSN`, `CREDIT_CARD`, `DATE_TIME`, `IP_ADDRESS`, `URL`.

### Hebrew and Israeli coverage

- Expanded support includes `HE_PERSON`, `TEUDAT_ZEHUT`, `IL_PHONE`, `IL_ADDRESS`, and `IL_BANK_ACCOUNT`.
- `hebrew_backend` must support `auto`, spaCy-based Hebrew, Stanza, and transformer-backed modes where licensed and pinned.
- RTL content must preserve readability and restoration integrity in DOCX, XLSX, plain text, and clipboard flows.

### Spreadsheet-selective handling

- Column-selective controls must allow users to target specific spreadsheet columns while leaving other columns untouched or optionally applying general PII detection to non-selected columns.
- Audit summaries must account for column-qualified and Hebrew-qualified protection classes, not just generic English entity types.

## 8. Security and Reliability Invariants

- Zero incorrect restores. Restore must abort rather than guess.
- Byte-identical deterministic replay for the same input and workspace state where required by acceptance testing.
- No partial restores. All restore operations must use temp output plus verification before final commit.
- No master keys on disk.
- No plaintext logging.
- No silent retries that can disguise state divergence.
- No success UI without verified protocol, workspace, and clipboard conditions.

### Atomicity rules

- Vault commit is the final step of anonymize operations.
- Crash at any point must not leave mismatched file and vault state.
- Audit writes and attestation writes must themselves be atomic and only acknowledged after commit confirmation.

## 9. Vault Governance

### Purpose

Vault Governance is part of the core Cloakroom product, but only in its local-first commercialization form. It exists to minimize persistent sensitive mappings, provide auditor-safe reporting, and keep reversible workflows commercially sellable in corporate environments without overreaching into premature enterprise infrastructure.

### Required capabilities

- Time-to-live per workspace, with a default of 24 hours and a Pro-controlled configurable window up to the approved commercial limit.
- Optional self-destruct-on-restore behavior that purges mappings immediately after a successful restore.
- Manual vault purge that retains zero-PII audit metadata only.
- Encrypted backup prior to destructive purge unless the user explicitly declines in a knowingly destructive workflow.
- Automatic cleanup on startup, on access, and on background cadence as implemented by the lifecycle manager.
- Tamper-evident audit logs with hashed filenames and entity-count summaries only.

### Governance boundaries

- Vault governance must extend the existing local encrypted vault; it does not replace it.
- It must not break deterministic replay, recovery-key export/import, or other core recoverability paths.
- Centralized KMS and shared workspaces are explicitly future enterprise scope and are not part of the current master release scope.

### Audit record model

Sanitization reports must be metadata-only. They may include timestamp, workspace identifier, file hash, entity-count breakdown, action type, and integrity chain metadata. They must not include original values, reversible tokens, or unhashed filenames.

## 10. Wrapper Architecture

### Wrapper role

The Swift wrapper is not a decorative shell. It is a state machine, protocol client, clipboard security controller, and OS integration boundary.

### Required states

`UNINITIALIZED -> ENGINE_HANDSHAKE -> READY -> BUSY -> HARD_FAIL -> SHUTDOWN`

### Required behaviors

- Reject malformed protocol responses, schema drift, request mismatches, and protocol-version mismatches.
- Disable operations and require explicit recovery after `HARD_FAIL`.
- Clear clipboard defensively on hard-fail paths.
- Lock workspace access during in-flight operations and prohibit reentrancy.
- Validate heartbeat health and suspend or fail appropriately on sleep/wake and engine-health events.

### IPC decision

The master decision is hybrid IPC. Cloakroom must support subprocess plus stdin/stdout for immediate compatibility with existing TUI and Gradio-based integration paths, while also supporting UNIX domain sockets for the native menu bar app and longer-term hardened integration.

### Payload extensibility

- Payloads must support `columns`, `detect_pii`, `hebrew_backend`, `pdf_output_format`, `force_reanonymize`, `reason`, and `license_key` where relevant.
- Wrapper success presentation must depend on engine confirmation plus protocol validation plus clipboard verification where applicable.

## 11. Clipboard and Local UX

- Clipboard anonymize and restore flows must copy content into zeroing memory buffers, clear the visible clipboard during processing, confirm OS `changeCount` transitions, and only then write the resulting payload.
- Original plaintext clipboard contents must not linger after anonymization completion.
- Previous-session plaintext signatures found on launch must be purged.
- Menu bar operations must remain transparent, reversible, and visibly scoped to the active workspace.

### Human-in-the-loop review

The ingest dialog is part of the local trust model. It provides entity preview, attestation capture, and explicit user acknowledgment for high-sensitivity workflows. Attestation logs remain local, structured, and zero-PII.

## 12. Observability and Behavioral Metrics

- All behavioral metrics are local-only and encrypted with workspace metadata.
- Tracked signals may include anonymizations, restores, aborts, trust-flip responses, rewrite-avoidance responses, shipped-work signals, workspace-recall patterns, attestation friction, and time-to-close after restore.
- Behavioral metrics must not be confused with PII mappings and should follow the metadata retention policy rather than the mapping retention policy.

## 13. Non-Goals

- Windows and Linux support.
- Cloud sync of vaults or telemetry.
- System-wide background interception as part of the current release scope.
- Enterprise KMS and shared real-time workspaces in the current release.
- Native PDF parsing as a first-class current feature.
- A broad corporate policy engine or full DLP replacement.

## 14. Acceptance Criteria

- Zero incorrect restores in unit, integration, and beta usage.
- 100 percent formula preservation in supported spreadsheet workflows.
- Byte-identical deterministic replay for the approved acceptance cases.
- Clipboard round trip at or below 1.5 seconds in the target environment.
- 10k-row CSV anonymization performance brought into the approved target window before broad external beta.
- Multi-pass LLM mutation handling meeting the approved cumulative restore threshold.
- Tamper-evident, zero-PII audit logs and reports.
- Wrapper hard-fail and anti-false-success behaviors fully covered by red-team and state-machine tests.

## 15. Immediate Implementation Order

1. Lock product naming and rename all future references to Cloakroom.
2. Stabilize the engine as the canonical transformation core and preserve current recoverability guarantees.
3. Implement vault governance as a local-first extension, not a replacement.
4. Implement hybrid wrapper IPC with state-machine enforcement and clipboard security.
5. Bring Hebrew and column-selective coverage into both product behavior and audit summaries.
6. Add edition gating where required for commercial packaging.
7. Use the separate status and release-gates document as the operational companion to this PRD.
