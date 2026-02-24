# CoWork Shield Performance Bottleneck Technical Report

## 1) Purpose
This document is a technical handoff for external performance experts.

It consolidates:
- all known performance targets
- all measured performance metrics to date
- all failed performance cases (listed individually)
- optimizations already attempted and their effects
- current bottleneck hypotheses and recommended next experiments

Scope is the HANDOFF_B-based fork implementation with v11 launch-prep additions.

## 2) Performance Targets (Current Gate)
From Phase 2 v11 launch requirements:
- 10k-row CSV anonymize: **<= 8.0s**
- 10k-row CSV restore: **<= 2.0s**
- Clipboard round-trip (shield + restore): **<= 1.5s**

## 3) Measurement Environment
Known benchmark host metadata (from project baseline docs):
- Hardware: Apple Silicon Mac mini (M4 in recorded baseline)
- OS: macOS 26.3 (recorded baseline)
- Python: 3.12.x (`uv` managed)
- Engine: local-only Presidio/spaCy pipeline, encrypted local vault

## 4) Full Performance Metrics Collected So Far

### 4.1 Baseline (2026-02-22)
Source: `PERFORMANCE.md`
- 10k-row CSV anonymize (English): **95.74s**
- 10k-row CSV restore (English): **11.49s**
- Clipboard shield median: **1.07s**
- Clipboard restore median: **0.50s**
- Clipboard round-trip median: **1.57s**

### 4.2 Hebrew Benchmark Set (2026-02-23)
Source: `PERFORMANCE.md`
- 10k-row CSV anonymize (Hebrew full detect): **45.89s**
- 10k-row CSV restore (Hebrew full detect): **0.77s**
- 10k-row CSV anonymize (Hebrew column-only): **1.94s**
- 10k-row CSV restore (Hebrew column-only): **0.86s**
- 10k-row CSV anonymize (Hebrew column + pii): **30.05s**
- 10k-row CSV restore (Hebrew column + pii): **0.90s**
- Hebrew markdown anonymize: **1.86s**
- Hebrew markdown restore: **0.62s**
- Hebrew DOCX anonymize: **1.84s**
- Hebrew DOCX restore: **0.64s**

### 4.3 v11 Launch-Gate Benchmark (2026-02-24)
Command used:
- `uv run cowork-shield benchmark-performance --rows 10000 --language en --output /tmp/cws_perf_en.json`
- `uv run cowork-shield benchmark-performance --rows 10000 --language he --output /tmp/cws_perf_he.json`

Results:
- English 10k CSV anonymize: **48.95s**
- English 10k CSV restore: **0.16s**
- English clipboard shield: **0.059s**
- English clipboard restore: **0.111s**
- English clipboard round-trip: **0.170s**

- Hebrew 10k CSV anonymize: **20.00s**
- Hebrew 10k CSV restore: **0.14s**
- Hebrew clipboard shield: **0.071s**
- Hebrew clipboard restore: **0.113s**
- Hebrew clipboard round-trip: **0.184s**

## 5) Performance Failures (All Listed Separately)

### PF-001: 10k CSV anonymize (English) exceeds gate
- Target: <= 8.0s
- Observed:
  - 95.74s (baseline)
  - 48.95s (current v11 benchmark)
- Failure magnitude (latest): **+40.95s over target**
- Status: **Open / unresolved**

### PF-002: 10k CSV anonymize (Hebrew) exceeds gate
- Target: <= 8.0s
- Observed:
  - 45.89s (Hebrew benchmark set)
  - 20.00s (current v11 benchmark)
- Failure magnitude (latest): **+12.00s over target**
- Status: **Open / unresolved**

### PF-003 (historical): 10k CSV restore exceeded gate before restore-path optimizations
- Target: <= 2.0s
- Observed historical: 11.49s
- Current observed: 0.16s (English), 0.14s (Hebrew)
- Status: **Resolved**

### PF-004 (historical): Clipboard round-trip exceeded gate in early baseline
- Target: <= 1.5s
- Observed historical: 1.57s
- Current observed: 0.17-0.18s
- Status: **Resolved**

## 6) What Has Been Tried So Far

### 6.1 Early cell-level detection pruning
Implemented in `src/cowork_shield/handlers/pii_prefilter.py`.
- Skips empty/tiny/punctuation/no-signal cells before NER.
- Avoids re-detecting already-tokenized values.
- Effect: reduced wasted detector calls; did not solve 10k full-detect latency alone.

### 6.2 Detection engine caching and fast language paths
Implemented in `src/cowork_shield/detection/engine.py`.
- Cell detection result cache (`_cell_detection_cache`) for repeated short values.
- Fast language path:
  - Hebrew script quick detect
  - ASCII short-circuit to English
  - avoids costly language detection per cell where possible
- Effect: improved throughput vs earliest baseline, especially repetitive data.

### 6.3 Row-batched detection pass for CSV/XLSX
Implemented in:
- `src/cowork_shield/handlers/csv_handler.py`
- `src/cowork_shield/handlers/xlsx.py`

Approach:
- merge candidate cells in a row with delimiter
- run detector once per row candidate set
- remap offsets back to per-cell entities

Effect:
- English anonymize improved from 95.74s to 48.95s on 10k benchmark
- Hebrew anonymize improved from 45.89s to 20.00s on 10k benchmark
- Still above 8s gate.

### 6.4 Restore-path fast skip for non-token cells
Implemented in CSV/XLSX restore handlers.
- skip expensive replacement attempts when cell lacks token-like markers
- Effect: major restore gains; restore now comfortably below 2s target.

### 6.5 Column-selective workflow (bypass detector where user-selected)
Implemented in spreadsheet handlers + CLI/UI.
- column-only mode can keep large-sheet anonymization near-instant relative to full detect.
- Example metric: Hebrew 10k column-only anonymize 1.94s.
- Effect: practical workaround for many consulting workflows, but does not satisfy full-detect gate requirement.

### 6.6 Benchmark harness + CI gate added
Implemented in:
- `src/cowork_shield/performance/benchmark.py`
- `src/cowork_shield/cli.py` (`benchmark-performance`)
- `.github/workflows/performance-gate.yml`

Effect:
- repeatable measurements and explicit pass/fail telemetry.
- does not improve runtime itself.

## 7) Current Bottleneck Hypotheses

### H-001: NER invocation cost remains dominant even after row batching
Evidence:
- Anonymize remains far above target while restore and clipboard are fast.
- Full-detect spreadsheets are slow; column-only mode is fast.

### H-002: Python-level structured file I/O + detector interaction overhead is still high
Evidence:
- CSV/XLSX full-detect times remain high despite reductions in detector call count.
- Per-row remapping and replacer passes may still add substantial overhead at 10k scale.

### H-003: Hebrew backend/model path cost remains materially higher than target budget
Evidence:
- Hebrew improved strongly but remains 2.5x above target.
- Additional backend choices may trade accuracy vs speed; currently not auto-optimized by corpus profile.

## 8) What Has Not Yet Been Implemented
- detector batching at larger chunk granularity than row-level (with robust offset mapping)
- alternative fast-path recognizer stack for common PII patterns before Presidio NER
- profile-based engine mode ("speed" vs "accuracy") with explicit operational policy
- low-level profiling traces (cProfile/py-spy flamegraphs) attached to benchmark artifacts
- compiled/vectorized anonymization data paths for large structured sheets

## 9) Recommended Expert Work Package

### 9.1 Immediate Profiling Package
Run and deliver:
- per-function CPU profile for 10k CSV anonymize (English/Hebrew)
- call-count heatmap for detection + replacement + file I/O
- memory profile over full run

### 9.2 Candidate Optimization Experiments
1. Chunked detector calls across multi-row blocks with stable offset mapping.
2. Regex/context first-pass extraction for common entities (email/phone/id) to reduce NER volume.
3. Parallelized detection workers (process-based) for spreadsheet chunks while preserving deterministic token assignment ordering.
4. Optional high-speed backend profile for pilot mode with explicit confidence boundaries.

### 9.3 Acceptance Criteria for Expert Fix Validation
- English 10k CSV anonymize <= 8.0s on M1+
- Hebrew 10k CSV anonymize <= 8.0s on M1+
- deterministic replay, fail-closed guarantees, and EC-15 integrity tests remain green

## 10) Relevant Code and Artifacts for Expert Review

Core paths:
- `src/cowork_shield/handlers/csv_handler.py`
- `src/cowork_shield/handlers/xlsx.py`
- `src/cowork_shield/detection/engine.py`
- `src/cowork_shield/handlers/pii_prefilter.py`
- `src/cowork_shield/pipeline/anonymize.py`
- `src/cowork_shield/performance/benchmark.py`

Benchmark docs:
- `PERFORMANCE.md`

Benchmark artifact examples:
- `/tmp/cws_perf_en.json`
- `/tmp/cws_perf_he.json`

## 11) Bottom Line
- Reliability and recoverability controls are strong.
- Restore and clipboard latency targets are met.
- The only unresolved performance gate is full-detect 10k CSV anonymize (English and Hebrew).
- Current improvements are significant but insufficient for v11 launch thresholds.
