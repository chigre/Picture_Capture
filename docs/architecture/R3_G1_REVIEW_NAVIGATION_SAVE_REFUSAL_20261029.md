# PC-CQ v1.3.0 G1 — refused ReviewWindow save must cancel page navigation (2026-10-29)

## Failure boundary
The existing `review_page_sync.save_review_before_page_change` ignored the
return of `review.save(redraw_main=False)` and reported True to the caller.
`project_session_workflow.load_page` therefore changed the committed page
after an explicit save refusal (including active batch processing). The direct
`ReviewWindow.change_page` callback also progressed after a False return.
The synchronous PageController always reported True if load_page returned
explicit False. These combined paths can throw away unsaved human Tk text.

## Fail-first and corrective scope
- Tests-only `a2dec00b2fcc36690254fc4cebc14e92218e9364`
  (`tests/test_g1_review_navigation_save_refusal_20261029.py`) exercises
  the helper, main window, review pager and synchronous controller.
- `save_review_before_page_change` now returns a distinct None only when
  the actual review save explicitly returns False; True still means saved;
  False still means not applicable. Existing legacy None-returning test
  fixtures remain supported, but are not mistaken for a refusal.
- The page commit aborts before changing page and before saving/syncing stale
  canvas text; clears pending page index, restores the page list selection,
  and provides an operator message. Direct ReviewWindow page navigation also
  refuses to consume prefetch or request a new page if save returned False.
- The synchronous PageController reports explicit False from load_page;
  a historical None return remains a successful legacy adapter result.
- No new persistent format, OCR choice, coordinate lookup, user Undo/Redo,
  cross-file transaction, profile schema or renderer reset.

## Limitations
This fixes **explicit False** save refusal. Exceptions already stop the old
page commit but need a separate UI-notification audit if evidence justifies it.
Batch `skip_current_save` routes and focused-filter cross-page behavior are
separate owners not broadened here. This E2 synthetic fix does not prove
Windows real-dictionary E3 or 20-step Undo/Redo, PDIC/PPP/SECTION save-reopen,
source-pixel crop parity, or #483 W1–W11.
Keep #663 Draft/Open/Unmerged and #503/#562/#483 Open.
