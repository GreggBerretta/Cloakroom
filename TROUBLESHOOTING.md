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

