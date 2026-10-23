# Issue #562 — OCR selected-review finalization owner (2026-10-23)

## Migration boundary

After merged #639, the next large independent architecture batch extracts **the
whole post-arbitration review-finalization chain** from
`paddle_headwords_core.py` into `ocr/review_finalization.py`. The current
candidate arbitration and image OCR operations stay in the original core until
separate, independently testable full-chain extractions.

All 13 coupled functions move together:

- Review box height, quality priority and normalized CJK lemma checks
- Single-glyph and same-compound geometry/identity checks and line tolerance
- Whole-review-list near-Y deduplication (with correct upper/lower boundary)
- Selected review row conversion to persistent `Entry` objects
- Project-wide quality-summary TSV update under the original process lock

`paddle_headwords_core.py` retains the same named public/private functions and
signatures. They delegate to the canonical owner, injecting the **18 original
live operations, threshold values, Entry constructor and shared lock** each call.
Monkeypatches to the existing OCR facade/core remain observable, while the
implementation owner does not import the core, GUI or native OCR engine.

## Critical invariants

Oversized single-CJK duplicate lines use the wider 0.55 normal-line threshold
and retain the upper source separator; ordinary/bracketed near-Y duplicates
use 0.22 and retain the lower source separator. Never combine individual source
X/Y values drawn from different coordinate rows. The preferred OCR engine,
selected/needs-review flags, merged/suppressed issue codes, candidate IDs and
manual overrides stay stable.

The final `Entry` constructor is the original type from
`picture_capture.models`, retaining saved-file and pickle identities. Quality
TSV field order/format, page-sorted replacement, atomic-write hook, and process
lock remain unchanged. No new root file, installer, GPU initialization,
namespace copy, GUI dependency or disk-format revision is introduced.

The core shrinks **363854 → 351535 normalized UTF-8 bytes** (−12319);
the historical oversized baseline remains unchanged, with an additional
strict **351540-byte** ceiling. Physical root count remains **15**.

New direct tests cover import isolation; call-time monkeypatch hooks;
single-CJK, ordinary and compound duplicate semantics; selected Entry
materialization and oversized flags; quality-summary atomic write/replacement
and live output publisher. Original full Windows/macOS/Ubuntu × Python3.10/3.13,
GUI smoke, compatibility runner, wheel, architecture change guard, CodeQL,
review threads and independent postmerge main acceptance are mandatory gates.
Synthetic tests cannot establish real-page/GUI/native CUDA acceptance.

PR #640 is an independent crop-package refactor and must be accepted separately
before both changes are considered integrated on main.
