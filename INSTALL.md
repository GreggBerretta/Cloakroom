# CoWork Shield Internal Install (HANDOFF B)

This install path is for the HANDOFF B internal validation build (no Swift/IPC).

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
git clone https://github.com/GreggBerretta/cowork-shield-fork.git
cd cowork-shield-fork
git checkout codex/handoff-b-status-doc
uv sync --extra dev
uv run python -m ensurepip
uv run python -m spacy download en_core_web_lg
uv run python -m spacy download he_core_news_sm || uv run python -m spacy download xx_ent_wiki_sm
```

If you are installing from the source repo instead of the fork:
```bash
git clone https://github.com/GreggBerretta/cowork-shield.git
cd cowork-shield
uv sync --extra dev
uv run python -m ensurepip
uv run python -m spacy download en_core_web_lg
uv run python -m spacy download he_core_news_sm || uv run python -m spacy download xx_ent_wiki_sm
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
uv run cowork-shield anonymize ./hebrew.txt -w client-a --language he
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
- Risky anonymize overrides require explicit confirmation in-app:
  - `Allow lossy XLSX`
  - `Force re-anonymize` (requires non-empty reason)
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
Security requirement: Gradio must stay bound to `127.0.0.1` only. Do not expose this service externally.

Features:
- Shield tab: upload file, select workspace, anonymize, download output, review entity table.
- Restore tab: upload anonymized file, select workspace, restore, download output.
- Risky overrides are gated with explicit confirmation:
  - `allow-lossy-xlsx`
  - `force-reanonymize` (requires a non-empty reason)

Clipboard flow:
```bash
uv run cowork-shield shield-clipboard -w client-a
uv run cowork-shield restore-clipboard -w client-a
uv run cowork-shield shield-clipboard -w client-a --language he
```

## Language Support
- Supported detection languages: `auto`, `en`, `he`
- CLI options:
  - `cowork-shield anonymize ... --language he`
  - `cowork-shield shield-clipboard ... --language he`
- UI options:
  - TUI language selector (`Auto`/`English`/`Hebrew`)
  - Gradio shield tab language dropdown (`auto`/`en`/`he`)

Current Hebrew caveats:
- Hebrew NER quality is moderate compared with English.
- `he_core_news_sm` may be unavailable in some spaCy distributions; fallback model is `xx_ent_wiki_sm`.
- Always validate high-stakes outputs during early pilot usage.

Operational note:
- Keep dependencies pinned by re-running `uv sync --extra dev` after pulling updates.

### Advanced Hebrew Recognition Backends
Default backend is `spacy` for deterministic local behavior.

Optional backend flags:
- `--hebrew-backend spacy|stanza|transformers`
- `--hebrew-stanza-model he`
- `--hebrew-transformer-model CordwainerSmith/GolemPII-v1`

Examples:
```bash
uv run cowork-shield anonymize ./hebrew.txt --language he --hebrew-backend stanza
uv run cowork-shield anonymize ./hebrew.txt --language he --hebrew-backend transformers --hebrew-transformer-model CordwainerSmith/GolemPII-v1
```

Install optional backend dependencies:
```bash
# Stanza backend
uv sync --extra hebrew_advanced
uv run python -c "import stanza; stanza.download('he')"
```

If you only want the transformers backend:
```bash
uv pip install transformers spacy-huggingface-pipelines
```

Environment variable equivalents:
```bash
export CWS_HEBREW_NLP_ENGINE=transformers
export CWS_HEBREW_TRANSFORMER_MODEL=CordwainerSmith/GolemPII-v1
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
