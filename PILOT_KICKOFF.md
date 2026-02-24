# Cloakroom Pilot Kickoff (HANDOFF B)

## Scheduled Session
- **Date:** Wednesday, February 25, 2026
- **Time:** 10:00 AM - 10:45 AM Pacific Time (PT)
- **Format:** Remote (internal call)
- **Scope:** HANDOFF B pilot onboarding (3-5 users)

## Objectives
1. Confirm installation is successful on pilot machines.
2. Run live workflow: anonymize -> LLM -> restore.
3. Review fail-closed behavior and support runbook.
4. Capture first-friction feedback and triage process.

## Required Prep (Before Kickoff)
- Install via `INSTALL.md` (`uv sync` path).
- Run:
  - `uv run pytest -q`
  - `uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py`
- Generate one recovery key export:
  - `uv run cloakroom workspace export-key --workspace <name> --output <name>.recovery.key`

## Agenda (45 min)
1. 10 min: Scope, trust invariants, and pilot rules.
2. 15 min: Live workflow demo and participant run-through.
3. 10 min: Troubleshooting and support escalation flow.
4. 10 min: Feedback capture and next-week check-in plan.

## Owners
- Pilot Lead: Gregg Berretta
- Engineering Owner: Cloakroom core maintainer
- Support Channel: `#cloakroom-pilot`

