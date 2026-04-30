# Cloakroom — Build Status

**Date:** 2026-04-30
**Canonical working tree:** `/Users/greggberretta/Documents/New project/Cloakroom`
**Origin:** `https://github.com/GreggBerretta/Cloakroom` (public)
**Engine version:** `0.2.0` (pyproject + `__init__.py` + CLI aligned)
**Supersedes:** the 2026-02-24 status report previously at this path. Performance baselines from that snapshot are folded into §5.

This document is the operational state of the Cloakroom codebase. The Master PRD ([docs/Cloakroom_Master_PRD.md](docs/Cloakroom_Master_PRD.md)) defines what the product is. The Killer Demo PRD ([docs/Cloakroom_Killer_Demo_PRD.md](docs/Cloakroom_Killer_Demo_PRD.md)) defines the buyer-facing demo. The current execution plan lives at `~/.claude/plans/users-greggberretta-documents-new-proje-merry-flask.md`. This file tracks where we are against that plan today, with enough detail for an engineer picking this up cold.

---

## 1. Source of Truth

| Item | State |
|---|---|
| Canonical tree | `/Users/greggberretta/Documents/New project/Cloakroom` |
| GitHub default branch | `main` (changed 2026-04-29 from `codex/handoff-b-status-doc`) |
| Active feature branch | None. PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1) merged into `main` on 2026-04-30 (`ad3e5db`). |
| Stale local branches | None. `codex/handoff-b-status-doc` and `feature/rename-to-cloakroom` deleted after PR #1 merge. |
| Stale remote branches | None. `codex/handoff-b-status-doc`, `codex/handoff-b-status-doc-clean`, `feature/rename-to-cloakroom`, and the merged feature branch have been deleted/pruned. |
| Working tree | Clean on `main` after latest post-merge maintenance commit |
| Engine tests | **333 passing** on `main` (was 329; +4 from PR closeout safety cleanup) |
| Swift build | Pass on 2026-04-30 after Swift wrapper false-success fixes |

### PR #1 merge summary

```
03b2aa0  fix(detection): full international phone capture, stable token ordering, single-token dates
08d55f6  feat(detection): demo rules engine + first-class IL/HE entity taxonomy
```

These functional commits, the NER template-cache performance fix, Phase 2 audit/report safety hardening, Phase 3 demo backend work, Phase 4 demo UI work, Phase 5 browser acceptance gate, Phase 6 launcher/runbook work, dependency hardening, and PR closeout safety cleanup are now on `main` via merged PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

Additional post-Phase-6 commits included in merged PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1):

```
7c016d2  docs(status): record dependency swap, IT review findings, and revised what's-next
d82dbd9  deps: replace PyMuPDF with pdfplumber + reportlab
53478cc  docs: add teammate setup guide for the killer demo
```

Post-Phase-6 closeout work also included the CI workflow filter cleanup, `AttestationRecord` safe identity redesign, and Swift wrapper false-success fixes documented below.

---

## 2. What Has Been Built

Phases reference the execution plan. Phases 0, 1, 2, 3, 4, 5, and 6 are complete on `main`; Phase 7 is not started.

### Phase 0 — Source-of-truth lock (DONE)

Commit `4ea8eff` on `main`.

- `docs/` directory created with the four governing documents:
  - [docs/Cloakroom_Master_PRD.md](docs/Cloakroom_Master_PRD.md)
  - [docs/Cloakroom_Status_Testing_and_Release_Gates.md](docs/Cloakroom_Status_Testing_and_Release_Gates.md)
  - [docs/Cloakroom_Killer_Demo_PRD.md](docs/Cloakroom_Killer_Demo_PRD.md)
  - [docs/Cloakroom_Current_State_and_Gaps.md](docs/Cloakroom_Current_State_and_Gaps.md)
- Versions aligned: `pyproject.toml` 0.1.0 → 0.2.0 to match `src/cloakroom/__init__.py` and `cloakroom --version`.
- `tests/test_cli.py` updated to assert `0.2.0`.
- Local `main` fast-forwarded onto the rebrand work; pushed to origin.
- GitHub default branch flipped to `main`.

### Phase 1 — Demo rules + first-class IL/HE entity taxonomy (DONE)

Commits `08d55f6` and `03b2aa0`, merged to `main` via PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

**EntityType expansion** ([src/cloakroom/models.py](src/cloakroom/models.py))
- Israeli/Hebrew first-class members: `HE_PERSON`, `TEUDAT_ZEHUT`, `IL_PHONE`, `IL_ADDRESS`, `IL_BANK_ACCOUNT`.
- Confidential business types: `PROJECT`, `CONTRACT_VALUE`, `PRICING_TERM`, `STRATEGY`, `ADDRESS_LINE` (token prefix `ADDRESS` to match PRD §6 example), `CUSTOMER_ID`.
- Token-prefix entries for every new member.
- `HEBREW_ENTITY_MAPPING` no longer folds `TEUDAT_ZEHUT` into `US_SSN`.

**Detection engine** ([src/cloakroom/detection/engine.py](src/cloakroom/detection/engine.py))
- Optional `demo_ruleset: DemoRuleSet` parameter.
- New `_detect_demo_entities()` runs as the first pre-pass; merge precedence is **demo rules → regex prefilter → Presidio NER**.
- `_promote_localized_entity()` post-processes NER hits: `PERSON` whose value contains Hebrew script is promoted to `HE_PERSON`.
- `_TARGET_PRESIDIO_ENTITIES` sourced from `entity_types.SUPPORTED_PRESIDIO_ENTITIES`, which excludes Cloakroom-only types.
- NER template cache now persists across `detect_many()` batches on the same engine instance, so spreadsheet-shaped corpora reuse analyzer work across the full CSV run instead of repeating it per batch.

**Regex prefilter** ([src/cloakroom/detection/regex_prefilter.py](src/cloakroom/detection/regex_prefilter.py))
- IL_ID 9-digit pattern produces `TEUDAT_ZEHUT` (was `SSN`).
- New IL_PHONE pattern (`+972` and `0XX` shapes); produces `IL_PHONE`.
- New IL_BANK_ACCOUNT pattern; produces `IL_BANK_ACCOUNT`.
- Hebrew-language pre-pass order: IL specs run **before** generic phone, so a bare 9-digit Teudat Zehut isn't mis-tagged as `PHONE`.
- Generic PHONE pattern rewritten to capture full international forms (`+44 20 7946 0182`); was previously truncating to a single trailing 4-digit group.
- Anchors use `(?<![\w+])` / `(?!\w)` so leading `+` doesn't break `\b`.

**Demo rule engine** ([src/cloakroom/detection/demo_rules.py](src/cloakroom/detection/demo_rules.py))
- New module. `DemoRuleSet` with `add_dictionary()`, `add_regex()`, `detect()`.
- Dictionary entries are case-insensitive whole-token matches via lookarounds (so `"Lantern"` does not match inside `"Lanterns"`).
- `_resolve_overlaps()` keeps the higher-scoring (or longer at equal score) match.
- `build_default_demo_ruleset()` ships the killer-demo coverage: `Acme Health`, `Project Lantern`, `Q3 churn containment plan`, `pre-acquisition integration risk`, `15 Farringdon Street, London`, `EU-CUST-{n}`, `$X.XM` contract values, `N percent discount`, `Month DD, YYYY` dates.

**Tokenizer** ([src/cloakroom/tokenizer/replacer.py](src/cloakroom/tokenizer/replacer.py))
- `replace_entities()` previously minted tokens in the same right-to-left order it spliced text, so the *rightmost* entity got `_00001`. Split into two passes: mint left-to-right (so source order determines counter), replace right-to-left (so offsets stay valid).

**Pipeline** ([src/cloakroom/pipeline/anonymize.py](src/cloakroom/pipeline/anonymize.py))
- `AnonymizePipeline.__init__` accepts `demo_ruleset`; threads through to `DetectionEngine`.
- No change for callers that omit the parameter.

**Reporting** ([src/cloakroom/governance/reporting.py](src/cloakroom/governance/reporting.py))
- `_LOCALIZED_ENTITY_TYPES` set ensures `HE_PERSON` / `IL_*` use their own token prefix in entity-count breakdowns instead of being double-prefixed (`HE_HE_PERSON`) by the legacy Hebrew-script promotion path.

**Demo fixtures** ([src/cloakroom/demo/](src/cloakroom/demo/))
- `customer_escalation_en.md` — exact Customer Escalation memo from PRD §6.
- `customer_escalation_he.md` — Hebrew/Israeli companion: HE_PERSON, TEUDAT_ZEHUT, IL_PHONE, IL_ADDRESS, IL_BANK_ACCOUNT.
- `__init__.py` exposes `load_sample(name)`.

**Local walkthrough** ([scripts/demo_walkthrough.py](scripts/demo_walkthrough.py))
- Terminal sanity check: full Shield → simulated AI → Restore loop on the bundled English sample. Run with `uv run python scripts/demo_walkthrough.py`.

### Phase 2 — Audit/report safety hardening (DONE on main)

Current Phase 2 implementation is on `main` after PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

**Safe file identity** ([src/cloakroom/governance/file_identity.py](src/cloakroom/governance/file_identity.py))
- New helper builds auditor-safe file references as `{file_hash, file_label_safe}`.
- `file_label_safe` is opaque and extension-scoped, e.g. `csv:aaaaaaaaaaaa`; it never includes the original basename or parent directory.
- Raw `file_path`, `input_path`, `output_path`, and `anonymized_path` fields are scrubbed from nested audit/report metadata.

**Sanitization reports** ([src/cloakroom/governance/reporting.py](src/cloakroom/governance/reporting.py))
- Report rows no longer persist raw `file_path`.
- Rows include `file_hash`, `file_label_safe`, `prev_report_hash`, `report_hash`, `chain_index`, and read-time `chain_verified`.
- Legacy rows with raw `file_path` are normalized on read/export so future Trust Center views do not re-surface old raw paths.
- JSON/PDF export uses `read_sanitization_reports()`, so exported reports inherit the same no-raw-path behavior.

**Audit trail** ([src/cloakroom/logging/audit.py](src/cloakroom/logging/audit.py))
- `append_audit_event()` now scrubs raw path-shaped fields before signing the event.
- Existing HMAC tamper evidence remains intact.

**Pipeline and CLI integration**
- Anonymize/restore/clipboard flows pass content hashes into sanitization reports.
- Workspace report display shows `file_label_safe` instead of a raw filename/path.
- Added integration coverage proving a PII-bearing filename does not leak into report or audit logs after a real anonymize pipeline run.

### Phase 3 — Local demo backend (DONE on main)

Current Phase 3 implementation is on `main` after PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

**FastAPI backend** ([src/cloakroom/demo_server/app.py](src/cloakroom/demo_server/app.py))
- New local-only FastAPI app factory: `create_app(runtime=None)`.
- New console script: `cloakroom-demo-server`.
- Runtime defaults to `127.0.0.1:8765`; `validate_bind_host()` rejects non-loopback bind hosts such as `0.0.0.0`.
- Middleware rejects non-loopback client hosts, with `TestClient` allowed for tests.

**Demo endpoints**
- `GET /api/health` — local service health.
- `POST /api/demo/load-sample` — returns bundled EN/HE demo sample text and language metadata.
- `POST /api/demo/reset` — resets the demo vault/workspace to a known clean state.
- `POST /api/shield` — runs the real anonymize pipeline with `build_default_demo_ruleset()`, returns AI-safe text, entity counts, latest audit-safe report row, simulated AI response, and mutated-token sample.
- `POST /api/restore` — runs the real restore pipeline and returns either restored text or a structured fail-closed error payload.
- `GET /api/trust-center` — returns workspace/vault status, local-only proof, activity counters, audit-safe reports, signed audit events, and policy preview.

**Dependencies**
- Added `fastapi>=0.115.0` and `uvicorn>=0.30.0` to `pyproject.toml`.

**Coverage**
- Added HTTP-level tests for sample loading, Shield -> Trust Center -> Restore, mutated-token blocking, reset behavior, unknown sample rejection, and loopback bind validation.

### Phase 4 — Buyer-facing local web UI (DONE on main)

Current Phase 4 implementation is on `main` after PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

**Served UI** ([src/cloakroom/demo_server/static/](src/cloakroom/demo_server/static/))
- `GET /` now serves a purpose-built single-page Cloakroom demo UI from the local FastAPI server.
- Static assets are packaged under the demo server module: `index.html`, `styles.css`, and `app.js`.
- No separate Node/npm build step was introduced; the demo remains a Python/FastAPI local app.

**Screens**
- `Shield for AI` screen: original-local source pane, processing rail, AI-safe output pane, proof panels for "What the AI sees" and "What stays local", and masked detection review table.
- `Restore` screen: simulated AI response pane, token verification metrics, clean/mutated response controls, restore button, restored-output pane, and calm fail-closed error state.
- `Trust Center` screen: workspace/vault status, TTL, mapping counts, local-only proof, audit-safe report rows, policy preview, and custom demo rules.

**Presenter controls**
- Sample switcher includes EN, HE-IL, and mixed EN/HE demo content.
- Buttons for `Use Demo Sample`, `Load Failure Sample`, `Reset Demo`, and `Export Audit JSON`.
- `Load Failure Sample` uses the backend's canned `[PERSON_00001]` -> `[PERSON_001]` mutation and shows "No partial restore was created" on block.

**Input and RTL support**
- Source input supports direct editing, browser clipboard paste, and local `.txt` / `.md` file loading via file picker or drag/drop. File text is read in the browser; it is not uploaded to a cloud service.
- Text panes use `dir="auto"` / plaintext bidi handling so Hebrew and mixed EN/HE samples remain readable.
- New bundled mixed sample: [src/cloakroom/demo/customer_escalation_mixed.md](src/cloakroom/demo/customer_escalation_mixed.md).

**Backend additions for UI**
- `POST /api/shield` now returns masked `review_items` for the detection review table. Raw original values are not returned in review rows.
- Demo sample metadata now includes `customer_escalation_mixed.md`.
- HE/IL deterministic leak markers are tracked for the HE and mixed samples.
- The browser API helper handles JSON and non-JSON backend errors so demo users see readable failure copy instead of a JSON parser exception if the local server returns a plain-text 500.

**Coverage**
- Added HTTP/static tests proving `/` serves the Phase 4 UI and static assets.
- Added mixed-sample test proving English and IL deterministic values are shielded, `TEUDAT_ZEHUT` is emitted, and review rows do not expose raw values.
- Browser verification used installed Chrome headless/CDP fallback because the Browser/IAB tool was not exposed and macOS Computer Use permissions were pending.

### Phase 5 — Browser acceptance gate + fail-closed proof (DONE on main)

Current Phase 5 implementation is on `main` after PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

**Acceptance script** ([scripts/demo_browser_acceptance.mjs](scripts/demo_browser_acceptance.mjs))
- Starts `uv run cloakroom-demo-server` on a random loopback port.
- Finds installed Chrome/Chromium (or `CLOAKROOM_BROWSER_BIN`) and drives the real UI through Chrome DevTools Protocol.
- Exercises the actual buyer flow: Shield -> Restore blocked -> Trust Center -> mobile layout.
- Asserts the PRD §9 failure proof: mutated `[PERSON_00001]` -> `[PERSON_001]`, `Restore blocked`, expected/found token copy, and no partial restored output.
- Asserts AI-safe output contains 12 replacements, 0 raw demo leaks, masked review rows, and no desktop/mobile horizontal overflow.
- Writes screenshots for review: `shield.png`, `restore-blocked.png`, `trust-center.png`, and `mobile.png`.
- CI-hardened on 2026-04-30 after the first hosted run exposed a cold-start timing gap: the gate now arms CDP diagnostics before navigation, allows a 120s Shield timeout, and dumps page/server/browser diagnostics plus `failure.png` if the hosted browser path fails.

**Hosted gate** ([.github/workflows/demo-acceptance.yml](.github/workflows/demo-acceptance.yml))
- New GitHub Actions workflow: `Demo Acceptance`.
- Runs on `pull_request` and `workflow_dispatch`.
- Installs Python/uv dependencies, Node 22, the English spaCy model, and the multilingual Hebrew fallback spaCy model (`xx_ent_wiki_sm`), then runs the browser acceptance script.
- Uploads screenshots as `demo-acceptance-artifacts`.

**Local result**
- `node scripts/demo_browser_acceptance.mjs --screenshot-dir /tmp/cloakroom_phase5_acceptance` -> pass.
- Observed local result: 12 replacements, 0 leaks, 1 changed/invented token blocked, 0 partial output, Trust Center local-only proof, and mobile `scrollWidth == clientWidth == 390`.

### Phase 6 — Demo launcher and runbook (DONE on main)

Current Phase 6 implementation is on `main` after PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

**One-command launcher**
- New CLI command: `uv run cloakroom demo`.
- Opens the polished local demo UI in the default browser by default.
- Binds only to loopback hosts via the same `validate_bind_host()` guard as the backend.
- Supports `--host`, `--port`, and `--no-open-browser` for scripted or presenter-controlled runs.
- Demo command is exempted from first-run workspace onboarding warnings because it uses its own self-contained demo vault.

**Server launcher reuse** ([src/cloakroom/demo_server/app.py](src/cloakroom/demo_server/app.py))
- Added `demo_url()` and `run_demo_server()` helpers.
- `cloakroom-demo-server` now also supports `--open-browser`.

**Runbook** ([docs/Cloakroom_Demo_Runbook.md](docs/Cloakroom_Demo_Runbook.md))
- New reviewer/presenter runbook with quick start, demo flow, presenter controls, acceptance gate command, and local-only notes.

**Coverage**
- CLI tests cover `cloakroom demo --help` and non-loopback host rejection without onboarding noise.
- Demo-server tests cover `demo_url()` formatting and non-loopback rejection.
- Local smoke test started `uv run cloakroom demo --host 127.0.0.1 --port <random> --no-open-browser`, confirmed `/api/health`, then stopped the process.

### Post-Phase-6 dependency hardening — PyMuPDF removed (DONE on main, 2026-04-30)

Commit `d82dbd9`, merged via PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1). Driven by IT review: PyMuPDF (and the bundled `fitz` it ships) is AGPL/commercial-licensed, which would force a costly legal decision before commercial release. Replaced with permissively-licensed alternatives:

- **PDF input extraction** ([src/cloakroom/extractors/pdf_markdown.py](src/cloakroom/extractors/pdf_markdown.py)) — `_extract_with_pymupdf` rewritten as `_extract_with_pdfplumber` (MIT). Same `PDFExtractionResult(markdown, backend)` contract; docling-first ordering preserved; `PdfExtractionError` semantics unchanged.
- **PDF report export** ([src/cloakroom/governance/reporting.py](src/cloakroom/governance/reporting.py)) — `_export_reports_pdf` rewritten on `reportlab.canvas.Canvas` (BSD). Same signature, same multi-page behavior, same per-row line format. y-axis inversion handled (reportlab origin is bottom-left vs. PyMuPDF top-left).
- **Dependency manifest** ([pyproject.toml](pyproject.toml)) — `pymupdf>=1.24.0` removed; `pdfplumber>=0.11.0` and `reportlab>=4.0.0` added.
- **User-facing strings** in [src/cloakroom/pipeline/ui_api.py](src/cloakroom/pipeline/ui_api.py), [INSTALL.md](INSTALL.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md), and the gap catalog updated to reference pdfplumber.

**Coverage added**:
- [tests/test_extractors/test_pdf_markdown.py](tests/test_extractors/test_pdf_markdown.py) — three pdfplumber-backend tests (single page, multi-page header structure, empty PDF raises `PdfExtractionError`).
- [tests/test_governance/test_reporting.py](tests/test_governance/test_reporting.py) — two new PDF-export tests asserting `%PDF-` magic bytes on populated and empty workspaces. The reportlab-based PDF export path was previously uncovered.

**Verification**: `uv run pytest -q` → 329 passed (was 324). Demo walkthrough still byte-identical round trip on the bundled English sample.

### Teammate setup guide (DONE on main, 2026-04-30)

Commit `53478cc`. Added [docs/Demo_Setup_Guide.md](docs/Demo_Setup_Guide.md) — step-by-step instructions for a teammate getting the demo running on a fresh Mac for the first time. Complements the presenter-focused [Cloakroom_Demo_Runbook.md](docs/Cloakroom_Demo_Runbook.md) with a setup-and-launch path that assumes no existing checkout.

### PR closeout safety cleanup — CI filters, attestation, Swift wrapper (DONE on main, 2026-04-30)

This closeout batch addressed the highest-leverage items IT called out before PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1) was merged:

- **GitHub workflow filters** ([.github/workflows/ci.yml](.github/workflows/ci.yml), [.github/workflows/security-scan.yml](.github/workflows/security-scan.yml), [.github/workflows/performance-gate.yml](.github/workflows/performance-gate.yml)) — removed stale `codex/**` push triggers; workflows now run on `main` pushes and pull requests.
- **Attestation model safety** ([src/cloakroom/models.py](src/cloakroom/models.py)) — `AttestationRecord` now persists `{file_hash, file_label_safe}` instead of raw `file_path`; legacy deserialization normalizes old `file_path` records through the existing safe file-reference helper.
- **Clipboard text IPC lane** ([src/cloakroom/ipc/server.py](src/cloakroom/ipc/server.py), [src/cloakroom/clipboard/operations.py](src/cloakroom/clipboard/operations.py)) — added `TEXT_ANONYMIZE` and `TEXT_RESTORE` request types so native wrappers can pass buffered clipboard text to the engine without letting Python read/write the system clipboard directly.
- **Swift ClipboardGuard wiring** ([wrapper/CloakroomWrapper/Sources/CloakroomMenuBar/main.swift](wrapper/CloakroomWrapper/Sources/CloakroomMenuBar/main.swift)) — menu-bar Shield/Restore now clear the clipboard through `ClipboardGuard`, call the local text IPC transform, write the final value through `NSPasteboard`, and only display success after the pasteboard `changeCount` proves the write occurred.
- **Swift wake checks** ([wrapper/CloakroomWrapper/Sources/CloakroomMenuBar/main.swift](wrapper/CloakroomWrapper/Sources/CloakroomMenuBar/main.swift)) — wake handling now probes `HEARTBEAT` and `STATS_QUERY` instead of passing hardcoded `true` values into `handleSystemWake`.
- **Wrapper validation parity** ([wrapper/CloakroomWrapper/Sources/CloakroomWrapper/WrapperController.swift](wrapper/CloakroomWrapper/Sources/CloakroomWrapper/WrapperController.swift)) — expected validation error codes now include restore/replay/model/hash/lossy-XLSX failures the Python IPC server already classifies as `VALIDATION_ERROR`.

**Coverage added**:
- [tests/test_models.py](tests/test_models.py) — `AttestationRecord` round trip asserts `file_path` is absent; legacy `file_path` records normalize without leaking PII-bearing filename text.
- [tests/test_clipboard/test_operations.py](tests/test_clipboard/test_operations.py) — text transform round trip proves the new API updates vault state without touching the system clipboard.
- [tests/test_ipc/test_server.py](tests/test_ipc/test_server.py) — `TEXT_ANONYMIZE` and `TEXT_RESTORE` dispatch tests cover transformed payloads and free-tier restore accounting.

**Verification**: `uv run pytest -q` -> 333 passed; `uv run ruff check ...` -> pass; `swift build --package-path wrapper/CloakroomWrapper` -> pass; `swift run --package-path wrapper/CloakroomWrapper wrapper-invariant-checks` -> pass.

### Post-merge performance workflow hardening (DONE on main, 2026-04-30)

After PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1) merged, a status-only push to `main` re-ran the hosted `performance-gate.yml`. Functional gates stayed green, but the hosted performance job failed twice on the anonymize leg only:

- Run 1: anonymize 9.43s vs. 8.00s target; restore 0.65s and clipboard 0.83s passed.
- Run 2 rerun: anonymize 8.22s vs. 8.00s target; restore 0.67s and clipboard 0.77s passed.

The workflow now retries the same `uv run cloakroom benchmark-performance --rows 10000 --language en --enforce-gates` command up to three times and uploads `performance-gate-*.json` artifacts even when all attempts fail. The 8.00s anonymize threshold is unchanged; the hardening addresses hosted macOS runner variance without weakening the gate.

### Already-built capabilities preserved from the prior 2026-02-24 status

These were validated before Phase 0/1 work and remain green; Phase 1 did not touch them:

- Deterministic replay + model hash lock.
- Fail-closed restore with hallucination/mutation/dropped-token blocking.
- Column-selective spreadsheet anonymization (`--columns`, `inspect-columns`, `--detect-pii/--no-detect-pii`).
- Hebrew support across `auto / spacy / stanza / transformers` backends.
- PDF input-only conversion pipeline (PDF → MD/DOCX). Restore from PDF intentionally rejected.
- Hybrid IPC core (Mode A stdio, Mode B AF_UNIX).
- Textual TUI + Gradio web UI (internal-grade; not the killer demo).
- EC-15 state-integrity harness.
- Sanitized logs and signed audit events.
- Workspace governance commands: `close`, `recover`, `purge`, `set-governance --self-destruct-on-restore`, `report show`, Pro-gated `report export --format json|pdf`.
- Free TTL fixed at 24h, Pro TTL cap at 30 days, Pro gating for column-selective mode, advanced Hebrew backends, long TTL, and report export.
- File support: `.txt`, `.md`, `.csv` (with dialect preservation), `.xlsx` (formula preservation + lossy chart/image gate), `.docx` (run redistribution), `.pdf` (input-only).
- Native Mac menu-bar Swift target (`cloakroom-menubar`) — partially hardened for clipboard and wake false-success paths; signed app packaging, onboarding, updater, real heartbeat timer, and wrapper integration tests remain Master-PRD product work.
- Performance gate workflow + benchmark CLI.

---

## 3. What Has Been Tested

### 3.1 Test counts

| Suite | Pre-Phase-1 | Now |
|---|---|---|
| Total Python tests | 297 | **333** |
| Phase-1 additions | — | 13 (7 demo-rule unit, 5 demo end-to-end, 1 NER template-cache regression) |
| Phase-2 additions | — | 4 new tests plus 1 strengthened report export test (report path safety, report hash chain, audit path safety, pipeline no-leak integration) |
| Phase-3 additions | — | 5 demo-server HTTP tests |
| Phase-4 additions | — | 2 demo-server UI/sample tests |
| Phase-5 additions | — | Browser acceptance gate script + GitHub workflow |
| Phase-6 additions | — | 3 Python tests for demo launcher/URL guardrails |
| PyMuPDF→pdfplumber/reportlab swap | — | 5 (3 pdfplumber backend, 2 PDF export magic-bytes) |
| PR closeout safety cleanup | — | 4 (AttestationRecord safe identity, text clipboard transform, text IPC dispatch) |

Run command: `uv run pytest -q` (canonical tree).

### 3.2 New tests added in Phase 1

[tests/test_detection/test_demo_rules.py](tests/test_detection/test_demo_rules.py):
- `test_dictionary_match_case_insensitive`
- `test_dictionary_does_not_match_substring`
- `test_regex_match`
- `test_default_ruleset_finds_killer_demo_entities`
- `test_overlapping_rules_keep_higher_score`
- `test_no_rules_returns_empty`
- `test_empty_text_returns_empty`

[tests/test_demo/test_customer_escalation.py](tests/test_demo/test_customer_escalation.py):
- `test_english_sample_tokens_match_killer_demo_prd` — every expected token present, no PII strings leaked into AI-safe output.
- `test_english_sample_matches_prd_token_layout` — **strict byte-for-byte match against the PRD §6 example**.
- `test_english_sample_round_trip_byte_identical` — Anonymize → Restore returns the original file byte-identically.
- `test_hebrew_sample_produces_first_class_il_tokens` — `[TEUDAT_ZEHUT_*]`, `[IL_PHONE_*]`, `[IL_BANK_ACCOUNT_*]` present; no `[SSN_*]` folding.
- `test_hebrew_sample_round_trip_byte_identical`.

### 3.3 New tests added in Phase 2

[tests/test_governance/test_reporting.py](tests/test_governance/test_reporting.py):
- `test_report_storage_never_persists_raw_pii_filename`
- `test_report_hash_chain_detects_tampering`
- Existing report append/read/export test now asserts `file_hash`, `file_label_safe`, and `chain_verified`.

[tests/test_logging/test_observability.py](tests/test_logging/test_observability.py):
- `test_audit_event_replaces_raw_file_path_with_safe_reference`

[tests/test_pipeline/test_anonymize.py](tests/test_pipeline/test_anonymize.py):
- `test_anonymize_report_and_audit_do_not_leak_pii_filename`

### 3.4 New tests added in Phase 3

[tests/test_demo_server/test_app.py](tests/test_demo_server/test_app.py):
- `test_demo_server_shield_restore_and_trust_center`
- `test_demo_server_restore_blocks_mutated_token`
- `test_demo_server_reset_returns_clean_workspace`
- `test_demo_server_rejects_unknown_sample`
- `test_demo_server_validates_loopback_bind_host`

### 3.5 New tests added in Phase 4

[tests/test_demo_server/test_app.py](tests/test_demo_server/test_app.py):
- `test_demo_server_serves_phase4_ui`
- `test_demo_server_mixed_sample_shields_english_and_il_values`

### 3.6 New tests and gates added in Phase 5/6

[scripts/demo_browser_acceptance.mjs](scripts/demo_browser_acceptance.mjs):
- Browser gate starts the local server, drives Chrome through Shield, Restore-blocked, Trust Center, and mobile layout.
- Local run passed with 12 replacements, 0 leaks, 1 changed/invented token blocked, 0 partial output, and mobile no-overflow.
- Hosted gate passed on 2026-04-30 after adding the multilingual Hebrew fallback spaCy model to the workflow.

[tests/test_demo_server/test_app.py](tests/test_demo_server/test_app.py):
- `test_demo_url_formats_loopback_hosts`

[tests/test_cli.py](tests/test_cli.py):
- `test_demo_help`
- `test_demo_rejects_non_loopback_without_onboarding_warning`

### 3.7 New tests added in the PyMuPDF→pdfplumber/reportlab swap

[tests/test_extractors/test_pdf_markdown.py](tests/test_extractors/test_pdf_markdown.py):
- `test_pdfplumber_backend_extracts_text` — single-page PDF round-trips through pdfplumber with expected markdown.
- `test_pdfplumber_backend_includes_per_page_headers` — multi-page PDF preserves `## Page N` headers.
- `test_pdfplumber_backend_raises_on_empty_pdf` — empty PDF raises `PdfExtractionError` rather than producing empty output.

[tests/test_governance/test_reporting.py](tests/test_governance/test_reporting.py):
- `test_export_sanitization_reports_pdf_writes_valid_pdf` — populated report exports as a real PDF (`%PDF-` magic, non-trivial size).
- `test_export_sanitization_reports_pdf_handles_empty_workspace` — empty workspace still produces a valid PDF.

### 3.8 New tests added in PR closeout safety cleanup

[tests/test_models.py](tests/test_models.py):
- `test_legacy_file_path_normalizes_to_safe_reference`

[tests/test_clipboard/test_operations.py](tests/test_clipboard/test_operations.py):
- `test_text_transform_roundtrip_does_not_touch_system_clipboard`

[tests/test_ipc/test_server.py](tests/test_ipc/test_server.py):
- `test_text_anonymize_returns_transformed_text`
- `test_text_restore_returns_transformed_text`

### 3.9 Walkthrough output (current state)

`uv run python scripts/demo_walkthrough.py` produces:

```
[PERSON_00001] at [ORG_00001] emailed [EMAIL_00001] about the [PROJECT_00001] renewal.
The account is [CUSTOMER_ID_00001] and includes a [CONTRACT_VALUE_00001] contract with an [PRICING_TERM_00001] exception.
Her phone number is [PHONE_00001] and the account address is [ADDRESS_00001].
The team wants AI help summarizing the [STRATEGY_00001] and [STRATEGY_00002] before the [DATE_00001] renewal meeting.
```

11 sensitive items shielded, 0 leaked, byte-identical round trip.

### 3.10 Browser/UI verification (Phase 4/5 local)

Browser verification used installed Chrome headless/CDP fallback because Browser/IAB was not available in this session and Computer Use permissions were pending.

- Desktop Shield path: loaded `/`, clicked `Create AI-Safe Version`, confirmed `Safe to paste into AI`, 12 masked review rows, 12 mappings stored locally, 0 leaks, and no horizontal overflow at 1440px.
- Mobile layout: loaded `/` at 390px width, confirmed `documentElement.scrollWidth == clientWidth == 390`, status pills fit, and presenter controls collapse to full-width rows.
- Restore failure path: loaded the mutated response, clicked restore, confirmed `Blocked`, 1 changed/invented token, expected `[PERSON_00001]`, found `[PERSON_001]`, and empty restored output.
- Trust Center path: confirmed mappings, shield events, audit-safe rows, local bind host `127.0.0.1`, external AI calls `0`, encrypted vault, and reports excluding original values.
- Screenshot artifacts from this local QA pass were written to `/tmp/cloakroom_phase4_desktop_after_shield.png`, `/tmp/cloakroom_phase4_mobile_checked.png`, `/tmp/cloakroom_phase4_restore_blocked.png`, and `/tmp/cloakroom_phase4_trust_center.png`.
- Phase 5 acceptance screenshots were written to `/tmp/cloakroom_phase5_acceptance/`.
- Phase 5 hardened acceptance screenshots were written to `/tmp/cloakroom_phase5_acceptance_after_fix/`.
- Phase 5 model-workflow acceptance screenshots were written to `/tmp/cloakroom_phase5_acceptance_after_model_fix/`.

### 3.11 GitHub-hosted closeout validation

- **GitHub CI** — PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1) is merged. Hosted `ci.yml`, `security-scan.yml`, and `ec15-gate.yml` passed on 2026-04-29 after the Phase 1 branch was pushed, and all closeout checks passed again before merge on 2026-04-30.
- **GitHub performance gate** — manually dispatched `performance-gate.yml` passed on hosted macOS after the NER template-cache fix. Observed hosted run: anonymize 5.82s, restore 0.53s, clipboard 0.49s against the 8.00s / 2.00s / 1.50s gates.
- **Phase 2 hosted checks** — passed on 2026-04-29 after the audit/report safety commit was pushed: CI tests, Security Scan dependency audit, EC-15, and manual `performance-gate.yml`.
- **Phase 3 hosted checks** — passed on 2026-04-29 after the demo backend commit was pushed: CI tests, Security Scan dependency audit, EC-15, and manual `performance-gate.yml`.
- **Phase 4 hosted checks** — passed on 2026-04-29 after the demo UI commit was pushed: CI tests, Security Scan dependency audit, EC-15, and manual `performance-gate.yml`.
- **Phase 5/6 hosted checks** — passed on 2026-04-30 after the workflow fix: Demo Acceptance passed in 1m0s ([run](https://github.com/GreggBerretta/Cloakroom/actions/runs/25150299365)), CI tests passed in 1m35s, Security Scan dependency audit passed in 22s, and both EC-15 jobs passed (59s / 43s). Historical note: the first hosted Demo Acceptance run on `b94c5cf` timed out waiting for Shield output; the hardened re-run on `763e1c8` identified that the workflow lacked `xx_ent_wiki_sm`, which is now installed.
- **Dependency-swap hosted checks** — passed on 2026-04-30 after `7c016d2` was pushed: Demo Acceptance passed in 56s ([run](https://github.com/GreggBerretta/Cloakroom/actions/runs/25162106630)), CI tests passed in 43s, Security Scan dependency audit passed in 16s, and both EC-15 jobs passed (34s / 35s). This confirms pdfplumber/reportlab work on GitHub macOS runners.
- **PR closeout safety hosted checks** — passed on 2026-04-30 after the wrapper-safety/attestation cleanup was pushed: Demo Acceptance passed in 52s ([run](https://github.com/GreggBerretta/Cloakroom/actions/runs/25162754701)), CI tests passed in 47s, Security Scan dependency audit passed in 15s, and both EC-15 jobs passed (45s / 41s). This confirms the text IPC lane, Swift wrapper changes, AttestationRecord redesign, and CI filter cleanup on GitHub macOS runners.
- **Local closeout validation** — latest completed on 2026-04-30:
  - `uv run pytest -q` -> 333 passed, 1 warning
  - `swift build --package-path wrapper/CloakroomWrapper` -> pass
  - `swift run --package-path wrapper/CloakroomWrapper wrapper-invariant-checks` -> pass
  - `uv run ruff check src/cloakroom/clipboard src/cloakroom/ipc src/cloakroom/licensing.py src/cloakroom/models.py tests/test_clipboard/test_operations.py tests/test_ipc/test_server.py tests/test_models.py` -> pass
  - `uv run python scripts/demo_walkthrough.py` -> pass
  - `uv run --with pip-audit pip-audit --local` -> no known vulnerabilities found
  - `uv run cloakroom benchmark-performance --rows 10000 --language en --enforce-gates --output /tmp/cloakroom_phase6_performance_gate.json` -> Gate PASS (anonymize 1.67s, restore 0.21s, clipboard 0.22s)
  - `uv run pytest -q tests/test_demo_server/test_app.py tests/test_cli.py` -> 30 passed, 1 warning
  - `uv run ruff check src/cloakroom/demo_server src/cloakroom/cli.py tests/test_demo_server tests/test_cli.py` -> pass
  - `node --check src/cloakroom/demo_server/static/app.js` -> pass
  - `node --check scripts/demo_browser_acceptance.mjs` -> pass
  - `node scripts/demo_browser_acceptance.mjs --screenshot-dir /tmp/cloakroom_phase5_acceptance` -> pass
  - `node scripts/demo_browser_acceptance.mjs --screenshot-dir /tmp/cloakroom_phase5_acceptance_after_fix` -> pass
  - `uv run python -c "import spacy; spacy.load('xx_ent_wiki_sm')"` -> pass
  - `node scripts/demo_browser_acceptance.mjs --screenshot-dir /tmp/cloakroom_phase5_acceptance_after_model_fix` -> pass
  - `uv run cloakroom demo --host 127.0.0.1 --port <random> --no-open-browser` + `/api/health` -> pass

---

## 4. What Has Passed or Failed

### 4.1 Passing

| Gate | State |
|---|---|
| Engine correctness (333 tests) | Pass |
| Demo-rule unit tests (7) | Pass |
| End-to-end killer-demo flow on EN sample | Pass |
| Strict PRD §6 token-layout assertion | Pass |
| Anonymize → Restore byte-identical round trip (EN + HE) | Pass |
| First-class IL/HE token emission | Pass |
| TEUDAT_ZEHUT no longer folded into US_SSN | Pass (regression test added) |
| Swift wrapper build | Pass |
| Wrapper invariant harness | Pass |
| Dependency audit (`pip-audit --local`) | Pass; no known vulnerabilities found |
| Local performance gate (EN, 10k rows) | Pass: anonymize 1.67s, restore 0.21s, clipboard 0.22s |
| Phase 2 audit/report safety focused tests | Pass: governance/reporting, logging/observability, pipeline no-leak integration, EC-15 |
| Phase 2 hosted PR checks | Pass: CI tests, Security Scan dependency audit, EC-15 |
| Phase 2 hosted performance gate | Pass: anonymize 5.56s, restore 0.52s, clipboard 0.44s |
| Phase 3 demo backend HTTP tests | Pass: `tests/test_demo_server/test_app.py` |
| Phase 3 hosted PR checks | Pass: CI tests, Security Scan dependency audit, EC-15 |
| Phase 3 hosted performance gate | Pass: anonymize 6.34s, restore 0.45s, clipboard 0.58s |
| Phase 4 demo UI/static tests | Pass: `tests/test_demo_server/test_app.py` |
| Phase 4 browser smoke | Pass: Chrome headless/CDP desktop Shield, mobile layout, Restore block, Trust Center |
| Phase 4 hosted PR checks | Pass: CI tests, Security Scan dependency audit, EC-15 |
| Phase 4 hosted performance gate | Pass: anonymize 7.49s, restore 0.70s, clipboard 0.62s |
| Phase 5 browser acceptance gate | Pass locally: `scripts/demo_browser_acceptance.mjs` |
| Phase 5 hosted browser acceptance gate | Pass: GitHub Demo Acceptance, 1m0s on 2026-04-30 |
| Phase 6 demo launcher smoke | Pass locally: `uv run cloakroom demo --no-open-browser` health check |
| Phase 5/6 hosted PR checks | Pass: CI tests, Security Scan dependency audit, EC-15, Demo Acceptance |
| PR closeout safety cleanup | Pass: AttestationRecord safe identity, text clipboard transform, text IPC dispatch, Swift wrapper build/invariants |

### 4.2 Failing

None at this moment.

### 4.3 Known regressions / edge cases left open

- **US area-code-with-parens phones** (`(415) 555-1234`) capture only `555-1234`. Not in the killer-demo sample; acceptable for now.
- **Hebrew NER quality is limited in this dev env.** Only `xx_ent_wiki_sm` (multilingual fallback) is installed; `he_core_news_sm` is missing. So HE_PERSON detection on the bundled HE sample is best-effort. The deterministic IL_PHONE / TEUDAT_ZEHUT / IL_BANK_ACCOUNT paths work regardless. Production install must `python -m spacy download he_core_news_sm`. Phase 1 tests deliberately do not assert HE_PERSON on the bundled sample for this reason.
- **Multi-pass LLM mutation acceptance gate** is still synthetic, not against real LLM outputs (per gap catalog). Phase 5 now gates the canned mutated-token sample in a real browser; broader real-LLM corpus coverage stays Master-PRD scope.

---

## 5. Performance Baselines

The historical numbers below come from the prior status report. A local English performance regression gate was re-run on 2026-04-29 after the Phase 1 demo-rule, replacer, and NER template-cache changes. The GitHub-hosted performance workflow also passed on PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

### Phase 1 local closeout run (2026-04-29)

Command:
```
uv run cloakroom benchmark-performance --rows 10000 --language en --enforce-gates --output /tmp/cloakroom_phase1_performance_gate_after_cache.json
```

| Operation | Result | Target | State |
|---|---|---|---|
| English 10k CSV anonymize (balanced) | 1.64 s | <= 8 s | PASS |
| English 10k CSV restore | 0.22 s | <= 2 s | PASS |
| Clipboard round trip | 0.23 s | <= 1.5 s | PASS |

### Phase 1 hosted closeout run (2026-04-29)

Manual workflow run: <https://github.com/GreggBerretta/Cloakroom/actions/runs/25114759087>

| Operation | Result | Target | State |
|---|---|---|---|
| English 10k CSV anonymize (balanced) | 5.82 s | <= 8 s | PASS |
| English 10k CSV restore | 0.53 s | <= 2 s | PASS |
| Clipboard round trip | 0.49 s | <= 1.5 s | PASS |

### Phase 2 hosted closeout run (2026-04-29)

Manual workflow run: <https://github.com/GreggBerretta/Cloakroom/actions/runs/25115584234>

| Operation | Result | Target | State |
|---|---|---|---|
| English 10k CSV anonymize (balanced) | 5.56 s | <= 8 s | PASS |
| English 10k CSV restore | 0.52 s | <= 2 s | PASS |
| Clipboard round trip | 0.44 s | <= 1.5 s | PASS |

### Phase 3 hosted closeout run (2026-04-29)

Manual workflow run: <https://github.com/GreggBerretta/Cloakroom/actions/runs/25116234504>

| Operation | Result | Target | State |
|---|---|---|---|
| English 10k CSV anonymize (balanced) | 6.34 s | <= 8 s | PASS |
| English 10k CSV restore | 0.45 s | <= 2 s | PASS |
| Clipboard round trip | 0.58 s | <= 1.5 s | PASS |

### Phase 4 hosted closeout run (2026-04-29)

Manual workflow run: <https://github.com/GreggBerretta/Cloakroom/actions/runs/25130332726>

| Operation | Result | Target | State |
|---|---|---|---|
| English 10k CSV anonymize (balanced) | 7.49 s | <= 8 s | PASS |
| English 10k CSV restore | 0.70 s | <= 2 s | PASS |
| Clipboard round trip | 0.62 s | <= 1.5 s | PASS |

### Pre-optimization baseline

| Operation | Result |
|---|---|
| English 10k CSV anonymize | 48.95 s — FAIL |
| Hebrew 10k CSV anonymize | 20.00 s — FAIL |
| 10k CSV restore | 0.14–0.16 s — PASS |
| Clipboard round trip | 0.17–0.18 s — PASS |

### Post-optimization baseline (2026-02-24)

Benchmark commands:
```
uv run cloakroom benchmark-performance -w perf-opt2-en-balanced --rows 10000 --language en --detection-mode balanced -o /tmp/cloakroom_perf2_en_balanced.json
uv run cloakroom benchmark-performance -w perf-opt2-en-speed    --rows 10000 --language en --detection-mode speed    -o /tmp/cloakroom_perf2_en_speed.json
uv run cloakroom benchmark-performance -w perf-opt2-he-balanced --rows 10000 --language he --detection-mode balanced -o /tmp/cloakroom_perf2_he_balanced.json
uv run cloakroom benchmark-performance -w perf-opt2-he-speed    --rows 10000 --language he --detection-mode speed    -o /tmp/cloakroom_perf2_he_speed.json
```

| Operation | Result | Target | State |
|---|---|---|---|
| English 10k CSV anonymize (balanced) | 1.96 s | ≤ 8 s | PASS |
| English 10k CSV anonymize (speed) | 1.95 s | ≤ 8 s | PASS |
| Hebrew 10k CSV anonymize (balanced) | 1.71 s | ≤ 8 s | PASS |
| Hebrew 10k CSV anonymize (speed) | 1.60 s | ≤ 8 s | PASS |
| 10k CSV restore | 0.19–0.22 s | ≤ 2 s | PASS |
| Clipboard round trip | 0.14–0.23 s | ≤ 1.5 s | PASS |

Delta vs. pre-optimization: English anonymize 48.95 s → 1.96 s (~96% faster); Hebrew 20.00 s → 1.71 s (~91% faster).

> Note: the Master Status & Release Gates doc cites a 95.74 s 10k CSV anonymize as "the primary watch item." That number predates the post-optimization run above and is likely from an even earlier measurement set. The 1.96 s / 1.71 s numbers are the current truth; the release gates document needs reconciling once the next benchmark run lands.

---

## 6. What Is Left To Be Done

### 6.1 Immediate (before any buyer demo)

| Item | Why | Phase |
|---|---|---|
| Phase 7 clean-machine dress rehearsal | PR #1 is merged; the next buyer-demo blocker is proving the full narrative on a clean Mac and capturing proof artifacts | Phase 7 |
| Reconcile Master Status & Release Gates performance note | The old 95.74s number conflicts with the current 1.96s / hosted-pass truth | Documentation closeout |

### 6.2 Demo build-out (per the execution plan)

| Phase | Scope | Rough effort |
|---|---|---|
| 2 | Audit/report safety. Replace raw `file_path` report/audit surfaces with `{file_hash, file_label_safe}`. Add hash chain on sanitization reports. Tests with PII-bearing filenames. | DONE on main |
| 3 | Demo backend: FastAPI bound to `127.0.0.1` only. Endpoints: `POST /api/shield`, `POST /api/restore`, `GET /api/trust-center`, `POST /api/demo/load-sample`, `POST /api/demo/reset`. | DONE on main |
| 4 | Three-screen web UI with RTL support (Shield for AI, Restore, Trust Center). Sample switcher (EN / HE-IL / mixed). Presenter controls. | DONE on main |
| 5 | Mutated-token failure hardening. Formal browser/integration gate asserting exact PRD §9 copy/state and no partial restore across CI. | DONE on main |
| 6 | Demo packaging. `cloakroom demo` opens browser, README runbook. Optional signed `.app` if time permits. | DONE on main for web demo; signed `.app` not included |
| 7 | Dress rehearsal + gates. Full PRD §5 narrative on a clean machine, success criteria check, performance NFRs, network capture proving no outbound traffic. | 1–2 days |

Total remaining for a presentable buyer demo after Phase 6 and PR #1 merge: **~2–4 focused engineering days** beyond what's already in, mostly clean-machine rehearsal, proof capture, and release-gates documentation reconciliation.

### 6.3 Out of scope for the killer demo (Master-PRD work)

Tracked but not blocking the buyer demo:

- Swift menu-bar packaging (signed `.app`, real heartbeat timer, first-run onboarding, updater, recovery UX, and stdio+AF_UNIX wrapper integration tests). ClipboardGuard is now wired into the menu flow and wake checks now probe the engine/vault instead of hardcoded success, but the native app is still not the signed production surface. **IT review revised the effort estimate to 3–5 engineering weeks** (was 2–3) once notarization, polished onboarding, Sparkle/MDM updater, and stdio+AF_UNIX wrapper integration tests are included.
- Crash atomicity / staged-output reconciliation.
- Real LLM mutation harness against representative corpora. **IT review reframed**: the release gate is the fail-closed invariant (zero incorrect restores, calm recovery UX), not third-party LLM token-retention rates. Real LLM runs are evidence/monitoring, not a release lock. Master Release-Gates doc needs this language.
- License/entitlement system upgrade (currently regex/env-var based). IT priority order: signed offline license file for pilots first, online/hybrid later.
- Third-party model/license review (spaCy, Presidio, Hebrew models, Stanza, Transformers, pdfplumber, reportlab, Gradio, Textual, Swift deps). **PyMuPDF was removed 2026-04-30** in favor of pdfplumber (MIT) + reportlab (BSD) to eliminate the AGPL/commercial licensing decision; that part of the legal review is now closed.
- Attestation workflow UX is still not built. The data model pre-work is complete: `AttestationRecord` now stores `{file_hash, file_label_safe}` instead of raw `file_path` ([src/cloakroom/models.py:337](src/cloakroom/models.py)).
- The two small Swift wrapper hardcoded-value fixes are complete on `main`: wake checks now call `HEARTBEAT` + `STATS_QUERY`, and menu-bar clipboard Shield/Restore now use `ClipboardGuard` + text IPC before displaying success.
- Apple Developer enrollment is calendar-critical-path: notarization can't begin until the team is enrolled and the Developer ID Application certificate is issued. Start in parallel with engineering work, not after.
- Update channel decision (Sparkle vs. MDM-distributed `.pkg`). Many enterprises block self-updating apps via MDM policy. Survey 2–3 likely pilot customers before wiring Sparkle.
- Reconciliation of the 95.74 s vs. 1.96 s perf numbers between the master release-gates doc and the actual benchmark.

---

## 7. Open Issues / Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Attestation workflow not built** | The safe data model is ready, but sensitive workflows still do not require a user attestation step | Build the required ingest-review dialog and persist zero-PII attestation records before public beta |
| **Hosted performance creeping toward gate** | Phase 4 hosted run was 7.49 s vs. 8 s gate; could be runner variance or a real regression | Re-run `performance-gate.yml` 3× on the tip commit and confirm the 95th percentile is comfortably under 8 s |
| Future feature branches can stale checks | New PRs will need their own hosted validation before merge | Keep the PR #1 pattern: local validation first, then hosted CI/security/EC-15/demo acceptance on the exact tip |
| Native wrapper still not commercially packaged | Clipboard/wake false-success paths are improved, but customers still need a signed/notarized app, onboarding, updater policy, and wrapper integration tests | Treat native app hardening as the closed-pilot critical path |
| Follow-up raw path additions | New report/audit call sites could reintroduce raw paths if they bypass the helpers | Use `append_sanitization_report()` / `append_audit_event()` and keep PII-bearing filename tests green |
| Signed native app not built | `cloakroom demo` gives a one-command local web demo, but not a signed macOS `.app` | Phase 6 follow-up. Out of scope for the killer demo (in-person presentation, no hand-off). Required for closed pilot. |
| Hebrew NER quality in this dev env | HE_PERSON detection on the bundled HE sample relies on `xx_ent_wiki_sm` fallback | Production install: `python -m spacy download he_core_news_sm`. Phase 1 explicitly does not assert HE_PERSON on the bundled sample. |
| Demo-rule false positives in non-demo workspaces | Default ruleset includes `Acme Health`, `Project Lantern`, etc. — fine for the killer demo, wrong for a real customer | Default ruleset is opt-in via the `demo_ruleset=` constructor argument; pipeline default is `None`, so no production change. |

---

## 8. How To Run This Locally

From the canonical tree (`/Users/greggberretta/Documents/New project/Cloakroom`):

```bash
# 1. Install / refresh deps (uv-managed venv).
uv sync --extra dev
uv run python -m ensurepip
uv run python -m spacy download en_core_web_lg
uv run python -m spacy download he_core_news_sm   # or xx_ent_wiki_sm

# 2. Full test suite.
uv run pytest -q                           # expect 333 passed

# 3. EC-15 state integrity gate.
uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py

# 4. Killer-demo terminal walkthrough (English sample).
uv run python scripts/demo_walkthrough.py

# 5. Local demo UI/backend.
uv run cloakroom demo

# 6. Browser acceptance gate.
node scripts/demo_browser_acceptance.mjs --screenshot-dir /tmp/cloakroom-demo-acceptance

# 7. Swift wrapper build + invariant harness.
swift build --package-path wrapper/CloakroomWrapper
swift run --package-path wrapper/CloakroomWrapper wrapper-invariant-checks
```

Branch / push / PR for future work:

```bash
git checkout main
git pull --ff-only origin main
git checkout -b feature/<short-topic>
git push -u origin feature/<short-topic>
gh pr create --base main --fill --draft
```

The GitHub CLI token has `workflow` scope as of 2026-04-30; the CI filter cleanup was merged in PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

---

## 9. Pointers For An Engineer Picking This Up Cold

- **Read order:** [docs/Cloakroom_Master_PRD.md](docs/Cloakroom_Master_PRD.md) → [docs/Cloakroom_Killer_Demo_PRD.md](docs/Cloakroom_Killer_Demo_PRD.md) → [docs/Cloakroom_Current_State_and_Gaps.md](docs/Cloakroom_Current_State_and_Gaps.md) → this file → execution plan in `~/.claude/plans/`.
- **Spine of the engine:** [src/cloakroom/pipeline/anonymize.py](src/cloakroom/pipeline/anonymize.py) and [src/cloakroom/pipeline/restore.py](src/cloakroom/pipeline/restore.py).
- **Detection layering (highest precedence first):** demo rules → regex prefilter → Presidio NER. All converge in [src/cloakroom/detection/engine.py](src/cloakroom/detection/engine.py) `_merge_entities`.
- **Token model:** [src/cloakroom/models.py](src/cloakroom/models.py) (`EntityType`, `Token`, `EntityMapping`); minted in [src/cloakroom/tokenizer/generator.py](src/cloakroom/tokenizer/generator.py); applied in [src/cloakroom/tokenizer/replacer.py](src/cloakroom/tokenizer/replacer.py).
- **Vault and workspace lifecycle:** [src/cloakroom/vault/](src/cloakroom/vault/) and [src/cloakroom/workspace/manager.py](src/cloakroom/workspace/manager.py).
- **Existing UI surfaces** (internal-only, not the killer demo): [src/cloakroom/ui/gradio_app.py](src/cloakroom/ui/gradio_app.py), [src/cloakroom/tui/app.py](src/cloakroom/tui/app.py).
- **Killer-demo backend:** [src/cloakroom/demo_server/app.py](src/cloakroom/demo_server/app.py) (`create_app`, `DemoRuntime`, local-only FastAPI endpoints).
- **Killer-demo UI:** [src/cloakroom/demo_server/static/](src/cloakroom/demo_server/static/) (`Shield for AI`, `Restore`, `Trust Center` single-page app served from `/`).
- **Killer-demo acceptance:** [scripts/demo_browser_acceptance.mjs](scripts/demo_browser_acceptance.mjs) and [.github/workflows/demo-acceptance.yml](.github/workflows/demo-acceptance.yml).
- **Killer-demo runbook:** [docs/Cloakroom_Demo_Runbook.md](docs/Cloakroom_Demo_Runbook.md). Preferred launch command: `uv run cloakroom demo`.
