# PC-CQ v1.3.0 G1 — filtered editor clipboard / IME source capture (2026-10-29)

## Original loss path
In `focused_filter_workflow._render_filter_batch` each filter row was
bound only to `<KeyRelease>` for manual input, apart from the OCR-fill
button's explicit commit. Clipboard paste, cut, some IME commits, and
programmatic updates to the backing Tk `StringVar` can change the
visible editor without generating `KeyRelease`. The previous save
barriers only inspected `_filter_pending_changes`; they could therefore
accept page/mode/batch navigation after a visually edited but untracked
filter row. Source page/X/Y ownership was at risk.

## Fail-first regression and bounded fix
Test-only commit `7d249868e724a736f78edc1ab9d603a560caec39`,
`tests/test_g1_filter_tk_var_clipboard_ime_20261029.py`, tests
real `_render_filter_batch` with headless Tk-like controls:

- Textvariable changes without KeyRelease queue the original page/X/Y.
- FocusOut is bound, and repeated commit of the same value is idempotent.
- Programmatic input followed by reversion clears the queued snapshot.
- Stale variables from a replaced batch cannot edit another page/XY owner.
- Initial rendering does not enqueue untouched source values.

Fix attaches per-row `StringVar.trace_add("write", ...)`, with exact
rendered variable and target **object identity** checks before committing;
`FocusOut` uses the same guarded commit path. Existing `KeyRelease`,
digit substitution, OCR-fill, 160-ms debounce, source-coordinate
save writer, PDIC/PPP/SECTION and transaction formats remain unchanged.
The edit commit now avoids duplicate requeue when the value already
matches the visible target.

## Limitations
E2 headless tests cannot prove native Windows IME composition behavior;
real Windows scanned dictionary E3 must verify CJK typing/paste/FocusOut,
undo/redo and save/reopen. No OCR strategy or crop/coordinate transform
changes. Keep #663 Draft/Open/Unmerged, #503/#562 open and #483 W1–W11
incomplete. Do not represent the result as OS-level cross-file CAS or
power-loss atomicity.
