# Cloakroom — Build Status

**Date:** 2026-04-29
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
| Active feature branch | `feature/demo-rules-and-il-entities` (pushed; draft PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1)) |
| Stale local branches | `codex/handoff-b-status-doc`, `feature/rename-to-cloakroom` (kept as historical refs; deletable) |
| Stale remote branches | `codex/handoff-b-status-doc`, `codex/handoff-b-status-doc-clean` (consider deleting after Phase 1 PR merges) |
| Working tree | Clean after latest status commit |
| Engine tests | **314 passing** on the active branch after Phase 2 local validation |
| Swift build | Pass on 2026-04-29 during Phase 1 closeout |

### Functional commits ahead of main on the active branch

```
03b2aa0  fix(detection): full international phone capture, stable token ordering, single-token dates
08d55f6  feat(detection): demo rules engine + first-class IL/HE entity taxonomy
```

These functional commits, the NER template-cache performance fix, Phase 2 audit/report safety hardening, and status-documentation commits are on draft PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

---

## 2. What Has Been Built

Phases reference the execution plan. Phases 0, 1, and 2 are complete locally; Phase 3 onward is not started.

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

Commits `08d55f6` and `03b2aa0` on `feature/demo-rules-and-il-entities`.

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

### Phase 2 — Audit/report safety hardening (DONE locally)

Current Phase 2 implementation is on the active branch after the Phase 1 commits.

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
- Native Mac menu-bar Swift target (`cloakroom-menubar`) — scaffold-grade only.
- Performance gate workflow + benchmark CLI.

---

## 3. What Has Been Tested

### 3.1 Test counts

| Suite | Pre-Phase-1 | Now |
|---|---|---|
| Total Python tests | 297 | **314** |
| Phase-1 additions | — | 13 (7 demo-rule unit, 5 demo end-to-end, 1 NER template-cache regression) |
| Phase-2 additions | — | 4 new tests plus 1 strengthened report export test (report path safety, report hash chain, audit path safety, pipeline no-leak integration) |

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

### 3.4 Walkthrough output (current state)

`uv run python scripts/demo_walkthrough.py` produces:

```
[PERSON_00001] at [ORG_00001] emailed [EMAIL_00001] about the [PROJECT_00001] renewal.
The account is [CUSTOMER_ID_00001] and includes a [CONTRACT_VALUE_00001] contract with an [PRICING_TERM_00001] exception.
Her phone number is [PHONE_00001] and the account address is [ADDRESS_00001].
The team wants AI help summarizing the [STRATEGY_00001] and [STRATEGY_00002] before the [DATE_00001] renewal meeting.
```

11 sensitive items shielded, 0 leaked, byte-identical round trip.

### 3.5 GitHub-hosted closeout validation

- **GitHub CI** — draft PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1) is open. Hosted `ci.yml`, `security-scan.yml`, and `ec15-gate.yml` passed on 2026-04-29 after the Phase 1 branch was pushed.
- **GitHub performance gate** — manually dispatched `performance-gate.yml` passed on hosted macOS after the NER template-cache fix. Observed hosted run: anonymize 5.82s, restore 0.53s, clipboard 0.49s against the 8.00s / 2.00s / 1.50s gates.
- **Phase 2 hosted checks** — passed on 2026-04-29 after the audit/report safety commit was pushed: CI tests, Security Scan dependency audit, EC-15, and manual `performance-gate.yml`.
- **Local closeout validation** — completed on 2026-04-29:
  - `uv run pytest -q` -> 314 passed, 1 warning
  - `swift build --package-path wrapper/CloakroomWrapper` -> pass
  - `swift run --package-path wrapper/CloakroomWrapper wrapper-invariant-checks` -> pass
  - `uv run python scripts/demo_walkthrough.py` -> pass
  - `uv run --with pip-audit pip-audit --local` -> no known vulnerabilities found
  - `uv run cloakroom benchmark-performance --rows 10000 --language en --enforce-gates --output /tmp/cloakroom_phase1_performance_gate_after_cache.json` -> Gate PASS

---

## 4. What Has Passed or Failed

### 4.1 Passing

| Gate | State |
|---|---|
| Engine correctness (314 tests) | Pass |
| Demo-rule unit tests (7) | Pass |
| End-to-end killer-demo flow on EN sample | Pass |
| Strict PRD §6 token-layout assertion | Pass |
| Anonymize → Restore byte-identical round trip (EN + HE) | Pass |
| First-class IL/HE token emission | Pass |
| TEUDAT_ZEHUT no longer folded into US_SSN | Pass (regression test added) |
| Swift wrapper build | Pass |
| Wrapper invariant harness | Pass |
| Dependency audit (`pip-audit --local`) | Pass; no known vulnerabilities found |
| Local performance gate (EN, 10k rows) | Pass: anonymize 1.64s, restore 0.22s, clipboard 0.23s |
| Phase 2 audit/report safety focused tests | Pass: governance/reporting, logging/observability, pipeline no-leak integration, EC-15 |
| Phase 2 hosted PR checks | Pass: CI tests, Security Scan dependency audit, EC-15 |
| Phase 2 hosted performance gate | Pass: anonymize 5.56s, restore 0.52s, clipboard 0.44s |

### 4.2 Failing

None at this moment.

### 4.3 Known regressions / edge cases left open

- **US area-code-with-parens phones** (`(415) 555-1234`) capture only `555-1234`. Not in the killer-demo sample; acceptable for now.
- **Hebrew NER quality is limited in this dev env.** Only `xx_ent_wiki_sm` (multilingual fallback) is installed; `he_core_news_sm` is missing. So HE_PERSON detection on the bundled HE sample is best-effort. The deterministic IL_PHONE / TEUDAT_ZEHUT / IL_BANK_ACCOUNT paths work regardless. Production install must `python -m spacy download he_core_news_sm`. Phase 1 tests deliberately do not assert HE_PERSON on the bundled sample for this reason.
- **Multi-pass LLM mutation acceptance gate** is still synthetic, not against real LLM outputs (per gap catalog). The killer-demo Phase 5 covers one canned mutated-token sample; broader real-LLM corpus gate stays Master-PRD scope.

---

## 5. Performance Baselines

The historical numbers below come from the prior status report. A local English performance regression gate was re-run on 2026-04-29 after the Phase 1 demo-rule, replacer, and NER template-cache changes. The GitHub-hosted performance workflow also passed on draft PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1).

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
| Human-review and merge draft PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1) when ready | Branch is pushed, PR is open, and local + hosted closeout gates have passed through Phase 2 | Phase 1/2 closeout |
| Run `gh auth refresh -s workflow` and land the deferred CI filter cleanup (drop `codex/**`, leave `main` + `pull_request`) | The change is already prepared; the OAuth token didn't have `workflow` scope when we tried | Phase 0 leftover |

### 6.2 Demo build-out (per the execution plan)

| Phase | Scope | Rough effort |
|---|---|---|
| 2 | Audit/report safety. Replace raw `file_path` report/audit surfaces with `{file_hash, file_label_safe}`. Add hash chain on sanitization reports. Tests with PII-bearing filenames. | DONE locally |
| 3 | Demo backend: FastAPI bound to `127.0.0.1` only. Endpoints: `POST /api/shield`, `POST /api/restore`, `GET /api/trust-center`, `POST /api/demo/load-sample`, `POST /api/demo/reset`. | 3–4 days |
| 4 | Three-screen web UI with RTL support (Shield for AI, Restore, Trust Center). Sample switcher (EN / HE-IL / mixed). Presenter controls. | 5–7 days |
| 5 | Mutated-token failure flow. Pre-canned response that breaks `[PERSON_00001]` → `[PERSON_001]`. Fail-closed UI exactly per PRD §9 Step 8. Integration test asserting structured error and no partial restore. | 1 day |
| 6 | Demo packaging. `cloakroom demo` opens browser, README runbook. Optional signed `.app` if time permits. | 2–3 days |
| 7 | Dress rehearsal + gates. Full PRD §5 narrative on a clean machine, success criteria check, performance NFRs, network capture proving no outbound traffic. | 1–2 days |

Total remaining for a presentable buyer demo after Phase 2: **~3–4 focused engineering weeks** beyond what's already in.

### 6.3 Out of scope for the killer demo (Master-PRD work)

Tracked but not blocking the buyer demo:

- Swift menu-bar packaging (signed `.app`, real heartbeat, `ClipboardGuard` wired into the production menu flow, real wake/health checks). Currently scaffold-grade.
- Crash atomicity / staged-output reconciliation.
- Real LLM mutation harness against representative corpora.
- License/entitlement system upgrade (currently regex/env-var based).
- Third-party model/license review (spaCy, Presidio, Hebrew models, Stanza, Transformers, PyMuPDF, Gradio, Textual, Swift deps).
- Reconciliation of the 95.74 s vs. 1.96 s perf numbers between the master release-gates doc and the actual benchmark.

---

## 7. Open Issues / Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| Follow-up pushes can stale PR checks | A final documentation or review fix can require checks to be re-run before merge | Re-check PR [#1](https://github.com/GreggBerretta/Cloakroom/pull/1) immediately before merging |
| Follow-up raw path additions | New report/audit call sites could reintroduce raw paths if they bypass the helpers | Use `append_sanitization_report()` / `append_audit_event()` and keep PII-bearing filename tests green |
| Hebrew NER quality in this dev env | HE_PERSON detection on the bundled HE sample relies on `xx_ent_wiki_sm` fallback | Production install: `python -m spacy download he_core_news_sm`. Phase 1 explicitly does not assert HE_PERSON on the bundled sample. |
| Demo-rule false positives in non-demo workspaces | Default ruleset includes `Acme Health`, `Project Lantern`, etc. — fine for the killer demo, wrong for a real customer | Default ruleset is opt-in via the `demo_ruleset=` constructor argument; pipeline default is `None`, so no production change. |
| Stale local + remote branches confuse new clones | `codex/handoff-b-status-doc(-clean)` and `feature/rename-to-cloakroom` are no longer load-bearing | Optional cleanup task: delete both remotes and the local rename branch after the Phase 1 PR merges. |

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
uv run pytest -q                           # expect 314 passed

# 3. EC-15 state integrity gate.
uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py

# 4. Killer-demo terminal walkthrough (English sample).
uv run python scripts/demo_walkthrough.py

# 5. Swift wrapper build + invariant harness.
swift build --package-path wrapper/CloakroomWrapper
swift run --package-path wrapper/CloakroomWrapper wrapper-invariant-checks
```

Branch / push / PR:

```bash
git checkout feature/demo-rules-and-il-entities
git push -u origin feature/demo-rules-and-il-entities
gh pr create --base main --fill
```

The CI filter cleanup commit needs `gh auth refresh -s workflow` first (the existing token has `repo` but not `workflow`).

---

## 9. Pointers For An Engineer Picking This Up Cold

- **Read order:** [docs/Cloakroom_Master_PRD.md](docs/Cloakroom_Master_PRD.md) → [docs/Cloakroom_Killer_Demo_PRD.md](docs/Cloakroom_Killer_Demo_PRD.md) → [docs/Cloakroom_Current_State_and_Gaps.md](docs/Cloakroom_Current_State_and_Gaps.md) → this file → execution plan in `~/.claude/plans/`.
- **Spine of the engine:** [src/cloakroom/pipeline/anonymize.py](src/cloakroom/pipeline/anonymize.py) and [src/cloakroom/pipeline/restore.py](src/cloakroom/pipeline/restore.py).
- **Detection layering (highest precedence first):** demo rules → regex prefilter → Presidio NER. All converge in [src/cloakroom/detection/engine.py](src/cloakroom/detection/engine.py) `_merge_entities`.
- **Token model:** [src/cloakroom/models.py](src/cloakroom/models.py) (`EntityType`, `Token`, `EntityMapping`); minted in [src/cloakroom/tokenizer/generator.py](src/cloakroom/tokenizer/generator.py); applied in [src/cloakroom/tokenizer/replacer.py](src/cloakroom/tokenizer/replacer.py).
- **Vault and workspace lifecycle:** [src/cloakroom/vault/](src/cloakroom/vault/) and [src/cloakroom/workspace/manager.py](src/cloakroom/workspace/manager.py).
- **Existing UI surfaces** (internal-only, not the killer demo): [src/cloakroom/ui/gradio_app.py](src/cloakroom/ui/gradio_app.py), [src/cloakroom/tui/app.py](src/cloakroom/tui/app.py).
- **Killer-demo entry points to build next:** `src/cloakroom/demo_server/` (Phase 3, doesn't exist yet) and a fresh single-page UI (Phase 4).
