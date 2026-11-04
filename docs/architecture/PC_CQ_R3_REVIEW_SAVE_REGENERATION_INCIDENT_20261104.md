# PC-CQ R3 — Reported review save, regeneration and navigation incident (2026-11-04)

## User-visible symptom and confirmed source logic

A real operator reported ReviewWindow showing “自动保存失败或未完成；文字仍保留在编辑框中”, refusal to save/advance, and a Tkinter callback traceback originating at `proofreading/simplified_review.py:validate_source_word_binding` during “重新简体化”. The operator clarified that the checkout contains Draft PR #663 branch code. The report is direct evidence of a usability failure, **not** permission to read/upload their private PDIC/PPP/SECTION/Profile/OCR or dictionary.

The R3 review and simplified workflows previously tried to persist a newly regenerated sidecar source word before the pending original word had reached PDIC, while an older manual sidecar could mismatch a later independently saved PDIC word. The save should preserve the old human record exactly, not reassign it to a new word at the same XY. A second defect propagated a guarded file-write `RuntimeError` as an uncaught native Tk callback, and a third denied a no-change page navigation even after the PDIC word had been saved.

## Fail-first synthetic evidence

| Work package | RED SHA | Real GitHub Actions evidence |
|---|---|---|
| Regenerate order, refused paired save, pending autosave warning | `d6c84984775c70ea24d601b51d47563eba19c924` | [CI #41783628164](https://github.com/chigre/PictureCapture/actions/runs/41783628164): Ubuntu 3.10 3 intended failures, 5666 passed, 3 skipped |
| Stale manual sidecar blocking independent original-word commit | `0e25c84c524931aaf711d43c0e39bf15886fff10` | [CI #41784802797](https://github.com/chigre/PictureCapture/actions/runs/41784802797): Ubuntu 3.13 1 intended failure, 5670 passed, 3 skipped |
| Uncaught regeneration callback exception, private diagnostic | `689c299ef10feb9161047de881d4c975d66d153f` | [CI #41786209004](https://github.com/chigre/PictureCapture/actions/runs/41786209004): Ubuntu 3.13 3 intended failures, 5672 passed, 3 skipped |
| Detached old sidecar traps a valid no-change page save | `cd6984d9322f828898ace675dd45aa696a0b7e36` | [CI #41786700665](https://github.com/chigre/PictureCapture/actions/runs/41786700665): Ubuntu 3.13 1 intended failure, 5676 passed, 3 skipped |

RED is expected FAILURE, not acceptance; unrelated successful tests do not cancel that intentional failure.

## Source corrections and owner boundaries

- `ui/review_simplified_workflow.py`: before simplified-only regeneration, first save any edited original word using existing paired PDIC+human sidecar commit, then recheck row/page ownership. If save refused, no regenerated write or success status.
- `ui/review_page_lifecycle.py` and `ui/main_pdic_persistence.py`: a pending background-page permission refusal remains an unconfirmed text save even if unrelated PPP is saved. A normal ReviewWindow save owns its frozen transaction snapshot and never silently downgrades to an unrelated main writer.
- `proofreading/main_editor_sync.py` and `proofreading/review_bundle.py`: the detached legacy human sidecar is never attached by coordinate alone to a new original word. Only verified ordinary ReviewWindow source-pinned transactions may save a new PDIC word without modifying the detached human JSON. A no-change navigation is allowed only when its serialized PDIC bytes are exactly the same; any new unconfirmed simplified Tk input blocks. Existing recovery marker and source readbacks remain in force.
- `app.py`: the public Tk regenerate callback converts known exceptions to generic privacy-safe warnings; it never prints the private path or original word in status/messagebox. The guarded workflow still restores its tentative sidecar preview.

No persisted schema, original-image XY, existing human sidecar bytes, or guard threshold changed. No real OCR or human data was used in the regressions.

## Source-head acceptance, not docs-head acceptance

Source/test HEAD `3273f3c67f8593a72f463766f9537d559e547c43`: [CI #41787070868](https://github.com/chigre/PictureCapture/actions/runs/41787070868) **six jobs SUCCESS**, Risk tier/gate **SUCCESS**; [OCR #41787070886](https://github.com/chigre/PictureCapture/actions/runs/41787070886) **3/3 SUCCESS**; [CodeQL #41787066779](https://github.com/chigre/PictureCapture/actions/runs/41787066779) **Actions+Python 2/2 SUCCESS**. Ubuntu 3.13 5677 passed/3 skipped; macOS 3.13 5678 passed/2 skipped. Documentation architecture check **SKIPPED**, not PASS. A new docs commit gets a new SHA and requires its own exact-head evidence; do not automatically inherit source acceptance.

## Open safety/useability verification

Real operator Windows E3, real dictionary sidecar/PDIC/PPP/SECTION save-reopen, #483 W1–W11, #503 complex manual Undo/Redo, R6 learned labels, R8 live scans: **NOT PERFORMED / DEFERRED**. If a user still cannot regenerate a detached old manual sidecar, treat it as a separate consent-and-preservation design problem: never silently overwrite human bytes or bypass the guard to make the warning disappear.

Continue with live #663 HEAD, non-force expected-sha updates only, PR Draft/Open/Unmerged, main unchanged. Next authorized package should be R3 usable ordinary ReviewWindow save/page transitions followed by R4.2 callback/epoch cases proved with synthetic RED-first.
