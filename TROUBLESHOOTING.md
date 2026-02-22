# CoWork Shield Troubleshooting (HANDOFF B)

This runbook covers internal support for the HANDOFF B validation project.

## 1) Error Codes
CLI errors print as:
`Error [<ExceptionClass>]: ...`

Treat `<ExceptionClass>` as the support error code.

Common examples:
- `IntegrityError`: vault mapping HMAC mismatch; fail-closed restore
- `ReplayMismatchError`: deterministic replay mismatch
- `ModelHashMismatchError`: model lock mismatch
- `HallucinationDetectedError`: mutated/hallucinated/dropped token detected
- `WorkspaceExpiredError`: workspace TTL elapsed
- `RecoveryKeyError`: bad or wrong-passphrase recovery key payload
- `WorkspaceNotFoundError`: workspace metadata/key not found

UI-specific examples:
- `UnsupportedFormatError`: file extension not currently handled by pipeline
- `CoWorkShieldError`: generic surfaced error in TUI/Gradio operation wrapper
- `DetectionError`: language model missing or Presidio detection initialization/analysis failure

## 2) Safe Log Collection (No PII)
Collect these outputs only:

```bash
uv run cowork-shield --version
uv run python --version
uv run cowork-shield workspace list
uv run cowork-shield workspace show <workspace-name>
```

Also collect:
- command run
- timestamp
- full error line (including exception code)
- whether file was CSV/XLSX/DOCX/TXT/clipboard

Do not share:
- original client files with live PII
- raw clipboard contents
- key export passphrases

If restore failure involves anonymized output (tokenized only), file sharing is generally acceptable.
If anonymization failure involves live data, manually redact first.

## 3) Keychain / Recovery Failures
Symptom:
- `WorkspaceNotFoundError` with keychain message

Recovery:
1. Obtain encrypted recovery key file (`*.recovery.key`).
2. Import:
```bash
uv run cowork-shield workspace import-key --workspace <workspace-name> --input <path>
```
3. Retry command.

Admin override (replace existing keychain entry):
```bash
uv run cowork-shield workspace import-key --workspace <workspace-name> --input <path> --force
```

## 4) EC-15 Failure Procedure
If state-integrity behavior is suspected:
1. Re-run EC-15 harness:
```bash
uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py
```
2. Capture failing test ID(s).
3. Open incident with:
   - failing test ID
   - exception code
   - reproduction steps
   - OS + Python versions

## 5) Support Escalation
Use internal support channel:
- Slack: `#cowork-shield-pilot`
- Backup email: `security@coworkshield.local` (replace with real alias)

Escalate immediately for:
- any silent mismatch concerns
- irreversible restore inability
- deterministic replay failures in production workflow

## 6) UI Launch Troubleshooting
Textual UI:
```bash
uv run cowork-shield-tui
```
If it fails, verify dependency install:
```bash
uv sync --extra dev
```

Gradio UI:
```bash
uv run cowork-shield-gradio
```
Security requirement: keep Gradio on localhost (`127.0.0.1`) only. Do not bind `0.0.0.0` or expose via external reverse proxy.
If port is in use, launch manually with a custom port:
```bash
uv run python -c "from cowork_shield.ui.gradio_app import create_demo; create_demo().launch(server_name='127.0.0.1', server_port=7861)"
```

## 7) Hebrew Detection Issues
If Hebrew detection fails to initialize:
```bash
uv run python -m spacy download he_core_news_sm || uv run python -m spacy download xx_ent_wiki_sm
```

The detector prefers `he_core_news_sm` and automatically falls back to `xx_ent_wiki_sm` if available.

If auto language selection is unstable for short text, force explicit language:
```bash
uv run cowork-shield anonymize <file> --language he
uv run cowork-shield shield-clipboard --language he
```

## 8) Environment Repair
If `spacy download` fails with `No module named pip`:
```bash
uv run python -m ensurepip
```

If you see binary compatibility errors (for example `numpy.dtype size changed`):
```bash
uv sync --extra dev
```
