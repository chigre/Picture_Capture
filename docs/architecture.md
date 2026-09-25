# Picture Capture v2.1 — Headword pipeline

## Core stages

1. PaddleOCR and Tesseract run on the same rectified column-left band. Google Lens can be off, diagnostic-only, conflict-triggered, or full-page.
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

A page may optionally define multiple vertical reading regions in `data/PageSections/<page>.json` (legacy projects use `QT/PageSections/`). The sidecar stores canonical full-resolution V bounds only; PDIC remains unchanged.

All ordering-sensitive paths resolve the page into SECTION-major reading lanes: `S1C1 → S1C2 → … → S2C1 → S2C2 → …`. Entry sorting, OCR text assignment, proofreading preload, page-aware word filling, PDIC repair/restore and whole-entry crop planning use this same lane order. Whole-entry crop pieces are clipped to each lane, so whitespace between SECTIONs is never swallowed by a cross-section crop.


## v2.12.4 editable simplified review sidecar

The proofreading window keeps the historical PDIC format unchanged. Editable
OpenCC-derived simplified headwords are persisted separately under
`_PictureCapture/data/Simplified/<page>.json`, keyed by marker coordinates.
OpenCC is used only to initialize a row that has no persisted simplified record.
Once a row exists in the sidecar, that saved text is authoritative on reopen
regardless of whether it was auto-generated or manually edited; reopening a page
never silently regenerates or overwrites existing simplified review data.

