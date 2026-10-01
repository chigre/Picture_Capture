# Picture Capture v2.1 — Headword pipeline

## Shared OCR channel and consumers

OCR recognition and OCR-assisted separator drawing are intentionally different layers.

- `ocr_channel.py` is the reusable OCR channel. It resolves the enabled PaddleOCR / Tesseract / Google Lens sources, runs multiple enabled engines on the same crop, preserves Lens `off / diagnostic / conflict / full` semantics, and exposes engine results without deciding where a dictionary separator belongs.
- `entry_classification_runtime.py` is the existing-marker text consumer used by 【仅OCR】. It first obtains the canonical crop from the already-established marker, then sends that same crop through the OCR channel. OCR may fill/replace text but is forbidden to change marker X/Y.
- `ocr_boundary_detection.py` is the OCR-assisted drawing consumer. It borrows OCR-channel evidence and passes it into the mature headword parser/arbitration stack to infer separator positions. Drawing policy therefore remains outside the OCR channel.
- `paddle_headwords_core.py` remains the mature low-level parser/evidence backend. The historical `detect_paddle_headwords` public name is compatibility only; new code should treat OCR-assisted boundary detection as a consumer, not as the OCR channel itself.

The historical settings names `paddle_use_paddleocr`, `paddle_compare_tesseract`, `paddle_enable_lens`, and `paddle_lens_mode` remain persisted/UI-compatible for existing projects. Runtime consumers must resolve them through `resolve_ocr_channel_plan()` rather than independently implementing engine-selection rules. The old single `ocr_engine` setting is only a fallback when every multi-engine channel switch is disabled.

This separation means 【仅OCR】 and 【OCR画线】 can use the same selected OCR sources while remaining functionally independent: enabling an OCR engine does not imply that OCR is allowed to create/move a separator, and using OCR to draw separators does not own OCR engine execution.

## Core stages

1. The OCR-assisted boundary consumer requests the shared channel plan. PaddleOCR and Tesseract can run on the same rectified column-left band; Google Lens can be off, diagnostic-only, conflict-triggered, or full participation.
2. OCR fragments are grouped, same-row fragments are actively absorbed, and a multi-line state machine may attach wrapped grammatical cues without moving the first-line Y.
3. A dictionary profile separates POS evidence from usage/domain metadata and internal article symbols; `parse_headword_text()` then produces lemma, variants, inflections, POS, usage, definition, parser trace and repair types.
4. Paddle/Tesseract candidates are aligned per column with `SequenceMatcher` sequence anchors, then unresolved blocks use lemma similarity + Y distance.
5. Arbitration ranks up to three engine candidates using parser score, OCR confidence, structural/visual evidence and repair penalty. Lens can break a local spelling conflict; two agreeing local engines are not silently overturned.
6. Alphabetical order is only a weak warning. It never automatically deletes a candidate.
7. Manual checkbox/review overrides are applied after automatic arbitration and persist in `*_manual_selection.json`.

## Output files

- `<page>.json`: complete machine-readable OCR/parser/fusion state.
- `<page>_ocr_diagnostics.txt`: strict 12-column TSV; raw + candidate records.
- `<page>_ocr_comparison.txt`: strict 27-column aligned Paddle/Tesseract TSV.
- `<page>_ocr_engines.tsv`: normalized 13-column long table for every engine.
- `<page>_fusion.tsv`: 12-column final arbitration table.
- `<page>_issues.tsv`: concise 16-column review queue with three-engine evidence.
- `<page>_manual_selection.json`: human selection/lemma overrides.
- `_quality_summary.tsv`: project-level page agreement summary.

## Manual checkbox semantics

The canvas shows a checkbox for each OCR row that is left-edge eligible in at least one engine. Checked means the row participates in final PDIC output. Automatic accept/reject initializes the state; the user's toggle has final priority.


## Project Storage v2 (v2.12.0)

The selected scan directory is treated as user-owned. Picture Capture writes its own persistent state only below `_PictureCapture/` for managed projects. `project.json` identifies the storage format; `settings.json`, profile/rules, PDIC/PPP sidecars, the historical QT tree and generated outputs are resolved through `project_storage.py`.

Legacy projects remain readable without mutation. The GUI offers an explicit migration that copies legacy software files into a staging directory, verifies every copied file by size, publishes `_PictureCapture`, and only then removes the old software-owned paths. Source scans and user reference files such as `wordslist.txt` remain at the project root.

Path resolution is centralized: `pdic_path()` is storage-aware, PPP uses dedicated read/write helpers, and QT/settings/profile/rule/output consumers no longer construct root-relative software paths directly.

## Page SECTION reading lanes

A page may optionally define one to ten explicit vertical reading regions in `data/PageSections/<page>.json` (legacy projects use `QT/PageSections/`). The page-list `Section` value is `0` when no sidecar is enabled and `1–10` for the explicit region count. The sidecar stores canonical full-resolution V bounds only; PDIC remains unchanged.

All ordering-sensitive paths resolve the page into SECTION-major reading lanes: `S1C1 → S1C2 → … → S2C1 → S2C2 → …`. Entry sorting, OCR text assignment, proofreading preload, page-aware word filling, PDIC repair/restore and whole-entry crop planning use this same lane order. When a page has explicit SECTIONs, their outer bounds are authoritative for entry and illustration cropping; the shared general crop top/bottom applies only to pages with `Section=0`. Thus `Section=1` replaces the former per-page special crop-bound override, while `Section≥2` additionally clips whole-entry pieces to each lane so inter-SECTION whitespace is never swallowed. Legacy `special_pages` crop settings remain a read-only fallback only when the page has no SECTION sidecar.


## v2.12.4 editable simplified review sidecar

The proofreading window keeps the historical PDIC format unchanged. Editable
OpenCC-derived simplified headwords are persisted separately under
`_PictureCapture/data/Simplified/<page>.json`, keyed by marker coordinates.
OpenCC is used only to initialize a row that has no persisted simplified record.
Once a row exists in the sidecar, that saved text is authoritative on reopen
regardless of whether it was auto-generated or manually edited; reopening a page
never silently regenerates or overwrites existing simplified review data.

