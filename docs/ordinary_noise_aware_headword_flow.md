# Ordinary drawing: noise-aware headword / boundary flow

This note applies specifically to **普通画线 (ordinary drawing)**.

The first correction is architectural: denoising is not a headword-only patch and is not owned by layout detection. The page is converted once into a shared, full-resolution **analysis image**. Layout, Page Understanding, legacy VB/ordinary detection and ordinary visual recovery all consume that same cleaned page. The original scan remains unchanged for display and crop/export.

## 1. Shared image contract

```text
original scan
    |
    | normalize EXIF / alpha only
    v
normalized source image ---------------------> display / crop / export
    |
    | shared isolated-speck cleanup
    | (NO resize, crop, deskew or coordinate shift)
    v
shared analysis image
    |
    +--> layout reliability
    +--> Page Understanding
    +--> ordinary/VB left-edge detector
    +--> ordinary visual recovery
    +--> ordinary postprocess
    +--> combined evidence arbitration
```

The important invariant is:

```python
analysis_image.size == source_image.size
analysis_x == source_x
analysis_y == source_y
```

Therefore a separator discovered on the analysis image can be written directly as the source-image marker coordinate.

## 2. Why this must happen before headword judgment

Dirty scans can create false evidence at several stages simultaneously:

- a speck near the physical left edge can become a false first-ink point;
- specks can distort the estimated body lane / indentation topology;
- a tiny black component can make a continuation row look visually stronger;
- a false local ink onset can move the separator above a non-headword row;
- if layout is cleaned but ordinary drawing is not, the two modules reason about different physical pages.

Therefore the correct sequence is **clean once, then reason**.

## 3. Ordinary drawing decision flow

```text
shared analysis image
        |
        v
page/body/column geometry
        |
        v
physical text rows + first-ink starts
        |
        +-----------------------------+
        |                             |
        v                             v
legacy VB separator evidence     Page Understanding evidence
        |                             |
        +-------------+---------------+
                      |
                      v
            candidate entry boundary
                      |
          +-----------+-----------+
          |                       |
          v                       v
 positive entry evidence      negative / continuation evidence
 - repeated entry lane        - body-lane row
 - stable left edge           - wrapped definition topology
 - strong whitespace gap      - weak/isolated ink only
 - oversized display head     - no new-entry boundary
 - marker-like repeated form  - continuation context
          |                       |
          +-----------+-----------+
                      |
                      v
            ordinary reliability gate
                      |
            +---------+---------+
            |                   |
          accept              suppress
            |
            v
       refine separator Y
            |
            v
        final marker
```

## 4. Shared denoising pseudocode

The common cleanup must be conservative. It is not morphological opening over the whole page and it must not erase punctuation or thin rules.

```python
def build_analysis_image(source):
    gray = grayscale(source)
    ink = conservative_local_contrast_mask(gray)

    local5 = foreground_count(ink, radius=(2, 2))
    local11 = foreground_count(ink, radius=(5, 5))
    vertical13 = foreground_count(ink, radius=(6, 0))
    horizontal13 = foreground_count(ink, radius=(0, 6))

    isolated_speck = (
        ink
        and local5 <= 3
        and local11 <= 4
        and vertical13 <= 2
        and horizontal13 <= 2
    )

    analysis = source.copy()
    analysis[isolated_speck] = white
    return analysis
```

This deliberately protects:

- thin vertical/horizontal dictionary rules;
- glyph stems;
- punctuation/diacritics with nearby character support;
- disconnected but nearby glyph components.

## 5. Ordinary candidate reliability pseudocode

The next stage should be implemented after the shared-image change has been benchmarked. It belongs in the ordinary path, not in Paddle headword parsing.

```python
def ordinary_candidate_reliability(candidate, page):
    positive = 0.0
    negative = 0.0
    reasons = []

    # positive physical evidence
    if candidate.at_stable_entry_lane:
        positive += 2.0
    if candidate.has_clean_separator_above:
        positive += 1.5
    if candidate.repeated_marker_shape:
        positive += 2.0
    if candidate.oversized_display_head:
        positive += 2.5
    if candidate.page_understanding_entry_role:
        positive += 2.0

    # negative physical evidence
    if candidate.matches_body_lane:
        negative += 2.0
        reasons.append("body_lane")
    if candidate.looks_like_wrapped_definition:
        negative += 2.0
        reasons.append("wrapped_definition")
    if candidate.visual_strength_depends_on_tiny_components:
        negative += 1.5
        reasons.append("noise_dependent_visual_evidence")
    if candidate.no_independent_new_entry_boundary:
        negative += 1.0
        reasons.append("no_new_entry_boundary")

    # strong entry structures are allowed to survive one weak negative cue.
    accepted = positive >= ordinary_threshold and positive - negative >= margin
    return accepted, reasons
```

## 6. Important separation of responsibilities

For ordinary drawing, OCR text such as Spanish examples (`Al niño ... ~`, `es una ~ ...`) may later be useful as an *optional semantic veto* in combined mode, but it must not become the primary ordinary detector. 普通画线 should first be robust using image/layout evidence alone.

So the implementation order is:

1. **shared denoised analysis image** (implemented first);
2. benchmark ordinary false positives on dirty pages;
3. add ordinary visual/continuation negative evidence where image structure is sufficient;
4. only then consider OCR semantic veto as an independent fusion signal, not as a dependency of ordinary mode.

## 7. Diagnostic fields recommended for the next ordinary-reliability commit

Each automatic ordinary candidate should eventually expose:

```text
analysis_image_shared = true
entry_lane_delta
body_lane_delta
separator_whitespace_score
preceding_gap
row_height_ratio
leading_component_count
isolated_component_fraction
page_role
positive_evidence_score
negative_evidence_score
negative_reasons[]
ordinary_reliability_score
```

This makes dirty-scan regressions explainable instead of turning the ordinary path into another opaque threshold stack.
