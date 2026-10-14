# PC-CQ/B1 — Quality gates, traceable benchmarks and OCR safety

Scope: R0.2, R1.1, R1.2, R1.3. **No OCR model, candidate score, PDIC format, or default setting is changed.**

## 1. Claims and data provenance

The following evidence classes are NOT interchangeable:

| run_type | Source | Permitted conclusion |
| --- | --- | --- |
| `synthetic_fixture` | `tests/fixtures/headword_quality_v1.json` | Algorithms and matching contracts satisfy deterministic examples. **Not** a real-scan F1. |
| `historic_cache` | `scripts/benchmark_training_archives.py` | Metrics for saved OCR results in an older archive. **Not** the current detector. |
| `current_detector` | `scripts/detection_benchmark.py` or complete training-archive rerunner | The checked-out detector ran on inputs; a saved PDIC is **not independently validated GT** unless separately audited. |

**PR-B real scanned-page benchmarking remains deferred**. Golden fixtures have no copyrighted page pixels and are synthetic; they cannot reproduce Otsu, font boldness, oversized CJK image recovery, OCR engine drift, or pixel-based separator placement.

## 2. Metric contract

Source file: `src/picture_capture/detection_quality_metrics.py`.

- Inputs are canonical `(column, reading_axis_v)` coordinates, not display pixels, list positions or untransformed source Y.
- Predicted and reference markers match **within the same column** using the existing monotone maximum-cardinality then minimum-displacement matcher. No duplicated matches.
- Tolerance is a **nonnegative canonical coordinate distance**; out-of-tolerance points are unmatched.
- `TP` is the number of matched markers, `FP` unmatched predictions and `FN` unmatched references.
- `precision=TP/(TP+FP)`, `recall=TP/(TP+FN)`, `F1=2PR/(P+R)`; pooled results are calculated from sum of counts (micro), **not average per-page F1**.
- Preserve existing single-page empty/empty semantics: P=R=F1=1 and exact=true, but *an unlabeled page is not an empty verified reference*. If there is no authoritative PDIC the caller must not score it.
- Y error median and P95 are **conditional on successfully matched markers** and are not proof that a horizontal line avoids ink. The original benchmark upper median / rounded rank P95 convention is preserved for compatibility.
- OCR text correctness, boundary/ink crossing, manual time, and FP/FN are separate; do not infer them from one scalar F1.

## 3. CI fixtures and commands

**Guaranteed reproducible without copyrighted images or actual OCR**:

```bash
uv run --locked pytest -q tests/test_headword_quality_golden_20261014.py
uv run --locked pytest -q tests/test_b1_benchmark_provenance_20261014.py
uv run --locked pytest -q tests/test_b1_merged_ocr_safety_20261014.py
uv run --locked python scripts/architecture_guard.py
uv run --locked python scripts/change_architecture_guard.py --base origin/main
```

The ordinary CI suite also runs pytest, GUI smoke, source compilation and Python 3.10 compatibility on supported platforms. CI fixture success is a **correctness gate**, not a claim of any improved F1 on real dictionary scans.

Golden fixture schema: `format`, `run_type`, `label_status`, `coordinate_space`, `examples` with id, tolerance, predicted/reference pairs, expected outputs. Every fixture is labeled `synthetic_contract_only_not_human_truth`. Never relabel these as manually verified scans.

## 4. Read-only benchmark report

To produce **separate** JSON/Markdown summaries from existing saved reports:

```bash
uv run --locked python scripts/quality_report.py historic_audit.json regenerated_current.json --json-output outputs/quality.json --markdown-output outputs/quality.md
```

The report explicitly lists the input file, evidence type, dictionary/mode, available TP/FP/FN and F1. Unknown report formats or contradictory `run_type` declarations fail closed. Image-only/no-ground-truth archives are not assigned a fabricated F1. **No pooling historical and current results** is permitted.

For real full-scan runtime and reproducibility, follow `docs/refactor/PHASE8D_BENCHMARK_RUNBOOK.md` and `docs/headword_boundary_upgrade_20261012.md` only when real scans become available and PR-B is authorized.

## 5. B1 verification and omissions

**R0.2**: default-off behavior for #475/#476/#477, old-settings import, save/restore options, checkable settings schema, PDIC lossless backup before overwrite, snapshot collision and final audit integration order.

**R1.1**: shared ordered matching uses prior algorithm, can be called without UI; deterministic cases include close neighbors, multiple columns, duplicates, empty, tolerance and micro-F1.

**R1.2**: synthetic fixture CI checks with provenance labels. No distribution-level detector performance claim.

**R1.3**: historical/current report provenance and read-only Markdown/JSON aggregation; existing scripts retain historic and actual-detector separation.

Not included: changing OCR scoring weights, modifying UI defaults, adding true image-level golden files to the repository, tuning an accuracy threshold from old OCR caches, running remote OCR or collecting keyboard/user telemetry.
