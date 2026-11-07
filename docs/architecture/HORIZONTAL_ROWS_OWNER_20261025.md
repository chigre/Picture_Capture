# Round 55 — horizontal OCR-row reconstruction and N-column grouping (2026-10-25)

Issue #562 / Draft PR #663. Eleven complete numerical implementations moved
to new canonical `preprocess/horizontal_rows.py`:

- normalize text angle and compute weighted median/percentile;
- derive independent top/bottom text polygon edge angles, weighted centroid and
  dual-edge metrics;
- cluster polygon samples into rows using original median ink height threshold;
- assign every valid OCR text polygon to a structural column by maximum
  horizontal overlap, excluding page-spanning headers and retaining sparse
  columns in diagnostics;
- build row clusters for each column; support fixed before/after correspondence
  and the read-only public column-row API.

`preprocess/geometry.py` retains all **eleven original callables and signatures**,
including `horizontal_column_rows`, so external callers in
`preprocess/text_line_geometry.py`, `preprocess/orthogonal_dewarp.py` and
perspective correction do not change imports. The legacy layer supplies current
`AppSettings`, `polygon_boxes`, `infer_layout_from_boxes`, polygon sample,
edge-angle, weighted-statistics, clustering and index hooks at **call time**.
New owner imports only numpy/math/types; no reverse dependency on
`geometry.py`, layout, Tk, app, processing or OCR.

All original thresholds, weights, fallbacks and layout call kwargs are unchanged.
Focused characterization covers weighted statistics, malformed/vertical polygon
rejection, live patchpoints, three staggered columns plus a spanning header,
layout failure/single-column fallback, fixed-group fast path, import isolation,
old public signatures and pickle identity. Existing high-order perspective,
orthogonal and 2/3/N-column tests remain in full regression.

No PDIC/PPP/SECTION, Profile, OCR model/cache, source pixel/coordinate space,
crop/export or Tk callback changes. Full exact-head CI and OCR 3-OS smoke
required. Real scanned dictionary-page manual acceptance remains NOT DONE.
Keep PR #663 Draft, unmerged.
