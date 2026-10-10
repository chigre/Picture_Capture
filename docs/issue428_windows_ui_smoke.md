# Issue #428 Windows GUI acceptance protocol

This is a **manual, real Windows GUI** gate. A passing pytest suite does not
substitute for seeing the buttons and checking the dispatched page sequence.
Do not mark #428 complete or merge #454/#455 merely because CI is green.

## Preconditions

- Open a disposable copy of a dictionary project containing **at least 8 pages**.
- Back up the source PDIC and PPP files.
- Open Settings Center → Crop; first set **parallel workers = 1**, then repeat
  with **parallel workers = 4**. Set page-merge off for the first pass.
- Select at least 8 pages, including rows with/without PDIC markers.

## Single-line and unlined-row export (four runs total)

Repeat **both** actions 【单行切图】 and 【未画线行导出】 at worker counts 1 and 4.

1. Start the batch. Verify the progress bar is visible and both **暂停** and
   **停止** controls are enabled while the task runs.
2. Click **暂停** after progress begins. Wait for any already-running pages
   to complete; confirm no *new* page is dispatched while paused.
3. Click **继续**; confirm new pages start again.
4. Start a fresh run and click **停止** before all pages complete. For
   worker=1, the current page may finish; for worker=4, up to four in-flight
   pages may finish. No new pages should be submitted after stopping.
5. Capture a screenshot with enabled buttons and a screenshot of the stopped
   progress/status; record completed/total page counts.
6. Confirm the UI becomes responsive and buttons return to their idle states.

Very fast pages may finish before a click is possible; in that case use a
larger collection of high-resolution scans. Never interpret an already-finished
run as passing the pause/stop test.

## Auxiliary-line and major-headword tests

1. Turn on 【辅助线模式】. Add a line between two PDIC markers and verify it
   appears dashed amber, without an entry number or text editor.
2. Move it by dragging, delete by right-clicking, and test undo by Ctrl+Z or
   【撤销辅助线】. Switch pages and back; verify the edited auxiliary lines
   persist independently from PDIC.
3. Compare the same page with 【切图预览】 to the actual 【词条切图】 output.
   Check fragment top/bottom coordinates and that no auxiliary-only word/crop
   or extra PDIC index appears. Repeat on a rotated-layout page if available.
4. Mark a normal PDIC row as **大字头**, verify that 【大字头单行】 exports only
   that row's left prefix according to 【向右比例】. Repeat with 【按页合并】 on
   and off. For a page with no major-headword marker, no major strip should
   remain in its output folder.
5. Confirm that a forced or accidental restart with no markers does not leave
   stale images from a prior export.

## Evidence to attach to Issue #428

- Windows version; Python/application version; project page count and image size
- Four batch runs: action / worker count / pause-resume / stop result / total pages
- Screenshots of visible controls plus stopped status
- Auxiliary preview vs exported crop images (same page) and PDIC index count
- Major-headword merged/unmerged output files and no-marker test
- Any failure, with page name and reproduction steps
