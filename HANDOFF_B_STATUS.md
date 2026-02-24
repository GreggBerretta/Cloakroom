# HANDOFF_B Implementation Status

## Baseline
This status is explicitly based on `HANDOFF_B.md` (lean internal validation scope), then extended with v11 launch-prep controls implemented in this branch.

## Current State
- Core HANDOFF_B engine is implemented and stable.
- All current automated tests pass.
- EC-15 integrity harness is green.
- Wrapper core and native shell target both compile.

## Completed from HANDOFF_B
- deterministic replay enforcement
- model hash lock
- fail-closed restore
- hallucination detection on restore
- TXT/MD support
- clipboard shield/restore
- bracketed token ABI
- PDF input-only conversion pipeline
- Hebrew support pathways
- spreadsheet column-selective anonymization

## Added Beyond Baseline (v11 Launch-Prep)
- Free TTL fixed to 24h, Pro TTL up to 30 days
- auditable license checks wired through CLI/UI/IPC
- workspace close/recover/purge governance commands
- self-destruct-on-restore policy toggle
- auditor-safe sanitization report generation + Pro export
- benchmark command + performance gate workflow
- Swift native menu-bar shell target scaffold

## Validation
- `uv run pytest -q` -> 297 passed
- `swift build` in `wrapper/CloakroomWrapper` -> pass
- `swift run wrapper-invariant-checks` -> pass

## Performance Reality vs Target
Current build now meets anonymize, restore, and clipboard latency goals after the detection optimization pass.

Measured (10k rows, 2026-02-24):
- English anonymize (balanced): 1.96s (target <= 8s) -> pass
- English anonymize (speed): 1.95s (target <= 8s) -> pass
- Hebrew anonymize (balanced): 1.71s (target <= 8s) -> pass
- Hebrew anonymize (speed): 1.60s (target <= 8s) -> pass
- Restore: 0.19-0.22s (target <= 2s) -> pass
- Clipboard round-trip: 0.14-0.23s (target <= 1.5s) -> pass

Delta from prior baseline:
- English anonymize: 48.95s -> 1.96s (~96.0% faster)
- Hebrew anonymize: 20.00s -> 1.71s (~91.4% faster)

## Decision Point
The project is operationally ready for continued internal validation and pilot hardening with performance budgets currently satisfied.
