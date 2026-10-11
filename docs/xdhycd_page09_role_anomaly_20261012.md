# XDHYCD page 0009: image-backed Layout role anomaly repair

Date: 2026-10-12. Draft PR #459 only; no change to default branch.

## Real scan audit (offline; no copyrighted image committed)

Input: 10-page `xdhycd_training_20261012_060210_670169.zip`,
with saved user-verified PDIC markers and historical `captured_at_automatic_draw`
markers. Old page 0009: 38 verified, 60 automatic, TP 23, FP 37,
FN 15, F1=46.9%. Other 9 pages are predominantly correct.

Diagnostic visual evidence: column 1 body rows often start ~35–45 pixels
further in than true entry starts; column 2 shows a comparable separation.
A full-sized CJK head can be ~70–74 pixels high although ordinary ink
height is about 29px and normal row pitch ~42px. The old role classifier
can call the next ~42px row another entry *inside the very same glyph*.

## Repair, implemented in the Layout-core path

1. `layout_role_visual_consistency.suppress_contradictory_cjk_body_lane_entries`
   checks **actual pixel starts** of alleged entry rows against repeated,
   separated outer-entry/inner-body indent families. It only demotes a
   batch if at least 6 contradictory entries and at least 20% of
   the column's entry candidates contradict their assigned lane.
   Only horizontal CJK pages with *body indentation* are eligible.
   Other layouts, columns with insufficient observations and isolated
   ambiguous candidates retain old behavior.
2. `layout_verified_oversized_heads.recover_verified_oversized_heads`
   runs **only on the columns confirmed anomalous by step 1**. Tall,
   nearly square, high-occupancy ink components at the row front are
   treated as a physical single oversized glyph. A verified head is
   entitled to one Layout entry at its true top; false entries in its
   interior are demoted, and a missing top is restored. At least 3
   qualifying glyphs are required in a column to modify it.
3. Existing bracket-pair and generic large-head evidence remain in
   place. New evidence is attached to LayoutLine metadata, so the
   *same Layout roles* feed both visualization and the ordinary PDIC
   emitter.

## Off-line shadow evaluation (NOT an end-to-end new-software run)

This retrospectively applies the isolated pixel-start/connected-component
rules to the *historical exported markers* and source images; it is
NOT a re-execution of the full contemporary Layout detection pipeline.

- Baseline page 0009: 23 TP, 37 FP, 15 FN, F1 **46.9%**.
- Repeated ink/role contradiction veto: removes 22 FP, 0 TP.
  Result 23 TP / 15 FP / 15 FN, F1 **60.5%**.
- Additional physical large-head component evidence, with deduplication
  and top recovery: 32 TP / 0 FP / 6 FN, F1 **91.4%**.
- The other nine exported pages did not trigger the repeated-contradiction
  veto and retained their baseline lines in the shadow evaluation.

These are *proof-of-concept* checks of the decision rules, not guaranteed
post-PR metrics. Saved auto baselines were captured earlier than some
subsequent detection and normalization changes, so full runtime results
can differ.

## Regression and release gate

Synthetic tests (rather than copyrighted page scans) check:
- multiple visually body-like rows misclassified in one entry mode;
- no change when the contradiction is isolated;
- no change for non-CJK/other indentation semantics;
- a 70px display glyph does not create two entry rows;
- real oversized glyph tops are restored when missing;
- no head recovery without independently established anomaly.

**Not yet established:** end-to-end evaluation on all ten true source
scans using the *exact current commit*, with the user's Profile and all
current auto-layout switches. The next acceptance criterion is no decrease
on the other nine pages, no loss of true bracket-pair markers, and
substantial improvement to page 0009 on both columns. No claim of perfect
recovery is made; the six still-missed markers in the shadow evaluation
need separate evidence before any additional rescue rule.
