# PC-CQ v1.3.0 G1 — serialized filtered-write success must honor in-flight reversion (2026-10-29)

## Loss path and fail-first
The asynchronous filter writer may snapshot an original-image XY change
`甲 -> 乙`. While that writer is running, the user reverts the visible row
to `甲`. The `_queue_focused_change` correctly removes the old pending
record because at that instant the on-disk `original_word` is `甲`.
But the old worker may then publish `乙`. Before this fix,
`done` rebased the target's `original_word` to `乙` without
recreating the now-needed `乙 -> 甲` pending correction, and could
approve a page change or deferred close despite the user still seeing
`甲` in the filtered editor.

Fail-first tests-only HEAD:
`1c24cdddb56bdb5632f8092a38bdc1632be2aec7`,
`tests/test_g1_filter_inflight_success_revert_20261029.py`.
Cases: true user reversion after success; request to close while reversion
is pending; redundant in-flight edit equal to saved word is removed;
different newer edit is rebased correctly; legacy owners without a
`current_word` remain unchanged.

## Small correction
In `focused_filter_workflow._flush_focused_changes.done`, only for
exact source page/X/Y records **reported saved by the existing writer**,
compare the filtered target's latest `current_word` to the actual
committed `saved_word`. When no newer pending record owns the coordinate,
restore a user revision as a new guarded `saved_word -> current_word`
pending change. Respect and rebase any already queued newer edit;
remove an entry only when it redundantly equals the saved text. Existing
serial-worker scheduling commits nonempty pending before an already
requested deferred close; the main canvas reconciliation remains based
only on actual saved PDIC entries.

No new writer, no implicit conflict resolution, no coordinate fallback,
no undo-history change, no PDIC/PPP/SECTION schema change or claim of
cross-file power-loss atomicity.

## Verification and gate
Verify 6/6 Windows/macOS/Ubuntu Python 3.10/3.13 CI,
3/3 OCR smoke, Python+Actions CodeQL for the exact final HEAD.
E2 synthetic tests are not native Windows E3 scanned-dictionary approval.
The real keyboard/IME, 20 Undo/Redo, PDIC/PPP/SECTION save/reopen,
original-pixel crop and #483 W1-W11 remain NOT PERFORMED.
Keep #663 Draft/Open/Unmerged and #503/#562 open.
