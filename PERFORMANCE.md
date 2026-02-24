# Cloakroom Performance Baseline (HANDOFF B)

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
  - `uv run cloakroom anonymize <10k.csv> -w perf-baseline-file`
  - `uv run cloakroom restore <10k.anonymized.csv> -w perf-baseline-file`
- Clipboard benchmark text:
  - `John Smith at Acme Corp can be reached at john.smith@example.com or (212) 555-1234.`
- Clipboard measured across 5 runs using:
  - `uv run cloakroom shield-clipboard -w perf-baseline-clipboard`
  - `uv run cloakroom restore-clipboard -w perf-baseline-clipboard`

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
  - `uv run cloakroom anonymize <he_10k.csv> -w <ws> --language he`
  - `uv run cloakroom restore <he_10k.anonymized.csv> -w <ws>`
  - Column-only and hybrid variants:
    - `--columns "A,C" --no-detect-pii`
    - `--columns "A,C" --detect-pii`
  - Markdown/DOCX:
    - `uv run cloakroom anonymize <file> -w <ws> --language he`
    - `uv run cloakroom restore <anonymized_file> -w <ws>`

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

## v11 Launch Gate Benchmark (Revised)
- Prior run date: 2026-02-24 05:38 UTC
- Revised run date: 2026-02-24 06:17 UTC
- Revised commands:
  - `uv run cloakroom benchmark-performance -w perf-opt2-en-balanced --rows 10000 --language en --detection-mode balanced -o /tmp/cloakroom_perf2_en_balanced.json`
  - `uv run cloakroom benchmark-performance -w perf-opt2-en-speed --rows 10000 --language en --detection-mode speed -o /tmp/cloakroom_perf2_en_speed.json`
  - `uv run cloakroom benchmark-performance -w perf-opt2-he-balanced --rows 10000 --language he --detection-mode balanced -o /tmp/cloakroom_perf2_he_balanced.json`
  - `uv run cloakroom benchmark-performance -w perf-opt2-he-speed --rows 10000 --language he --detection-mode speed -o /tmp/cloakroom_perf2_he_speed.json`

### Results vs v11 Targets
| Metric | Target (v11) | Prior (EN/HE) | Revised (EN balanced / HE balanced) | Status |
| --- | --- | ---:| ---:| --- |
| CSV anonymize | <= 8.0s | 48.95s / 20.00s | 1.96s / 1.71s | PASS |
| CSV restore | <= 2.0s | 0.16s / 0.14s | 0.21s / 0.19s | PASS |
| Clipboard round-trip | <= 1.5s | 0.17s / 0.18s | 0.19s / 0.15s | PASS |

Speed profile reference:
- English anonymize (speed): 1.95s
- Hebrew anonymize (speed): 1.60s

### Interpretation
- v11 launch performance budgets are currently met for both English and Hebrew benchmark corpus runs.
- Largest improvement is anonymize latency from:
  - English: 48.95s -> 1.96s (~96.0% faster)
  - Hebrew: 20.00s -> 1.71s (~91.4% faster)
