# G3 R4.2 — Exact source XY, page-owner and empty-batch PDIC refusal

**Date:** 2026-11-03 SGT. **Sole development PR:** #663 Draft/Open/Unmerged. **main:** `ec20989ea8c026cca5337293e67850b6b6df30f2`. **Code/test HEAD:** `b4ed2bad40c39e00732c55ba25323104444660de`.

## Verified fail-first counterexample
Previously `int(change["x"])` and `int(change["y"])` truncated nonintegral values, and numeric strings also aliased valid row coordinates. A crafted `x=3.9, y=4` change could write to the actual marker at (3,4), despite never identifying that exact source pixel. The low-level writer also did not reject a page argument different from `pages[page_index]`, ignored a conflicting `change["page_index"]`, and wrote/reformatted an unchanged PDIC when the input batch was empty.

Test-only [`e68d0559`](https://github.com/chigre/Picture_Capture/commit/e68d055972d0d493ca8e2655c7d57ecc30dcdbda) introduces 11 synthetic cases: fractional XY, bool XY, string XY, wrong page, wrong per-change page, out-of-range index, zero edits and a valid integer positive control. [RED CI #41610202553](https://github.com/chigre/Picture_Capture/actions/runs/41610202553) failed all six OS/Python jobs on the 10 intended negative/no-op cases; Ubuntu3.13 **10 failed/5450 passed/3 skipped**; RED Risk-tier gate failed as expected. This is evidence of old bugs, not passing acceptance.

## Bounded source fix and exact-head verification
[`b4ed2bad`](https://github.com/chigre/Picture_Capture/commit/b4ed2bad40c39e00732c55ba25323104444660de) limits source XY to real integral coordinates (`operator.index`, explicit bool refusal), validates `page_index`, matching page and per-change ownership, and returns `([], [])` for an empty batch without reading or writing PDIC. The canonical source file and call-time injected writer stay in place; there is no schema migration.

- [CI #41610298182](https://github.com/chigre/Picture_Capture/actions/runs/41610298182): six Windows/macOS/Ubuntu × Python3.10/3.13 jobs **SUCCESS**, Risk tier and Risk-tier CI gate **SUCCESS**; Ubuntu Python3.13 **5460 passed/3 skipped**.
- [OCR #41610298176](https://github.com/chigre/Picture_Capture/actions/runs/41610298176): Windows/macOS/Ubuntu **3/3 SUCCESS**.
- [CodeQL #41610293695](https://github.com/chigre/Picture_Capture/actions/runs/41610293695): Analyze Python/Actions **2/2 SUCCESS**.
- Documentation architecture check **SKIPPED, NOT PASS**. The later docs checkpoint has its own HEAD and must independently pass exact-head gates.

## Unchanged safety boundaries
Guarded PDIC writer, original source XY, file formats, session interfaces and default-OFF experimental controls remain unchanged. This adds no cross-file OS lock/CAS, rollback, OCR cache update or silent retry. No real project data was used.

**NOT PERFORMED:** Windows human E3, #483 W1–W11, #503 human Undo/Redo, real dictionary scans/PDIC/PPP/SECTION/Profile/OCR save/reopen, R6/R8 real labels. Preserve #503/#562/#483 Open and PR #663 Draft; no automatic merge or Ready transition.
