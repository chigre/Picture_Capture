# Issue #419 — actual-operation CPU / memory audit (2026-10-13)

**Source revision:** `main@130f3caf` with #419 follow-up PRs #462–#464 proposed separately. Audit is trace-based; no real user scan or profiler recording was available. Never infer a measured performance gain from a static inspection alone.

## Entry point and operational traces

| Operation | Source trace | Resource mechanism | Work / guard |
| --- | --- | --- | --- |
| Page change / preview | `app.py:_load_page()` or `load_page()` / `_get_cached_display_photo()` | Full-resolution RGB resident while resized `PhotoImage` and optional preloaded next-page image coexist. Worst-case RGB scan memory approximates `width × height × 3` bytes per copy. Zoom changes generate a new resized image. | **Keep** existing single-photo cache and async preloading. Measure actual RSS across 50 fast page changes, multi-monitor zoom, review window. Do not retain a full-size image per previous page. |
| Recent project updates on page change | `app.py` calls `touch_recent_project` from page loading, then `_save_session_state` | Registry load + JSON write + fsync on each navigation. #462 adds a short OS lock to protect correctness; frequent large-project page browsing could be fsync-heavy. | **Investigate:** profile navigation p50/p95 latency and writes/sec. Consider write coalescing only if explicit resume-crash tolerance is agreed; do not weaken crash recovery for speed. |
| Layout / ordinary drawing | `layout_core_understanding:understand_layout_core → _image_fingerprint` | Full raster converted into another huge `bytes` allocation even on a cache lookup. | #463 streams 16MiB+ images in ~4MiB chunks (preserving exact hash). PIL readonly images can reuse weak fingerprint; mutable images always rehash. Benchmark CPU tradeoff; tile overhead may be slower than monolithic hashing despite memory saving. |
| Crop PSW/PWW/PIC | `processing_core:split_single_lines / split_whole_entries / split_illustrations` | Per-page source decode + in-memory crops; worker count multiplies peak memory. Images are opened separately by export modes; concurrent exports may independently decode the same page. | Existing GUI parallel runner bounds active futures by worker count. Benchmark 1/2/4/6 workers against peak RSS; don't blindly increase worker count when scans are 600 dpi. |
| Full-project PNG standardization | `crop/export_output.normalize_project_crop_widths` | Enumerates every existing word/picture PNG and checks their dimensions; auto target reads width manifests and legacy image headers. The workload scales with entire project, not just new pages. | Already moved off the UI thread in #461. **Candidate optimization**: incremental per-page freshness bookkeeping only if target-width changes and conversion parity can be proved. No speculative rewrite in this PR. |
| Crop standalone coordinator | `single_line_parallel.run_single_line_pages` | Prior implementation submitted every page to `ProcessPoolExecutor`; `futures` memory and pending pickle data scale with requested pages. | #464 limits in-flight futures to `2 × workers`, checks cooperative cancellation before further submission, waits for running page transactions. Note actual GUI uses `app._start_parallel_batch_task` which **already** limited dispatch to `workers`. |
| Project path resolution | `project_storage.is_managed_project()` invoked by `qt_root`/sidecar helpers | Repeated JSON parsing and file opening, particularly expensive on network shares. | #463 memoizes parsed manifests by dev/inode/size/mtime/ctime and clears on writes. One cheap stat remains each lookup. |
| CC-CEDICT lexical validation | `cc_cedict._load_index()` | Multiple large resident dictionaries/sets per Python process; cache normally loaded once, but external replacement preserving mtime could be missed. | #463 keeps resident dictionary unchanged and uses broader filesystem identity to trigger a reload. **Future**: measure index RAM and lazy/mmap alternatives before redesign. |
| Online lexical lookup | `network_lookup.lookup_word_free` | Previous fresh thread pool on every lookup; `response.read()` had no explicit limit. | #463 shares three lazily instantiated workers and caps JSON payload at 1 MiB. Bound keeps at most three network operations concurrent; queue latency during burst lookup needs profiling. |
| Review focused filters | `app.py:_cache_filter_batch_payload` | Cache retains up to four batches of crop payloads; size depends on high-DPI word images. | Existing cap of four; instrument retained byte totals and inspect if GUI retains old tkinter photos when swapping batches. |

## Preliminary synthetic reference (not genuine dictionary measurements)

An independent local Pillow run repeated the two hash algorithms five times on a
**synthetic** 3000×4200 RGB page (12.6 megapixels; 36.0 MiB raw RGB).
Median timings and Python peak tracked by `tracemalloc` were:

| Hash strategy | Median duration (5 repeats) | Median peak tracked allocation |
| --- | ---: | ---: |
| Monolithic `image.tobytes()` + BLAKE2b | 73.1 ms | 72.2 MiB |
| 4 MiB-tiled, same BLAKE2b digest | 80.6 ms | 8.0 MiB |

This demonstration suggests an **~89% drop in Python-tracked temporary
allocation at the expense of ~10% more hash time on this synthetic image**.
Numbers are not from repository CI, not true OS peak RSS, and not an estimate
of GUI throughput. End-to-end page decoding and native PIL allocations are
excluded; benchmark supplied real user scans before tuning thresholds.

Other operational findings: `app.py:_start_network_lookup` currently creates
a separate daemon thread per uncached request; the 550 ms normal debounce and
serial result filtering reduce unnecessary work but do not cap concurrent outer
threads during rapid forced lookups. `_network_lookup_cache` retains entries
for the review-window lifetime without an explicit count limit. Investigate
request coalescing and LRU bounds with GUI interaction tests; these are *new
follow-up candidates*, not treated as solved by the shared inner pool in #463.

## Scope and validity of fixes

- #462: registry object identity + cleanup and cross-instance lost updates are correctness issues; tests must cover GC and concurrent mutations.
- #463: content identity and response-size limits are correctness/safety measures. Image hashing and thread reuse are performance changes; **measure their CPU impact** before extrapolating results to scan collections.
- #464: bounded coordinator for a secondary single-line entrypoint. The *actual main-window GUI* already had a bounded process dispatcher; do not attribute its pre-existing behavior to this patch.

## Reproducible benchmark command

```powershell
uv run python scripts/benchmark_issue419_hotpaths.py --image "D:\scans\page_600dpi.tif" --project "D:\dictionary" --repeats 5 --json "issue419-perf.json"
```

Repeat with >=3 genuine scans representing 300 and 600 dpi, grayscale and RGB, one/two/multi-column. Report wall time, Python allocations, and **OS peak RSS** (Task Manager / Process Explorer on Windows). `tracemalloc` deliberately does not claim to cover all PIL native allocations. Add task-level benchmarks for single-line 1, 2, 4, 6 workers and GUI page-turn p95 latency.

## Acceptance criteria / contraindications

- No change in PDIC, PPP, section mapping, layout hash, crop geometry or exported image bytes except where explicitly intended.
- A picture edited in-place must invalidate the Layout key even if object identity and dimensions are unchanged.
- Project-manifest replacement, manual text updates and dictionary index replacement must invalidate caches.
- Cancellations must prevent dispatch of *future* work; running page-level file transactions finish safely.
- Any post-merge CPU slowdown from bounded tiling on representative genuine scans should prompt a targeted threshold adjustment with new benchmarks, **not** relaxing image-content verification.
