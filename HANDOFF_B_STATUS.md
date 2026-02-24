# HANDOFF_B Implementation Status (Fork)

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

## Added Beyond Baseline (v11 Launch-Prep in Fork)
- Free TTL fixed to 24h, Pro TTL up to 30 days
- auditable license checks wired through CLI/UI/IPC
- workspace close/recover/purge governance commands
- self-destruct-on-restore policy toggle
- auditor-safe sanitization report generation + Pro export
- benchmark command + performance gate workflow
- Swift native menu-bar shell target scaffold

## Validation
- `uv run pytest -q` -> 296 passed
- `swift build` in `wrapper/CoWorkShieldWrapper` -> pass
- `swift run wrapper-invariant-checks` -> pass

## Performance Reality vs Target
Current build meets restore and clipboard latency goals, but does not meet 10k CSV anonymize budget.

Measured (10k rows):
- English anonymize: 48.95s (target <= 8s)
- Hebrew anonymize: 20.00s (target <= 8s)
- restore: pass
- clipboard: pass

## Decision Point
The project is operationally ready for continued internal validation and pilot hardening.
Release-level commercialization should wait until CSV full-detect anonymize throughput reaches target or is explicitly product-scoped behind an alternative workflow profile.
