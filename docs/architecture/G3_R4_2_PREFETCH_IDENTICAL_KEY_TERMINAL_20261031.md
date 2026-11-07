# G3 R4.2 — identical-key reissued prefetch must not be stolen by old terminal callbacks

Date: 2026-10-31. Sole Draft PR #663; main `ec20989ea8c026cca5337293e67850b6b6df30f2` unchanged. Automated synthetic E2 only.

## Independently verified baseline and RED evidence

Predecessor `8894d4cc4b781d811b429a051006d41d90ec46f9`: [CI #41216783408](https://github.com/chigre/Picture_Capture/actions/runs/41216783408) six Windows/macOS/Ubuntu × Python 3.10/3.13 success plus Risk tier/gate; [OCR #41216783393](https://github.com/chigre/Picture_Capture/actions/runs/41216783393) 3/3 success; [CodeQL #41216780401](https://github.com/chigre/Picture_Capture/actions/runs/41216780401) Python/Actions 2/2 success. These green results **do not** apply to the new change.

With the existing prefetch owner represented by a tuple cache key, a completed attempt sets `_filter_prefetch_key = None`. After a legitimate cache eviction or failed attempt, another worker can be scheduled for the **same epoch and exact key**. The prior worker's duplicated/contradictory done/failed callback still matches the new worker's key, letting it clear the new key and/or publish a result under the wrong worker's ownership.

Test-only `e2c6b5c1c01c134557909c0f8ad2033c2d457bc0` adds four parameterized temporary 8×8 BMP/PDIC/SECTION synthetic tests, covering first terminal done/failed × late old terminal done/failed with a newly dispatched **identical-key** owner; each asserts that the newer worker retains its key, that no old payload is published, and that only the newer worker can successfully complete. [CI #41218910472](https://github.com/chigre/Picture_Capture/actions/runs/41218910472) macOS Python 3.13 observed **4 targeted FAILED / 5,208 passed / 2 skipped**. This intentionally red SHA is not a passed gate.

## Minimal production fix

Commit `24d682ff4ffdd58f54b4e68762dee3017a819466` changes only `src/picture_capture/ui/focused_filter_workflow.py::_schedule_filter_next_batch_preload`:

1. A `terminal_claimed` mutable cell belongs to **one prefetch dispatch**, independent of the image/PDIC/SECTION cache key.
2. In both Tk `done` and `failed`, reject any already consumed terminal callback. The existing epoch and active-key checks run before first claim, preserving cross-epoch refusal. Claim the first valid terminal event before clearing `_filter_prefetch_key` or performing any cache/recovery effects.
3. Duplicate or contradictory completion from the old job cannot clear or populate the new job's identical-key state. The accepted new job continues to publish normally. Preserve source witness, pending human edits, save-running guards and bounded direct-render recovery.

This closes **post-terminal same-key reissue**; it is not a guarantee of independent job identity if application code explicitly cancels/reassigns a same-key prefetch **before any terminal event**. That separate race should remain an audit item, not be mislabeled verified. Volatile source hashes are not atomic multi-file CAS. No changes to persisted PDIC/PPP/SECTION/Profile/manual-selection schema, source XY, actual disk save transaction or default-OFF experiments; no real scans or private content.

## Pending final gates and human boundaries

At this documentation commit, exact-head CI six combinations + Risk-tier gate, OCR 3/3 and CodeQL Python/Actions 2/2 remain **PENDING**; confirm by workflow SHA before post-gate PR comment. Do not inherit green status from earlier commits or intermediate source-only builds.

**NOT PERFORMED**: Windows R3 E3, #483 W1–W11, #503 operator/compound Undo/Redo, real dictionary OCR/crop/PDIC/PPP/SECTION/Profile reopen, source-coordinate human checks, real benchmark. Automated E2 is not human E3.

**DEFERRED**: R6 verified human-label training, R8 real scans. Keep only PR #663 Draft/Open/Unmerged, main unchanged, issues #503/#562/#483 Open. Next: inspect *before-first-terminal* same-key reissue/cancellation and the direct-versus-prefetch save/SECTION transition, each by a distinct test-first packet, no duplicative refactor.
