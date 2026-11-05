# PC-CQ — repeated outer-entry alignment under explicit body indentation (2026-11-05)

## Problem / exact boundary

This is the **same open Draft PR #663** on `refactor/562-retire-root-image-utils-20261024`. On an ordinary Chinese→English dictionary page the user explicitly selected **正文缩进** (`indent_type=body`). Its Layout timeline stage 09, **缩进语义判定**, reported **33 body / 0 entry** despite most rows being individually aligned dictionary headwords. The UI diagnostic, not a copied user scan, gave only the following structural lane observations:

| Column | Measured local X centers / line support | Expected entry/body |
| --- | --- | --- |
| C1 | 12.0px × 10; 58.0px × 1 | 10 entry / 1 body |
| C2 | 13.6px × 11 | 11 entry / 0 body |
| C3 | 15.6px × 6; 22.1px × 2; 61.9px × 3 | 8 entry / 3 body |

The expected total is **29 entry / 4 body** for this synthetic structural fixture only; it is **not** a measurement of OCR/PDIC recall on the page.

## Root cause and scope

`layout.physical_indent.assign_binary_roles` historically seeded the body role from the most-supported lane **within each column**. This makes a column containing only one aligned entry family trivially `body`, and makes C1's sole genuine inward continuation lose to ten aligned entries. `core_understanding._resolve_directional_body_lanes` subsequently excludes a singleton inward lane from its stability threshold, so its later correction cannot rescue C1/C2 by itself. The timeline stage 09 is captured **before** that subsequent refinement; fixing only the later stage would leave a misleading RED UI step.

## Failure-first evidence (exact test-only commit)

- [Test-only RED `63907e9bd0c0cf6479f7389b0d2e6312ea3c400f`](https://github.com/chigre/PictureCapture/commit/63907e9bd0c0cf6479f7389b0d2e6312ea3c400f), [CI #42055132927](https://github.com/chigre/PictureCapture/actions/runs/42055132927), Ubuntu Python 3.13 **2 intended failures / 5735 passed / 3 skipped**. Both failures are the 33-row expected role assertions at semantic normalization (stage 09) and post-stage-09 body-lane refinement. Independent negative controls for a single unconfirmed inset and opposite headword polarity passed. No user scan, dictionary text or private sidecar is in the test file.

## Minimal source repair / explicit abstention gates

- [Source commit `b329b716f51e809320ce1169cefa765bbdc55a24`](https://github.com/chigre/PictureCapture/commit/b329b716f51e809320ce1169cefa765bbdc55a24) changes only `src/picture_capture/layout/physical_indent.py` and `src/picture_capture/layout/core_understanding.py`. `_reconcile_cross_column_body_indent` runs after normalizing per-column modes and after later directional refinement, so stage 09 and the final role result agree.
- Only for `body` polarity and **at least two columns**, require supported predominant outer starts that align across columns, no separately repeated outer lane preceding the anchor, and **at least two independent deeply inset continuation witnesses** of consistent offset (at least three supporting rows altogether). A single deep outlier cannot relabel a page.
- Preserve the physical lane clusters; label the repeated outer groups as `entry`, inward continuation groups as `body`. A column with entry-only evidence gets `body_mode=None`, not the false `body_mode=entry` from its per-column support maximum. `headword` and `none` polarity do not use this reconciliation. If page-wide confirmation is missing, retain the prior result rather than assert a new entry family; that ambiguity remains eligible for future diagnosis, not silent promotion.
- No new image processing, OCR, persisted PDIC/PPP/SECTION/Profile format, original XY, consent path, file safety transaction, external upload, model learning or real scan.

## Source-head verification and limitations

- [Exact source CI #42055921880](https://github.com/chigre/PictureCapture/actions/runs/42055921880): Windows/macOS/Ubuntu × Python 3.10/3.13 **6/6 SUCCESS**; Risk tier and Risk-tier CI gate **SUCCESS**; Ubuntu 3.13 **5737 passed / 3 skipped**, macOS and Windows 3.13 **5738 passed / 2 skipped**.
- [Exact source CodeQL dynamic #42055910901](https://github.com/chigre/PictureCapture/actions/runs/42055910901): Analyze Python and Analyze Actions **2/2 SUCCESS**.
- [Exact source OCR Platform Smoke #42055922584](https://github.com/chigre/PictureCapture/actions/runs/42055922584): **Windows and Ubuntu SUCCESS, macOS QUEUED when writing**; never count queued as pass. This test is a platform smoke, not the user's original page.
- Documentation architecture check **SKIPPED, not PASS**. The following STATE/RESUME/audit commit is **another HEAD** that needs independently checked gates.
- User original scanned page end-to-end, actual UI screenshot rerun, PDIC/PPP/SECTION save/reopen, Windows human E3, and all other deferred human work: **NOT PERFORMED**. Synthetic 29/4 expected role counts are not a verified performance or recall claim.

## Next deterministic handoff

Read live main and only #663 Open/Draft/Unmerged HEAD, exact source OCR completion and exact **new docs HEAD** CI six matrices/Risk-tier+gate/OCR three OS/CodeQL both languages. Fix any failure without weakening assertions or guards. Then resume RED-first R3 ordinary ReviewWindow/main text save or R4.2 epoch/worker/SECTION/crop prefetch/save owner. Keep the original scheduled hourly task; no new PR, merge, Ready, force-push or issue closure.
