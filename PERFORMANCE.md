# CoWork Shield Performance Baseline (HANDOFF B)

## Baseline Context
- Date: 2026-02-22 13:12:13 UTC
- Scope: HANDOFF B internal validation baseline
- Host: Gregg’s Mac mini
- CPU: Apple M4
- Python: 3.12.12 (`uv run python -V`)
- OS: macOS 26.3 (Build 25D125)

## Dataset / Method
- File benchmark dataset: synthetic CSV with 10,000 rows and columns:
  - `name`, `email`, `company`, `phone`, `notes`
- Commands timed end-to-end via CLI wall-clock:
  - `uv run cowork-shield anonymize <10k.csv> -w perf-baseline-file`
  - `uv run cowork-shield restore <10k.anonymized.csv> -w perf-baseline-file`
- Clipboard benchmark text:
  - `John Smith at Acme Corp can be reached at john.smith@example.com or (212) 555-1234.`
- Clipboard measured across 5 runs using:
  - `uv run cowork-shield shield-clipboard -w perf-baseline-clipboard`
  - `uv run cowork-shield restore-clipboard -w perf-baseline-clipboard`

## Baseline Results
- 10k-row CSV anonymize: **95.74 seconds**
- 10k-row CSV restore: **11.49 seconds**
- Clipboard operation (shield median): **1.07 seconds**
- Clipboard operation (restore median): **0.50 seconds**
- Clipboard round-trip (shield + restore median): **1.57 seconds**

## Raw Clipboard Runs
- Shield runs (s): 1.13, 1.12, 1.07, 1.07, 1.06
- Restore runs (s): 0.50, 0.50, 0.50, 0.50, 0.50

## Notes
- This is a one-time pilot baseline for comparison when slowness is reported.
- No automated thresholds are enforced from this file yet.
