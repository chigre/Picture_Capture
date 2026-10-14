# Ordinary drawing: single GPU producer + bounded CPU consumers (experimental)

## Context and safety

The previously default six-worker ordinary batch (#491) was rolled back by
#492 after a Windows 24-core workstation experienced six stalled pages and
saturated GPU VRAM/host memory. Ordinary drawing does not recognize text with
OCR, but optional per-page **automatic Layout** still runs GPU-capable Paddle
`TextDetection`. Six independent Windows-spawn processes each initialized a
full detector and private full-resolution image buffers.

This implementation retains the proven-safe **one-worker default**. It adds an
explicitly opt-in, two-stage producer/consumer path; no auto-enablement based
on CPU count, GPU count or generous installed RAM.

## How it works

With ordinary `left_edge`, **automatic Layout enabled**, *Layout illustration
masking disabled*, identity transform, and at least two selected pages:

1. Exactly **one persistent spawned GPU producer** reads each page, resolves
   effective Profile settings, builds the same analysis image and obtains the
   existing reliable `LayoutEstimate` via the same
   `layout_detection.detect_layout_parameters`. GPU detection has NO PDIC
   write permission in this stage.
2. A tiny pickleable estimate + page/settings/source identity are handed off
   to a **maximum of two separate CPU page-processing workers**, never the
   Paddle model or full-resolution pixels. Each CPU worker rebuilds the page's
   usual analysis view, consumes exactly the same prepared geometry once in
   `dictionary_page_layout_policy.detect_layout_parameters`, and uses the
   existing Layout Core, remaining ordinary evidence and the unchanged
   `detect_entries_job` per-page PDIC/baseline writer.
3. The CPU worker blocks additional calls to GPU TextDetection and fails before
   PDIC publication if estimate settings/size do not match, if the file changed
   after GPU preflight, if the estimate is consumed more than once/not at all,
   or if an unexpected detector path tries to initialize a second model.
4. The existing batch coordinator submits at most **two CPU jobs** and at
   most **one GPU preflight** at once. Manual pending→locked and
   pending→processing transitions share one UI-side lock; already processing
   pages are read-only until written and reloaded. Stop/pause prevent new
   dispatch; already claimed work finishes safely.

The GPU preflight and CPU execution are sequential *per page*, but
**pipelined across pages**. Once the first page has completed GPU Layout
preflight, CPU postprocessing can overlap with the second page's GPU stage.
Throughput gains are bounded by the time spent in CPU-only stages; no
multiplicative speedup is promised.

## How to enable a controlled trial

Default (no variable set): **old safe single-process mode**, even on 24 CPUs.
On Windows PowerShell:

```powershell
# Only in the PowerShell session launching the updated application:
$env:PICTURE_CAPTURE_ORDINARY_GPU_PIPELINE = "1"
# Run Picture_Capture normally from that session; select 2+ ordinary pages.

# Return to the safe one-process fallback:
Remove-Item Env:PICTURE_CAPTURE_ORDINARY_GPU_PIPELINE
```

Do NOT set `PICTURE_CAPTURE_ORDINARY_WORKERS=6` or `8` to activate this.
The old #492 safety rollback remains enforced: that override is ignored.
The supported experimental path is **one GPU model + two CPU workers**, not
N GPU models. It does not run when auto-Layout is off, illustration masking is
on, or transform is nonidentity.

## Acceptance before default enablement

Tests without private scanned pages prove dispatch and configuration
invariants, but are not real GPU peak-memory measurements.

On COPIES of representative scanned dictionary projects:

- Compare ordinary saved PDIC **coordinates, words, and ordering** with the
  same settings and the default one-worker path; compare automatic baseline
  entries/geometry rather than incidental timestamps.
- Measure per-page preflight GPU time, CPU stage time, total elapsed, peak
  VRAM, private RSS and OS RAM, and startup overhead on 12–30 pages.
- Verify CPU workers instantiate **zero** GPU TextDetection models, the GPU
  producer creates **one reusable** model, and preflight consumes no PDIC.
- Test edit of a still-pending page, pause/resume, stopping during preflight,
  page scan changed during a run, GPU model error, and crash/restart.
- Reject production default enablement if byte-level output parity or stable
  bounded memory cannot be demonstrated. This feature flag is deliberately
  temporary and may be disabled after trials.

Do not change OCR/fusion modes, saved PDIC/SECTION/Profile schema or PC-CQ
B2 #483 while tuning this experimental speedup.

## Alternative experiment: independent CPU-only page workers

A second **OFF-by-default** experimental route was added after reviewing the
PaddleOCR TextDetection 3.x `cpu_threads` interface:

- `PICTURE_CAPTURE_ORDINARY_CPU_POOL=1` selects **independent CPU-only** page
  workers. Each Windows-spawned process is reused for multiple pages and
  runs the original per-page ordinary detection/writer. No shared GPU stage is
  involved in this alternative. If both CPU and single-GPU flags are set,
  explicit CPU mode takes precedence.
- Automatic parallelism is **2 CPU processes**, not 6. Explicit
  `PICTURE_CAPTURE_ORDINARY_CPU_WORKERS` accepts 1, 2, 4 or 6; it is capped
  by selected pages and logical CPUs, with **6 as the experimental maximum**.
- `PICTURE_CAPTURE_ORDINARY_CPU_THREADS` caps the number of Paddle inference
  threads per worker (1–4, additionally bounded by total logical CPUs divided
  by the process count). When unspecified, 24 logical CPUs with 6 workers
  yields up to 4 inference threads each. The operating system and other
  NumPy/BLAS threads also need CPU resources; this budget is NOT a promise
  of 24 total OS threads.
- At the Paddle `TextDetection` constructor, this path explicitly supplies
  `device="cpu"`, `cpu_threads=N`, `enable_mkldnn=False`. If installed
  PaddleOCR does not support that complete argument set, the page fails
  closed instead of silently discarding the CPU device and starting CUDA.
- `OMP_NUM_THREADS` is an advisory limit applied at worker entry; libraries
  imported before the entrypoint may already have initialized their own
  thread pools. Explicit `cpu_threads` is the detector control.
- This path also forbids `layout_mask_illustrations=True` and nonidentity
  page transforms until their other possible model/device dependencies have
  been verified. Ordinary auto-layout may be enabled or disabled.

For a controlled Windows A/B test, in PowerShell **before launching the app**:

```powershell
$env:PICTURE_CAPTURE_ORDINARY_CPU_POOL = "1"
$env:PICTURE_CAPTURE_ORDINARY_CPU_WORKERS = "2"
$env:PICTURE_CAPTURE_ORDINARY_CPU_THREADS = "3"
# Run Picture_Capture normally from this session on a COPY of test scans.

# After establishing memory and output correctness, separately test 4 then 6:
$env:PICTURE_CAPTURE_ORDINARY_CPU_WORKERS = "4"

# Restore fully safe #492 default:
Remove-Item Env:PICTURE_CAPTURE_ORDINARY_CPU_POOL
Remove-Item Env:PICTURE_CAPTURE_ORDINARY_CPU_WORKERS
Remove-Item Env:PICTURE_CAPTURE_ORDINARY_CPU_THREADS
```

**Do not turn on `enable_mkldnn=True` casually.** This project has explicit
PaddlePaddle 3.3.x PIR/oneDNN compatibility constraints; changing MKLDNN
requires an independent clean-process inference experiment and exact PDIC
comparison. The statement that enabling it is a zero-risk, one-line speedup
is unsupported.

### Experiment matrix and acceptance

Start with identical copies of 12–30 representative pages and the same
Project/Profile, compare sequential GPU default, **CPU pool=1, 2, 4, 6**
and single-GPU-plus-two-CPU stages separately. Collect total elapsed,
page-by-page latency, resident RAM peak, GPU VRAM, CPU utilization and full
PDIC ordering/coordinates. No real dictionary images, measured speedup or
GPU/CPU-equivalence figures have been committed as part of this PR.
The two alternatives are **never activated by default**.

