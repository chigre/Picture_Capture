# Layout illustration PPP reuse and multiresolution experiment

## Layout illustration switches

The Illustration settings panel has a parent **Layout 分析前白化插图** checkbox
and a subordinate **使用已有的插图数据** checkbox. When the parent is OFF,
the child is disabled and neither detection nor Layout whitening runs.

When parent ON / reuse ON, read each page's existing PPP polygons in original
source image XY, fill them white only in a temporary Layout analysis copy, and
DO NOT run illustration detection or modify PPP. A missing PPP is a real error
(not equivalent to a valid empty PPP, and not a reason to rerun detection).
The checkbox is only suitable for projects where ALL pages have been processed,
including an intentionally empty PPP for pages with no illustration.

When parent ON / reuse OFF, run the existing illustration detector only ONCE
per page. Save the detected candidate polygons through the existing
`detect_illustrations_to_ppp` merge policy, retaining manual polygons and
replacing AUTO polygons. In Layout, continue applying the existing safety
rules: small/head-like auto candidates are not whitened. No original scan
pixels or PDIC coordinates are changed by the mask.

Manual PPP edits to the foreground page are flushed before the ordinary
batch worker runs in this auto-detection mode.

## Independent multiresolution geometry benchmark

The separate script `scripts/benchmark_layout_scales.py` measures automatic
layout detection at 100%, 75%, and 50%, maps estimated dimensions back to
source coordinates, and writes machine-readable JSON. It does NOT change
production drawing, PPP or PDIC.

Example (adjust paths to your project):

```powershell
python scripts/benchmark_layout_scales.py --settings "D:\\project\\settings.json" --images "D:\\project\\001.png" "D:\\project\\002.png" --output "D:\\benchmark\\layout_scales.json"
```

Compare columns, start Y, first column X, column width, gutter, and character
height against the unscaled baseline, not just elapsed seconds. An altered
geometry estimate is not by itself a PDIC error, but cannot be shipped as a
drawing optimization before running the same-page full PDIC parity comparison
with the actual drawing pipeline. Scaled settings are an approximate benchmark
and not a substitute for real per-page project Profile coordinates.

## Test and release gates

- Complete CI on Python 3.10 and Windows/macOS/Linux.
- Windows sample of 20 known pages, both PPP modes, verifying that manual PPP
  regions are preserved and reuse mode never calls a detector.
- Missing PPP reuse produces a clear error and does not silently run detection.
- Full PDIC equivalence and comparable screenshots for any eventual live
  multiresolution implementation.
- Do not enable multiresolution production drawing by default based on
  geometry-only benchmarking.


## Opt-in real drawing multiresolution (new)

The ordinary Layout detection facade now accepts an **experiment-only**
environment variable:

```bat
set "PICTURE_CAPTURE_LAYOUT_SCALE_EXPERIMENT=auto"
```

The default is `off`. Automatic choice is based on the **original page's
longest edge**:

| Original longest edge | Temporary Layout detector scale |
|---|---|
| < 3000 px | 100% |
| 3000–3999 px | 75% |
| >= 4000 px | 50% |

Explicit `75` and `50` options may be used to test, but still avoid
downsampling small images (<3000 px); a requested 50% is limited to 75%
when the longest side is 3000–3999 px.

Only the reliability detector input is scaled, and detected geometry is mapped
back to the original pixel coordinates; downstream physical rows, page
understanding, entry recovery and PDIC continue at original resolution.
Nonidentity Layout transformations retain the unscaled original path.
The profiling JSONL stage-group `layout_scale_100pct`,
`layout_scale_75pct` or `layout_scale_50pct` shows the selected scale.
The zero-valued `selected` marker is a category, **not a time**.

To compare the production pipeline, preserve full PDIC snapshots for the same
20 pages with the experiment flag `off` and `auto`. Strictly compare every
PDIC, including line count, order and coordinates. A layout estimate close
to baseline does not imply PDIC equality. Leave this setting OFF on projects
not yet validated.


## Layout settings revision — denoise and selected scaled parameters

Both independently persisted booleans are now in Layout settings and the
compact Layout parameters menu, directly above "使用自动版面参数":

- `analysis_denoise_enabled=True`: shared full-resolution adaptive denoise.
  The intensity `analysis_denoise_strength=auto` (off/weak/auto/strong)
  lives in the Layout-related advanced settings rather than Display controls.
- `layout_denoise_enabled=True`: additional detector-only speck cleanup,
  separately switchable.

The size-aware downsample flag is `layout_scale_enabled=False` by default
and has seven independently persisted allow-list switches. Default ON:
`layout_scale_columns`, `layout_scale_column_width`,
`layout_scale_gutter`. Default OFF:
`layout_scale_start_y`, `layout_scale_manual_x`,
`layout_scale_character_height`, `layout_scale_row_padding`.
Unchecked scalar parameters use existing full-resolution project parameter
priors, NOT a downsampled estimate; fine physical row/entry analysis remains
full resolution. In the 50% experiment, downsampled column lane boundaries
are omitted unless the user explicitly enables first-column X scaling.

The older `PICTURE_CAPTURE_LAYOUT_SCALE_EXPERIMENT` environment variable
still overrides the GUI scale master when explicitly set. To use the GUI switch,
remove that line from `windows_run.bat` (rather than forcing `off`).
