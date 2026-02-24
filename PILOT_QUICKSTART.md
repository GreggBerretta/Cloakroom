# CoWork Shield Pilot Quickstart (One Page)

Use this for pilot onboarding and daily operation.

## 1) Install
```bash
uv sync --extra dev
uv run python -m ensurepip
uv run python -m spacy download en_core_web_lg
uv run python -m spacy download he_core_news_sm || uv run python -m spacy download xx_ent_wiki_sm
```

## 2) Mandatory First Run
```bash
uv run cowork-shield onboarding --workspace default
```
This step creates workspace state and exports encrypted recovery key.

## 3) Safety Checks (Pilot Blockers)
```bash
uv run cowork-shield workspace verify-security
# Optional raw fallback check (canonical vault path)
stat -f "%Sp %N" ~/.cowork-shield/workspaces/*/vault.enc
uv run pytest -q tests/test_state_integrity/test_ec15_state_integrity.py
```

## 4) Core Workflow
```bash
# anonymize file
uv run cowork-shield anonymize ./client_notes.txt -w client-a

# run through LLM externally (tokenized content only)

# restore output
uv run cowork-shield restore ./client_notes.anonymized.txt -w client-a
```

## 5) Spreadsheet Column-Selective Mode
```bash
uv run cowork-shield inspect-columns ./deals.xlsx
uv run cowork-shield anonymize ./deals.xlsx -w client-a --columns "Deal ID,Client Name"
uv run cowork-shield anonymize ./deals.xlsx -w client-a --columns "Deal ID,Client Name" --detect-pii
```

## 6) Critical Warnings
- PDF is input-only: outputs are `.md` or `.docx`, never reconstructed `.pdf`.
- XLSX with charts/images requires explicit lossy override (`--allow-lossy-xlsx`).
- Hebrew detection quality is moderate (lower than English); validate sensitive outputs.
- If Keychain entry is lost and no recovery key exists, restore is cryptographically impossible.

## 7) Get Support
```bash
uv run cowork-shield logs export --workspace client-a --output ./support-logs.json
```
Share only sanitized export via the internal support channel.
