# Round 58 — remaining native main-window actions (2026-10-25)

Issue #562 / Draft PR #663. The main Tk shell already delegates almost all
large product implementation to UI workflows; its remaining composition and
dynamic monkeypatch binding factories are intentional, documented interfaces,
not candidates for mechanical source migration.

This round moves six **actual remaining behaviors** from
`PictureCaptureApp` into existing, appropriately layered owners:

- `ui/main_pdic_persistence.py`: guarded PDIC→PPP `save_all` sequence;
  project-only settings JSON save and historical status; sort and display
  collation setting fallback tuple;
- `ui/main_app_lifecycle.py`: guard-before-confirmation marker clearing
  preserving the exact existing `self.entries` list object and redrawing
  only on affirmative confirmation; existing ordered status/modal/traceback
  exception presentation.

`app.py` retains the identical original public Tk callback names and
signatures **directly in `PictureCaptureApp.__dict__`**, with original runtime
imports (dialog, traceback, path and lexicon sorter) passed explicitly **at
invocation time**. No reverse import, dynamic installer, class monkeypatch
or shadow module added. No Tk superclass/MRO changes. This remains a small
owner cleanup rather than inventing a large duplicate shell in a new module.

Regression tests invoke original class callables without opening a Tk window.
They validate blocked/declined/confirmed clear paths, unchanged list identity,
guarded PDIC→PPP order and failure propagation, project/no-project settings,
dynamic sort function binding and defaults, ordered error status/modal/
traceback, original class method/pickle identity and source ownership.

No PDIC/PPP/SECTION serialization changes, no OCR engine/cache/coordinates,
crop/export or Profile schema changes. Cross-platform CI and OCR smoke on
the final exact HEAD still required. Real scanned page manual GUI/Profile,
ordinary/OCR/combined, save/reopen and crop/export acceptance remains NOT DONE.
Maintain Draft PR #663 unmerged.
