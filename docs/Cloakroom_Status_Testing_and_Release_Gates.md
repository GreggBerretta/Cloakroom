# Cloakroom

## Program Status, Testing & Release Gates

Operational companion to the master PRD. Focus: current status, resolved contradictions, testing strategy, release gates, pilot sequencing, and execution priorities. Prepared from the performance baseline, Phase 1 / Phase 2 drafts, wrapper addenda, vault governance drafts, and gap analyses.

This document is intentionally separate from the master PRD. The PRD defines what Cloakroom is. This document defines where the program stands, what still blocks release, how testing is organized, and what gets done next.

## 1. Current Program Position

- The transformation engine baseline is materially ahead of the commercialization and wrapper docs in maturity.
- Earlier internal reporting characterized the engine as pilot-ready, with core test suites and integrity gates already green.
- The most important remaining execution problem is not conceptual scope. It is consolidation, performance, and disciplined release sequencing.

Operating conclusion: Cloakroom should move forward as a two-track program — a locked product/architecture specification and a separate release-management document. Blending both into one artifact is what caused the overlap in the first place.

## 2. Resolved Consolidation Decisions

| Area | Source-of-truth decision |
|---|---|
| Product name | Use Cloakroom everywhere. CoWork Shield becomes historical only. |
| Product frame | Treat the system as a reversible anonymizer/de-anonymizer and reasoning-enablement layer, not as a full DLP platform. |
| Vault scope | Keep local-first vault governance now; move KMS/shared-workspace ambitions out of the current release. |
| Wrapper IPC | Adopt hybrid IPC: support existing subprocess mode now and UNIX sockets for hardened native wrapper flows. |
| Hebrew and selective controls | Promote them from edge features to first-class supported capabilities in product and audit reporting. |
| Commercial packaging | Keep edition gating explicit rather than implied. |
| Document split | Master PRD for normative truth; status/gates document for execution truth. |

## 3. Baseline Status Snapshot

| Area | Status | Notes |
|---|---|---|
| Core engine correctness | Strong | Prior drafts report deterministic, fail-closed restoration across supported formats. |
| Wrapper architecture | Partially specified | Security invariants are strong; compatibility path had to be fixed. |
| Vault governance | Viable after scope trim | Local-only governance is ready to package; enterprise KMS must stay deferred. |
| Performance | Needs focused work | Large CSV anonymization remains the main user-friction risk. |
| Commercial readiness | Emerging | Packaging, gating, audit export, and wrapper polish matter more than new conceptual scope. |

## 4. Performance Baseline and Implications

| Operation | Observed baseline | Assessment |
|---|---|---|
| 10k CSV anonymize | 95.74 s | Primary watch item; too slow for broad, confident deployment. |
| 10k CSV restore | 11.49 s | Strong and commercially acceptable. |
| Clipboard shield | 1.07 s | Excellent; aligned with intended daily habit use. |
| Clipboard restore | 0.50 s | Excellent. |
| Clipboard round trip | 1.57 s | Near target; worth protecting during wrapper hardening. |

Execution implication: the product promise is already attractive, but the spreadsheet anonymization budget remains out of line with the stricter later targets. This must be treated as a real release gate rather than a documentation note.

## 5. Testing Structure

### 5.1 Test families

- Unit tests for models, crypto, tokenization, detection wrappers, file handlers, workspace logic, and verification logic.
- Integration tests for anonymize and restore across CSV, XLSX, DOCX, clipboard, and multi-file workspaces.
- Deterministic replay tests that validate byte-identical behavior after restart and across approved state boundaries.
- Wrapper state-machine tests for `READY`, `BUSY`, `HARD_FAIL`, sleep/wake, heartbeat loss, and clipboard verification paths.
- Red-team tests for protocol ambiguity, schema mismatch, malformed JSON, clipboard lifecycle violations, and false-success suppression.
- Mutation tests using real LLM rewrite patterns and multi-pass restore cycles.
- Hebrew and column-selective tests, including audit-summary correctness.

### 5.2 Acceptance gates

| Gate | Pass condition | Owner |
|---|---|---|
| Restore correctness | Zero incorrect restores | Engineering |
| Formula preservation | No spreadsheet formula breakage | Engineering |
| Replay integrity | Byte-identical accepted cases | Engineering |
| Wrapper truthfulness | No false success states | Engineering |
| Clipboard UX | At or under approved latency budget | Engineering |
| Audit safety | Zero-PII, tamper-evident logs | Engineering / Security |
| Commercial packaging | Edition gating and compliant third-party licensing checked | Product / Legal / Engineering |

## 6. Release Gates Before External Beta

1. Performance remediation for large spreadsheet anonymization must be documented and, preferably, materially improved.
2. Wrapper must support the compatibility path to current interfaces while enforcing hard-fail invariants.
3. License and model-weight review must be complete for all bundled or required detection components.
4. Audit export, TTL behavior, purge behavior, and backup-before-purge logic must be tested end to end.
5. Hebrew support and column-selective flows must be represented in both product behavior and audit summaries.
6. Support runbook, installation path, recovery-key flow, and user-facing pilot instructions must exist and be rehearsed.

## 7. Risks Worth Treating Seriously

| Risk | Why it matters | Mitigation |
|---|---|---|
| Large-file slowdown | Users will bypass the tool if anonymize feels expensive. | Performance sprint; set realistic guardrails and warnings. |
| Trust loss from a single bad restore | This is existential for adoption. | Keep fail-closed posture and elevate restore correctness above all other metrics. |
| Wrapper rewrite risk | A socket-only mandate would have delayed beta and stranded existing interfaces. | Use hybrid IPC and phase the harder path in cleanly. |
| Scope creep into enterprise infrastructure | Premature KMS/shared-workspace work would delay revenue and clarity. | Defer to future enterprise scope and say so plainly. |
| Incomplete Hebrew or selective audit coverage | High-value customer cases would appear half-supported. | Promote these to first-class test and reporting coverage. |
| Clipboard regressions during hardening | The fastest daily-use feature could become annoying. | Treat clipboard latency as a guarded budget, not a nice-to-have. |

## 8. Recommended 30-Day Execution Sequence

1. Freeze the new document structure and rename downstream artifacts to Cloakroom.
2. Run a focused performance sprint on CSV and high-volume spreadsheet anonymization paths.
3. Implement or finalize hybrid wrapper IPC, heartbeat handling, and hard-fail state enforcement.
4. Finish local-first vault governance: TTL, purge, encrypted backup, zero-PII audit, and export behavior.
5. Bring Hebrew and column-selective behavior into audit summaries, wrapper payloads, and acceptance tests.
6. Run a closed beta with real users only after the revised gates are green.

## 9. Suggested Document Control Going Forward

- Keep the master PRD stable and change it only when product truth changes.
- Use this status/gates document for readiness, sequencing, blockages, and execution calls.
- Append detailed test plans or red-team cases as annexes if needed, but do not fold them back into the main PRD.
- Any future enterprise KMS or shared-workspace work should begin as a separate enterprise addendum, not as stealth scope inside local vault docs.

## 10. Bottom Line

Cloakroom is not missing a concept. It is missing a disciplined finish. The underlying engine direction is strong; the wrapper and vault commercialization work become viable once their scope is normalized and execution is sequenced around performance, trust, and release truthfulness rather than around new speculative features.
