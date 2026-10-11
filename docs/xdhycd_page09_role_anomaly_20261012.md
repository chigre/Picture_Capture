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
  and top recovery across the full body height: **33 TP / 0 FP / 5 FN,
  F1 93.0%**. A preliminary crop truncated the right-column bottom
  head; the complete body range confirms it is another valid glyph.
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
recovery is made; the five still-missed markers in the shadow evaluation
need separate evidence before any additional rescue rule.

## Real rerun failure discovered at 06:28 (2026-10-12 +08:00)

The user confirmed that `xdhycd_training_20261012_062832_512411.zip`
was made after restarting the latest PR branch. Its new
`captured_at_automatic_draw` list has the exact same 60 ordered
coordinates **and source labels** as the earlier 06:00 capture.
This falsifies any claim that the first PR repair succeeded in
production. The new export's `ground_truth_lines` are the same 60
*unmodified auto lines*, so they must not be treated as human labels.
Use the earlier 38 user-verified markers for comparisons.

### Confirmed implementation error

`layout_role_visual_consistency` compared ink at `LayoutLine.y0`
against indent modes derived from that same raw line. The check was
not an independent validator; it did not fire on page 0009. The
earlier shadow evaluation examined the pixels **following the
rendered marker Y**, a different physical sampling interval.
The 93% figure is a *retrospective shadow replay*, not an observed
performance of the originally submitted patch.

### Revised execution boundary

`ordinary_final_visual_consistency.correct_anomalous_final_ordinary_entries`
runs inside `processing.detect_entries` after role materialization,
Y refinement, oversized suppression, bracket supplement, and template
filtering but before the final reading-order return. It evaluates the
actual coordinates to be emitted, not the original mode assignment.
It requires repeated contradictory rows, separate printed indent
families, and identity horizontal CJK/body-indentation settings.
Only affected columns are eligible for independent physically verified
large-glyph restoration; ordinary untouched columns remain unchanged.
It records affected columns, removed false marker counts, removed
glyph-internal markers, and inserted glyph tops in the layout reason.

Dedicated **final-candidate** synthetic tests were added, not just
intermediate Layout object tests. CI must pass on Windows, macOS and
Linux before finalizing this revision.

**Pending user acceptance**: this final-stage patch still requires a
new automatic draw from its latest commit and comparison with the
38 prior user-verified markers. Do not report shadow replay as real
performance.

## Latest 06:59 capture: two residual omissions and two extra markers

The 2026-10-12 06:59 (+08:00) export
`xdhycd_training_20261012_065918_956713.zip` contains only page
`XDHYCD_0009.png`. Its preserved automatic snapshot has **38** markers
and its saved PDIC also has **38**; the export's correction diff is
36 unchanged, 2 added, 2 deleted. The saved result is not a complete
independent multi-reader truth set, but these four edits are explicit.

New saved boundaries absent from auto:
- Left column y=1492: an intact bracketed two-character fish headword
  (printed left bracket x=3..17, right bracket x=83..97, actual print
  y=1495..1520).
- Left column y=2125: the four-character bracketed `鞍马劳顿`;
  printed left bracket x=1..15, printed y=2128..2154; its closing
  bracket is joined to the final glyph near x≈142.

Removed erroneous automatic markers:
- Right column y=908: ordinary Layout-role marker in completely blank
  ink space before a separately proven oversized glyph at y=950.
- Right column y=2037: same pattern, preceding the proven y=2081 head.

### Concrete root cause and narrowly scoped changes

The original `illustration_detection._rle_components` deliberately
connects previous-row run intervals up to one **extra blank column** beyond
true 8-neighborhood adjacency. This is suitable for near-touching drawing
fragments but not narrow print-bracket components. On the real scan it
incorrectly fused otherwise separate 15px brackets into 31px and 48px
components near y=1495, causing both directional-shape checks to fail.
New `ordinary_bracket_pair._strict_bracket_components` uses actual
8-neighbor adjacency *only for bracket printing* and does not change
illustration behavior globally.

The second omitted head is a variable-length bracket word with a closing
bracket physically fused to the previous Han ideograph; a repeated
two-character offset cannot locate it. A conservative longer-span
right-bracket-shape search now runs only after at least three independent
intact same-column pairs establish a reliable printed template.

The two extra markers have **no ink anywhere across the next 31px of
their entire column**; each is one line pitch before an independently
proven large printed glyph. The last-mile output filter now rejects
only this conjunction: unproven Layout-only entry, full-column
blank next-row interval, and a separate verified bracket/large-head
entry 0.85–2.05 line heights below. Bracket-confirmed and
large-glyph-confirmed markers are never removed.

### Acceptance limits

The pixel/component evidence was reproduced on the original scan and
specific synthetic pytest regressions were added for blank-separated
bracket glyphs, variable-length attached closing glyphs, near-bottom
headwords, and two misleading blank rows. CI alone does not establish
a corrected complete output. To confirm on a user installation, redraw
`XDHYCD_0009.png` at the latest PR HEAD and export an untouched
automatic baseline; compare it with the saved 38-line reference, then
run the other nine pages for unintended changes.
