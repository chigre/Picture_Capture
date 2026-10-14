# Ordinary drawing: bounded CPU parallelism

## Why this route was slow
The original main-window ordinary multi-page action called
`ProcessPoolExecutor(max_workers=1)` and waited for that one child before
starting the next page. A 24-core CPU was not being utilized for independent
pages. One page can still be limited by its own Layout and image-analysis work;
this change improves **multi-page throughput**, not necessarily the time
required to finish one isolated page.

## Worker policy
`ordinary_parallel.ordinary_draw_workers` chooses the number of **spawn
processes**, limited by available CPUs and selected pages:

- 1 page: exactly 1, retaining the existing serial pathway.
- Automatic: up to 6 concurrent pages on sufficiently large CPUs (24 cores
  and many selected pages -> 6 workers).
- Optional expert override: set process environment variable
  `PICTURE_CAPTURE_ORDINARY_WORKERS` to an integer 1–8 before starting the
  application (also capped by CPU count / page count). Invalid or unset values
  use automatic mode. No Project Profile / PDIC / settings field migration.

Windows PowerShell example before launching the **usual application command**:

```powershell
$env:PICTURE_CAPTURE_ORDINARY_WORKERS = "8"  # test eight concurrent pages
# Start Picture_Capture normally from this SAME PowerShell session.
# For a one-worker A/B comparison:
$env:PICTURE_CAPTURE_ORDINARY_WORKERS = "1"
# Restore automatic behavior for this session:
Remove-Item Env:PICTURE_CAPTURE_ORDINARY_WORKERS
```

Avoid confusing logical cores/threads with processing capacity. On very large
600-dpi RGB scans, each process can hold multiple image/NumPy arrays, so 8
workers may be *slower* than 4–6 if memory bandwidth, disk, or thermal
constraints dominate. No guaranteed speedup is claimed without end-to-end
measurement.

## Manual edit, cancellation, and output safety

The existing GUI parallel batch coordinator acquires
`_batch_state_lock` to atomically transition an intended page from
`pending` to `processing` **before process submission**. A foreground
manual edit transitions `pending` to `manual_locked` under the same lock,
so the batch **skips** it. Editing a `processing` page is blocked until the
worker commits, the page is marked `done`, and the UI reloads the current
page's freshly saved PDIC. Work is bounded to at most the available worker
slots; pause/stop prevents additional page submission and allows in-flight
per-page transactions to finish. This is not an all-pages atomic transaction.

The actual spawn worker is unchanged: `processing.detect_entries_job` calls
the same ordinary Layout Core detection, per-page LayoutRows capture, per-page
automatic baseline publication and `formats.write_pdic`. Batch confirmation
and saving of current visible edits **before the run** are unchanged.
OCR/combined paths remain sequential and use their existing preservation and
checkpoint flows. This PR does not change detection thresholds or PDIC format.

## Practical acceptance on genuine scans

For a controlled comparison, use a **separate copy** of the same selected
project/images (never run destructive benchmark overwrites on the only
manually corrected PDIC files), with all scan/Profile/SECTION settings identical.

1. Run once with override `1`, then with `4`, automatic `6`, optionally
   `8`. Start with multiple representative pages (e.g. 12–30), not one page.
2. Record total wall-clock run time, OS peak resident RAM and CPU utilization,
   disk throughput, and completion/skip counts. Allow process startup time.
3. Compare **per-page PDIC bytes** and the automatic-baseline entry coordinate
   lists; preserve old auto-baseline metadata separately, as it may include
   timestamps. A worker-count change must not change `(x, y, word)` entries.
4. During a separate safe test, manually edit one still-pending page while
   other pages run, then pause/resume/stop. It must be skipped, not overwritten,
   and all completed pages must still have valid PDIC.
5. Compare one/two-column scans and large/high-DPI pages. Do not claim
   linear scaling or success from synthetic CI alone.

The opt-in performance change is independent of PC-CQ/B2 #483. No OCR-based
training, layout-role tuning or manual PDIC remapping is authorized here.
