# PC-CQ R4.2 — SECTION same-size/same-mtime content witness (2026-11-07)

## Distinct reachable source gap

Earlier SECTION path-and-metadata invalidation [b29cfe64627d9fe7e272366062f3c620de524c84](https://github.com/chigre/PictureCapture/commit/b29cfe64627d9fe7e272366062f3c620de524c84) catches ordinary rewrite/remove/creation. A file sync/restore that copies different SECTION bytes while preserving file size and modification time defeats metadata-only comparison, even when the correct canonical/migrated path is pinned. SECTION content determines Entry reading order in adjacent-page cache; prefetched rows must not be consumed under another SECTION revision.

## True failure-first evidence

- New test-only [`b9db9eafed39c7400c7d4ee39546d4b5050ea9a0`](https://github.com/chigre/PictureCapture/commit/b9db9eafed39c7400c7d4ee39546d4b5050ea9a0), `tests/test_r42_review_prefetch_section_same_stamp_20261107.py`, writes synthetic SECTION v2, changes 80→60 without changing byte count and explicitly restores mtime_ns. Tests require worker key invalidation and _take_prefetched_page refusal, plus an unchanged positive control.
- [RED CI #42256668385](https://github.com/chigre/PictureCapture/actions/runs/42256668385): Ubuntu Python3.13 and Python3.10 both **2 intended SECTION assertion failures / 5754 passed / 3 skipped**, with unchanged positive control passing. RED is not acceptance.
- No real project scans, OCR, private data or external artifacts were used.

## Minimal repair and gates

- [Source `0dd0adfc6b37de55145a5b3e19e1d38d0763d880`](https://github.com/chigre/PictureCapture/commit/0dd0adfc6b37de55145a5b3e19e1d38d0763d880): only `src/picture_capture/ui/review_page_lifecycle.py`; hashes resolved SECTION bytes in 64-KiB streaming blocks and includes SHA-256 digest in the existing prefetch signature. Missing SECTION remains legitimate absent input; an existing unreadable SECTION emits a non-reusable witness (not a stable success). File path and stat still included. Does not create CAS or cross-file atomicity.
- [Source CI #42257286009](https://github.com/chigre/PictureCapture/actions/runs/42257286009): **Python 3.10 / ubuntu-latest:success, Python 3.10 / windows-latest:success, Python 3.10 / macos-latest:success, test (ubuntu-latest):success, test (windows-latest):success, test (macos-latest):queued** at checkpoint. [OCR #42257285923](https://github.com/chigre/PictureCapture/actions/runs/42257285923) 3/3 SUCCESS; [CodeQL #42257278831](https://github.com/chigre/PictureCapture/actions/runs/42257278831) Python/Actions 2/2 SUCCESS. Source test fixes are inherited only by descendants and require each latest HEAD's independent gates. Documentation check SKIPPED ≠ PASS.

## Limits

Not an OS-level source version CAS, atomic multi-file transaction, user-data benchmark or accuracy/performance result. No persistent schema/SECTION geometry, original XY, consent or experiment changes. Windows human E3, #483 W1-W11, #503 Undo/Redo and actual sidecar save-reopen remain NOT PERFORMED/DEFERRED.
