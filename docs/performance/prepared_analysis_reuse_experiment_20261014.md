# Shared analysis image reuse — controlled A/B experiment

This change introduces an **opt-in** environment flag only:

`PICTURE_CAPTURE_REUSE_PREPARED_ANALYSIS=1`

Default is OFF. It only skips a duplicate full-resolution analysis-image build if the caller's
RGB image carries the marker written by `build_analysis_image` and its denoise strength
matches the current settings. It returns a detached copy to preserve ownership.
No image is downsampled; PDIC coordinates stay at original resolution.

## Windows A/B validation

Keep `PICTURE_CAPTURE_DRAW_PROFILE=1` in `windows_run.bat`, run the same
20 pages in the same order, identical project settings and device.

1. Baseline: `set "PICTURE_CAPTURE_REUSE_PREPARED_ANALYSIS=0"`
2. Candidate: `set "PICTURE_CAPTURE_REUSE_PREPARED_ANALYSIS=1"`

Save **separate, immutable directories** with all baseline/candidate `*.pdic`
files immediately after the respective runs. Compare the whole directory tree:

```powershell
python scripts/compare_pdic_snapshots.py "D:\benchmark\baseline" "D:\benchmark\candidate" --json "D:\benchmark\pdic_compare.json"
```

The CLI must exit 0 with **no row/content/coordinate/order differences** before
recommending enabling this setting by default. Compare performance reports'
`facade_analysis_image`, `inner_image_prepare`, and batch total.

## Caution

Applying the adaptive denoiser twice is not guaranteed to be equivalent to applying
it once. This opt-in experiment deliberately changes that repeated processing
for images already marked as prepared, so parity with the original processing path
is an explicit gate. If any PDIC difference occurs, keep the flag OFF and investigate
the page-level differences. Multiresolution changes are a separate, later experiment.
