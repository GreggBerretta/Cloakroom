# Cloakroom Demo Runbook

Date: 2026-04-30

Purpose: run the local buyer-facing Cloakroom demo for IT/security review.

## Quick Start

From the repo root:

```bash
uv sync --extra dev
uv run python -m spacy download en_core_web_lg
uv run cloakroom demo
```

The command starts a local-only server and opens:

```text
http://127.0.0.1:8765/
```

Stop the demo with `Ctrl+C` in the terminal.

## Demo Flow

1. Click `Use Demo Sample`.
2. Click `Create AI-Safe Version`.
3. Confirm the right pane says `AI-safe version - safe to paste`.
4. Click `Restore AI Response`.
5. Use `Use Clean AI Response`, then click `Restore Original Values`.
6. Return to `Shield for AI`, click `Load Failure Sample`, then click `Restore Original Values`.
7. Confirm the restore is blocked and says `No partial restore was created.`
8. Open `Trust Center` and confirm local-only proof, audit-safe report rows, and policy preview.

## Presenter Controls

- `Demo sample`: switch between EN, HE-IL, and mixed EN/HE samples.
- `Use Demo Sample`: reload the selected sample.
- `Load Failure Sample`: load the canned mutated-token response.
- `Export Audit JSON`: export audit-safe metadata for review.
- `Reset Demo`: reset the local demo vault/workspace to a clean state.

## Acceptance Gate

Run the browser acceptance gate locally:

```bash
node scripts/demo_browser_acceptance.mjs --screenshot-dir /tmp/cloakroom-demo-acceptance
```

The gate starts the demo server on a random loopback port, drives Chrome headless through the Shield, Restore-blocked, Trust Center, and mobile-layout flows, and writes screenshots to the chosen directory.

## Local-Only Notes

- The demo binds to loopback only: `127.0.0.1`, `localhost`, or `::1`.
- The default `cloakroom demo` command opens a browser. Use `--no-open-browser` for scripted runs.
- Raw original values stay in the local demo vault.
- Audit/report views show hashes and safe labels, not raw filenames or original values.
