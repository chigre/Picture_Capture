# Ordinary drawing GPU memory safety — 2026-10-14 HOTFIX

## Current status: GPU-backed ordinary batch is serialized

**Safety rollback after field report:** Six ordinary pages were launched at
once on a 24-core workstation, with GPU and system memory saturated and no
pages completing. The initial parallel CPU-only assumption was incorrect.

Ordinary drawing **does not recognize text with OCR**, but its shared
Layout geometry calls `layout_detection.detect_layout_parameters`, which
normally invokes `layout_reliability._paddle_estimate` and
`layout_detection_legacy._get_text_detector`. The latter constructs a
PaddleOCR `TextDetection` instance using
`runtime_environment.resolve_paddle_device()`, whose default `auto` may
select **GPU**. In the Windows `spawn` pool every process has a separate
model/device allocation and private full-page NumPy/PIL buffers. Six concurrent
GPU-backed jobs cannot be scheduled safely merely because the CPU has 24 cores.

**The safety hotfix always selects 1 worker** (the historical persistent
single subprocess), even if a prior command set
`PICTURE_CAPTURE_ORDINARY_WORKERS=6` or `8`. No user-scoped setting is
migrated. The experimental multi-worker coordinator remains in the repository
but is not reachable through this safety policy, pending redesign and
performance measurements.

There is **no measured speedup** from the earlier #491 claim; its default
six-process setting is withdrawn. This safety change should restore
pre-#491 resource behavior, not improve speed.

## Emergency action on the currently running old build

1. Click the application's **停止** button. The old batch coordinator is
   designed to stop *dispatching* new pages and wait for already started pages
   to finish; this can remain blocked if the GPU/memory is exhausted.
2. If GPU/RAM usage does not fall and the app cannot exit gracefully, save any
   other work if possible, close Picture_Capture and end **only its spawned
   Python/Picture_Capture child processes** using Windows Task Manager. Do not
   delete source images, PDIC, or project sidecars as a "cleanup" operation.
3. Undo the previous persistent 8-worker override, in a new PowerShell:
   `setx PICTURE_CAPTURE_ORDINARY_WORKERS 1`. For an immediately launched
   program from that PowerShell, also run
   `$env:PICTURE_CAPTURE_ORDINARY_WORKERS = "1"`.
   Fully restart the application; `setx` does not change running processes.
4. Use a **copy** of a few test pages first after installing the fixed version.
   Check saved PDIC counts before restarting a large batch.

## Architecture requirements for a future measured speedup

- Treat Paddle GPU layout inference as **one shared GPU producer**, not one
  separate GPU model per worker.
- Allow independent page-level CPU postprocessing with explicit per-page memory
  / RAM budget and bounded queue, *after* GPU stages. A CUDA-capable model must
  never be accidentally initialized in each CPU worker.
- Or use a **CPU-only** ordinary layout geometry path, but that is an explicit
  algorithm change requiring geometry/PDIC parity validation, not an implicit
  workaround here.
- Profile actual large scan peak RSS, VRAM, disk throughput, model
  initialization and per-Layout-stage wall clock before selecting 2/4/6 workers.
- Preserve existing foreground `manual_locked` ownership,
  per-page baseline/PDIC, pause/stop semantics and source files. Add a
  resource-pressure abort when memory is exhausted, rather than queueing all
  first-group jobs into stalled models.

Do not merge experimental parallelism into `main` again solely on green
synthetic CI. This runbook is independent of PC-CQ/B2 #483.
