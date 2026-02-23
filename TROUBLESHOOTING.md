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
- `ColumnSelectionError`: invalid/missing spreadsheet column selection
- `IPCError`: IPC framing/envelope/protocol validation failure
- `WorkspaceExpiredError`: workspace TTL elapsed
- `RecoveryKeyError`: bad or wrong-passphrase recovery key payload
- `WorkspaceNotFoundError`: workspace metadata/key not found
- `LicenseKeyInvalidError`: supplied wrapper license key invalid
- `LicenseFeatureError`: attempted Pro-gated operation on Free tier
- `LicenseLimitExceededError`: free restore quota exceeded (daily)

UI-specific examples:
- `UnsupportedFormatError`: file extension not currently handled by pipeline
- `PdfExtractionError`: PDF extraction backend unavailable or extraction failed
- `PdfInputOnlyError`: attempted to restore from `.pdf` instead of tokenized `.md`/`.docx`
- `CoWorkShieldError`: generic surfaced error in TUI/Gradio operation wrapper
- `DetectionError`: language model missing or Presidio detection initialization/analysis failure

## 2) Safe Log Collection (No PII)
Collect these outputs only:

```bash
uv run cowork-shield --version
uv run python --version
uv run cowork-shield workspace list
uv run cowork-shield workspace show <workspace-name>
uv run cowork-shield logs export --workspace <workspace-name> --output ./support-logs.json
```

Also collect:
- command run
- timestamp
- full error line (including exception code)
- whether file was PDF/CSV/XLSX/DOCX/TXT/MD/clipboard

Do not share:
- original client files with live PII
- raw clipboard contents
- key export passphrases
- unsanitized manual dumps outside `logs export`

If restore failure involves anonymized output (tokenized only), file sharing is generally acceptable.
If anonymization failure involves live data, manually redact first.

Logging defaults:
- Location: `~/.cowork_shield/logs/`
- Permissions: `0600`
- Rotation: `10 MB x 5 files`
- Retention: `30 days`

If logs are not present:
- Check whether command used `--no-logging`
- Re-run with `--verbose` to increase diagnostic detail (still sanitized)

> [!WARNING]
> Do not post debug/support logs in public channels. Share only via approved internal support channels after review.

## 2b) IPC / Wrapper Hard-Fail Conditions
If wrapper integration reports protocol hard-fail:
- Verify Mode A or Mode B process is running:
```bash
# Mode A (default): subprocess stdio bridge
uv run cowork-shield ipc-stdio

# Mode B: AF_UNIX socket daemon
uv run cowork-shield ipc-server --socket-path ~/.cowork-shield/ipc/engine.sock
```
- Confirm wrapper and engine agree on protocol/schema hash via `HELLO`.
- For Mode B, confirm socket permissions remain `600`.
- Any partial/malformed frame is a hard-fail by design; restart wrapper and daemon after correction.
- If license metadata is missing from payload responses, treat as protocol drift and hard-fail.

Run pilot-blocking local security verification:
```bash
uv run cowork-shield workspace verify-security
```

## 2a) Column Selection Errors (CSV/XLSX)
Typical causes:
- Column name typo
- Letter out of range (for example `--columns Z` on a 5-column sheet)
- `--columns` used on non-spreadsheet file types
- Spreadsheet anonymize run with `--no-detect-pii` and no `--columns`

Quick checks:
```bash
uv run cowork-shield inspect-columns <file.csv|file.xlsx>
```

If you need combined behavior:
```bash
uv run cowork-shield anonymize <file.xlsx> --columns "Deal ID,Client Name" --detect-pii
```

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
   - sanitized support log bundle from `cowork-shield logs export`

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
Verify active bind:
```bash
netstat -an | grep 7860
```
Expected bind target: `127.0.0.1:7860` (never `0.0.0.0:7860`).
If spreadsheet columns do not appear:
- Re-upload the file to trigger column refresh.
- Confirm file extension is `.csv` or `.xlsx`.

Wrapper bridge note:
- When launched from Swift wrapper bridge, UI child processes inherit `CWS_WRAPPER_IPC_MODE`.
- `mode_a_stdio` is default; `mode_b_unix_socket` requires running `ipc-server` and valid socket path.

## 7) PDF Extraction Issues
PDF behavior:
- Input-only format: anonymize from `.pdf`, restore from `.md`/`.docx`.
- The app does not reconstruct original PDF binaries.

If PDF anonymize fails with `PdfExtractionError`:
```bash
# Ensure fallback backend exists
uv run python -c "import fitz; print('PyMuPDF OK')"

# Optional: install Docling for higher fidelity extraction
uv sync --extra pdf_docling
```

If you accidentally run restore on `.pdf`, rerun restore against the tokenized Markdown or DOCX output from anonymize.

## 8) Hebrew Detection Issues
> [!WARNING]
> Hebrew detection quality is currently lower than English. Treat Hebrew PII detection as assistive and verify high-stakes outputs manually during pilot.

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

If you selected `--hebrew-backend stanza`:
```bash
uv sync --extra hebrew_advanced
uv run python -c "import stanza; stanza.download('he')"
```

If you selected `--hebrew-backend transformers`:
```bash
uv sync --extra hebrew_advanced
# or: uv pip install transformers spacy-huggingface-pipelines
```

To use the specialized Golem model explicitly:
```bash
uv run cowork-shield anonymize <file> --language he --hebrew-backend transformers --hebrew-transformer-model CordwainerSmith/GolemPII-v1
```

## 9) Environment Repair
If `spacy download` fails with `No module named pip`:
```bash
uv run python -m ensurepip
```

If you see binary compatibility errors (for example `numpy.dtype size changed`):
```bash
uv sync --extra dev
```
