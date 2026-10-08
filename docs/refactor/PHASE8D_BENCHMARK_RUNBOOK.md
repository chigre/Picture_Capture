# Phase 8D Detection Benchmark Runbook

Phase 8D is a measurement gate, not a production-code optimization phase.

Use a representative Picture Capture project containing real dictionary pages, project settings, and preferably existing `.pdic` ground truth. Historical OCR debugging in this repository used real scans around pages 0055-0070; pages 55-60 are the preferred minimum benchmark slice when that project is available.

## Preconditions

- Run on the same machine/runtime that normally performs Picture Capture OCR.
- Use the real project settings and headword-filter rules.
- Use at least six representative dictionary pages. Preferred minimum: pages 55-60.
- Keep competing CPU/GPU-heavy workloads closed while measuring.
- Do not edit project data during the benchmark.
- Do not choose a production optimization from source inspection alone.

## Standard Phase 8D command

From the repository root:

```bash
python scripts/detection_benchmark.py "PROJECT_ROOT" \
  --modes left_edge,paddleocr,combined \
  --pages 55-60 \
  --force-ocr \
  --timing-repeats 4 \
  --warm-cpu-profile-dir phase8d_profiles_55_60 \
  --output phase8d_detection_55_60.json
```

On Windows PowerShell, the same arguments may be placed on one line.

### What this measures

For `paddleocr` and `combined`:

- the first call on each page is a forced cold OCR/cache-refresh call;
- the next three calls reuse the same temporary cache with `force_paddle_refresh=False`;
- the formal detection/ground-truth result always comes from the first call;
- warm repeats are timing-only and never overwrite the formal result;
- after wall-clock timing completes, a separate unprofiled warm-up plus one warm cProfile call is executed per selected page/mode.

For `left_edge`, the same repeat count provides a non-OCR CPU baseline.

The cProfile calls are not wall-clock timing samples.

## Minimum validity checks

Do not use the run to choose a production optimization unless all of the following hold:

1. Every selected mode completes all six pages.
2. `repeat_errors` is empty for every page/mode.
3. For OCR modes:
   - `cache.enabled == true`;
   - `cache.exists_before_first == false`;
   - `cache.exists_after_first == true`;
   - `cache.first_run_force_refresh == true`;
   - `cache.repeat_force_refresh == false`.
4. Each OCR mode contributes at least 18 warm-repeat timings across pages 55-60 (6 pages x 3 repeats).
5. Warm-profile manifest entries have no `error` and produce both `.prof` and cumulative top-50 `.txt` output.
6. If `.pdic` ground truth exists, accuracy/count fields remain plausible and no timing experiment changes the formal first-run result.

If any requirement fails, fix the benchmark/runtime problem first; do not optimize production code from that run.

## Decision rules

Use the JSON timing fields and warm cumulative profiles together.

### Cold OCR dominates

If first-run `paddleocr`/`combined` time is much larger than warm-repeat time, while the warm profile does not show one orchestration/cache helper dominating cumulative CPU:

- treat OCR inference/model startup as the cold bottleneck;
- do not micro-optimize Python orchestration merely because it is easy to edit;
- first consider whether normal user workflows already benefit from cache reuse.

### Warm cache/orchestration dominates

If warm-repeat time remains material and the warm profile repeatedly concentrates cumulative time in cache compaction, JSON publishing, diagnostics/quality-summary generation, or another repeated non-inference path:

- select the highest repeated cumulative-cost production path;
- make one bounded optimization;
- rerun the same Phase 8D command and compare warm median/p95 plus correctness fields.

### Image/metadata I/O is material

If `timing_ms.image_load` or `timing_ms.metadata_io` is a substantial component of `page_total` across pages:

- treat that as a separate I/O optimization problem;
- do not attribute it to OCR/detection CPU.

### Detection CPU dominates

If `left_edge` or warm `combined` remains expensive and the profile points to one detection/recovery/fusion chain rather than cache/reporting work:

- optimize that specific measured chain;
- preserve detection counts/ground-truth metrics and rerun the same benchmark.

## Required artifacts for the first production optimization

Keep together:

- `phase8d_detection_55_60.json`;
- the full `phase8d_profiles_55_60/` directory;
- machine/runtime notes: OS, Python version, CPU/GPU device used by Paddle, and whether competing heavy workloads were closed.

The first production optimization should cite the measured bottleneck from these artifacts in its PR description.

## Current repository-data boundary

The repository itself does not contain a representative Picture Capture project. It contains example headword crops and layout screenshots, but not the real page set, project settings, `.pdic` ground truth, and OCR diagnostics needed for a trustworthy Phase 8D performance conclusion.

Therefore the absence of a benchmark result is a data-access boundary, not evidence that no optimization is needed.
