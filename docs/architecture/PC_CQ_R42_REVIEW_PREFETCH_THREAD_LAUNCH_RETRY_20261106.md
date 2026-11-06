# PC-CQ R4.2 — prefetch thread launch failure must release in-flight owner (2026-11-06)

## Reachable source gap

The optional ReviewWindow _schedule_adjacent_preload first added a page index to _prefetch_inflight, then constructed and started a daemon Thread. When Python Thread.start() raised RuntimeError because the operating system could not start a thread, no worker ever executed its finally block. The in-flight set stayed latched for the page, the optional load exception surfaced through the caller, and later navigation could not retry. A failed first neighbor also aborted scheduling the second.

## Failure-first evidence

- Test-only [e38da39b73f59d06db8a0e711490ea482ea675eb](https://github.com/chigre/PictureCapture/commit/e38da39b73f59d06db8a0e711490ea482ea675eb) adds tests/test_r42_review_prefetch_thread_launch_retry_20261106.py. It uses deferred synthetic thread objects, no actual filesystem or background worker.
- [RED CI #42180700981](https://github.com/chigre/PictureCapture/actions/runs/42180700981), Ubuntu Python3.13 **2 intended failed / 5743 passed / 3 skipped**. Failing tests: failed start must clear in-flight and allow later retry; failed first neighbor must not block second. Existing successful single-flight positive control passed.

## Minimal fix and verified source HEAD

- [cb71f008aec5d384091b448a1c4e9a4ff6664ad5](https://github.com/chigre/PictureCapture/commit/cb71f008aec5d384091b448a1c4e9a4ff6664ad5): only src/picture_capture/ui/review_page_lifecycle.py. Catch RuntimeError/OSError around Thread construction/start; release ONLY the failed index under existing _prefetch_lock. Do not replace the worker body, crop geometry, callback owner, file signatures, persistence, or completed successful worker.
- [CI #42181016378](https://github.com/chigre/PictureCapture/actions/runs/42181016378): Windows/macOS/Ubuntu × Python3.10/3.13 **6/6 SUCCESS**, Risk-tier + Risk-tier CI gate SUCCESS; Ubuntu3.13 **5745 passed / 3 skipped**.
- [OCR #42181016349](https://github.com/chigre/PictureCapture/actions/runs/42181016349): Windows/macOS/Ubuntu **3/3 SUCCESS**. [CodeQL #42181011997](https://github.com/chigre/PictureCapture/actions/runs/42181011997): Python/Actions **2/2 SUCCESS**.
- Documentation architecture check **SKIPPED**, NOT PASS. This is E2 synthetic error injection: no actual OS resource exhaustion, real crop dataset, benchmark, OCR/PDIC/PPP save or manual GUI validation.

## Boundary / next actions

Only the existing #663 Open/Draft/Unmerged branch was modified; main stays intact. No force push, merge, Ready, new PR, persistent sidecar schema/transaction/XY edits or private uploads. Other callback epochs, in-flight invalidation on settings changes, and actual Windows E3 remain separate work. Read latest HEAD and verify exact docs checkpoint gates before the next independent RED-first package.
