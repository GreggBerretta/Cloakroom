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

## Hebrew Benchmark Update (Post-Optimization)
- Date: 2026-02-23 15:00 UTC
- Host: Apple M4, macOS 26.3, Python 3.12.12
- Hebrew model availability:
  - `he_core_news_sm`: not installed
  - `xx_ent_wiki_sm`: installed (fallback path)
- Detector mode: `--language he` (spaCy backend path)

### Dataset / Method
- Synthetic Hebrew CSV with 10,000 rows:
  - `name`, `email`, `company`, `phone`, `notes`
  - Example row values include Hebrew script names/notes and email/phone fields.
- Hebrew markdown and DOCX sample documents also benchmarked.
- Commands timed end-to-end via CLI wall-clock:
  - `uv run cowork-shield anonymize <he_10k.csv> -w <ws> --language he`
  - `uv run cowork-shield restore <he_10k.anonymized.csv> -w <ws>`
  - Column-only and hybrid variants:
    - `--columns "A,C" --no-detect-pii`
    - `--columns "A,C" --detect-pii`
  - Markdown/DOCX:
    - `uv run cowork-shield anonymize <file> -w <ws> --language he`
    - `uv run cowork-shield restore <anonymized_file> -w <ws>`

### Hebrew Results
- 10k Hebrew CSV anonymize (full detect): **45.89s**
- 10k Hebrew CSV restore (full detect path): **0.77s**
- 10k Hebrew CSV anonymize (column-only): **1.94s**
- 10k Hebrew CSV restore (column-only): **0.86s**
- 10k Hebrew CSV anonymize (column + pii): **30.05s**
- 10k Hebrew CSV restore (column + pii): **0.90s**
- Hebrew markdown anonymize: **1.86s**
- Hebrew markdown restore: **0.62s**
- Hebrew DOCX anonymize: **1.84s**
- Hebrew DOCX restore: **0.64s**

### Observations
- Hebrew spreadsheet anonymization is significantly faster than prior English full-detect baseline in this environment, but still high in full-detect mode.
- Column-only remains the fastest and most stable path for user-perceived responsiveness.
- Restore latency is now sub-second for all measured Hebrew document paths in this benchmark.
