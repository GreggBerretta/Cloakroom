# CoWork Shield Internal Install (HANDOFF B)

This install path is for the HANDOFF B internal validation build (CLI-only, no Swift/IPC).

## Distribution Strategy
Current recommendation:

- Primary: `uv sync` in repo checkout (fastest for pilot)
- Optional (future): internal Homebrew tap wrapper around the same CLI
- Not recommended now: PyInstaller packaging (defer unless users reject Python environment setup)

This document covers the current supported path: `uv sync`.

## Prerequisites
- macOS (tested on Apple Silicon + recent Intel)
- Git
- `uv` installed
- Access to this private repo

## Install Steps
```bash
git clone https://github.com/GreggBerretta/cowork-shield.git
cd cowork-shield
uv sync --extra dev
uv run python -m ensurepip
uv run python -m spacy download en_core_web_lg
```

Optional shell alias for daily usage:
```bash
alias cws='uv run cowork-shield'
```

## Verify
```bash
uv run cowork-shield --version
uv run pytest -q
uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py
```

Expected:
- CLI version prints successfully
- Test suite passes
- EC-15 state integrity gate passes

## Usage Quick Start
```bash
uv run cowork-shield anonymize ./sample.txt -w client-a
uv run cowork-shield restore ./sample.anonymized.txt -w client-a
```

First workspace sanity check:
```bash
uv run cowork-shield workspace list
uv run cowork-shield workspace show client-a
```

## Textual UI (Terminal)
Launch the terminal UI:
```bash
uv run cowork-shield-tui
```

Inside the TUI:
- Enter file path and workspace.
- Use buttons or hotkeys:
  - `p` preview entities
  - `a` anonymize
  - `r` restore
  - `w` refresh workspace list
  - `q` quit

## Gradio UI (Web)
Launch local web UI:
```bash
uv run cowork-shield-gradio
```

Default URL: `http://127.0.0.1:7860`

Features:
- Shield tab: upload file, select workspace, anonymize, download output, review entity table.
- Restore tab: upload anonymized file, select workspace, restore, download output.

Clipboard flow:
```bash
uv run cowork-shield shield-clipboard -w client-a
uv run cowork-shield restore-clipboard -w client-a
```

## Key Recovery (Admin)
Export encrypted recovery key:
```bash
uv run cowork-shield workspace export-key --workspace client-a --output ./client-a.recovery.key
```

Import encrypted recovery key:
```bash
uv run cowork-shield workspace import-key --workspace client-a --input ./client-a.recovery.key
```

Force replace existing Keychain entry (admin only):
```bash
uv run cowork-shield workspace import-key --workspace client-a --input ./client-a.recovery.key --force
```

## Notes
- Recovery key files are encrypted with your passphrase and written with `0600` permissions.
- If Keychain entry is deleted and no recovery export exists, workspace decryption is unrecoverable by design.
