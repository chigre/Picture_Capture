# Coordinate system contract

Picture Capture uses several coordinate spaces internally. They are deliberately
separated so projects, PDIC/PPP files, reports and training data remain portable
when the GUI zoom, OCR resize, writing direction or page transform changes.

## Public and persisted spaces

### Source-image pixels

**Use for:** PDIC points, PPP polygons, user-facing page coordinates, physical
page-template boundaries, exported annotations and source-space diagnostic
positions.

- origin: source image top-left
- X increases to the right
- Y increases downward
- unit: one pixel in the original scanned image

Source-image coordinates must never depend on viewer zoom or
`parameter_display_width`.

### Canonical reference-page pixels

**Use for:** persisted project layout geometry such as first-column U,
column width, gutter, body start/end V, line height and row spacing.

The persisted value is measured in pixels of one explicit canonical reference
page. `geometry_reference_width` records that page's canonical width. At
runtime, layout geometry is scaled to the current page's canonical width.

This keeps values human-readable as real full-resolution pixels while also
preserving layout on projects whose page images have different resolutions.

A bare `AppSettings` object has no implicit reference width. When a real new
project is opened, the first page establishes the initial canonical reference
width; the shipped numeric defaults are converted so their historical 1400px
physical meaning is preserved. Representative-page layout analysis may later
replace that reference with the detected aggregate reference width.

### Percentages

**Use for:** physical Profile rules that should follow page size, including
header, footer and page-edge exclusions.

For example, a 3% header on a 1642-pixel-high source image resolves to
`round(1642 * 0.03) = 49` source pixels.

## Internal-only spaces

### Canonical full-resolution pixels

Layout analysis normalizes reading direction into canonical U/V coordinates:

- U is the across-column axis.
- V is the reading progression axis.
- identity and mirror transforms keep the full source resolution.
- 90-degree transforms swap canonical width/height.

Canonical coordinates are runtime geometry. When a value is exposed externally,
its coordinate space must be named explicitly or converted back to source
coordinates.

### Analysis pixels

Temporary downscaled images used for projections/layout analysis. These
coordinates must be converted back to canonical full-resolution pixels before
leaving the analysis function.

### OCR-band local pixels

Temporary coordinates inside a cropped/straightened OCR band. They must be
mapped to canonical and then source coordinates before becoming PDIC markers or
exported source positions.

### 1400px reference units

OCR/profile tuning distances such as candidate-band margins and left-edge
tolerances use a fixed 1400-canonical-width reference. These are algorithmic
tuning units, not page coordinates.

## Legacy display pixels

Older Picture Capture projects stored layout geometry relative to
`parameter_display_width`, which depended on GUI display scaling.

On first open, once a real page size is known, the project is migrated once to
canonical reference-page pixels. `parameter_display_width` remains only as a
compatibility input for unmigrated projects and must not be used by new
features.

Migration must preserve the page geometry produced before migration, including
when later pages have a different resolution.

## Naming rules

Use coordinate-specific names at subsystem boundaries:

- source: `source_x`, `source_y`, `*_xy`
- canonical: `canonical_u`, `canonical_v`, `*_vu`
- analysis: `analysis_x`, `analysis_y`
- OCR band: `band_x`, `band_y`
- reference-page persisted geometry: document the
  `geometry_reference_width`

Avoid ambiguous exported names such as a bare `header_y` when the coordinate
space is not explicit.

## Export contract

Training annotations include a machine-readable `coordinate_contract`.

- ground-truth PDIC points and PPP polygons: source-image pixels
- physical Profile boundaries: source-image pixels
- derived runtime layout: canonical full-resolution pixels with explicit
  transform and canonical size
- persisted settings: canonical reference-page pixels with an explicit
  `geometry_reference_width`

A single JSON object must never silently mix two coordinate spaces under
unqualified field names.
