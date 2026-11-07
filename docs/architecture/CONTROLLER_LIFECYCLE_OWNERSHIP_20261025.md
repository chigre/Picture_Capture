# Round 50 — UI lazy controller lifecycle ownership (2026-10-25)

The shared `ui/controller_lifecycle.py` now physically owns app-instance
controller caching for **eight** owner types: Canvas, Review, Detection, Export,
Crop, Illustration, Headword, Project.

Existing methods and signatures are unchanged. Historical `PictureCaptureApp`
and `ui/project_session_workflow` callers pass their current constructor at
invocation time. Headword's parser/fill callbacks are also passed live. The
only cache is the original `app.__dict__`: an absent or `None` instance is
constructed once; a non-None instance is returned untouched. Failed constructor
calls never publish partially initialized controllers.

No new app imports or Tk import is allowed in this UI owner; no global
controller registry, runtime monkeypatch installer or shim exists. Original
eager startup controller initialization remains unaffected.

The eight existing source-location tests are reanchored to the real shared
owner, retaining their UI dispatch/startup assertions. New Round 50 regression
covers constructor monkeypatches, original signatures, lifetime, live callback
injection and failure atomicity.

No PDIC/PPP/SECTION, OCR runtime/model/cache, settings or export changes.
Full exact-head CI, architecture guards and three-platform OCR smoke required.
Manual representative dictionary-page end-to-end parity remains NOT DONE.
Keep original PR #663 Draft, open and unmerged.
