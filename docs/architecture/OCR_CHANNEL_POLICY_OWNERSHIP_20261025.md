# Round 48 — OCR channel policy and result accessor ownership (2026-10-25)

Working branch: `refactor/562-retire-root-image-utils-20261024`, Draft PR #663. Baseline head: `bc1fd6d1bd48604ab467de3ecd7fd46276b3d4f5`.

The root `ocr_channel.py` intentionally owns the **same original dataclass,
session, and public function import paths** for pickle and third-party caller
compatibility. The implementation of its case-folded engine alias normalization,
plan enabled/voting membership, diagnostic Lens conflict decision, candidate
success predicate and ordered result accessors is now physically located in the
existing domain owners:

- `ocr/channel_policy.py`: selection normalization, enabled/vote membership,
  conflict-trigger decision (uses caller's live `channel_text_key` per invocation).
- `ocr/channel_results.py`: candidate success, first-engine lookup, ordered
  successful tuple (no data model relocation).

Public wrappers remain intentionally thin. No Paddle engine initialization at
import, new cache, data-field or settings/PDIC/PPP/OCR sidecar change. The Lens
conflict evaluator retains the historical **twice-per-item callback** for
nonempty text, including the behavior of a patched callback.

New `tests/test_issue562_ocr_channel_policy_round48_20261025.py` covers:
stable pickle/module and field identity, owner code placement, monkeypatch
propagation, sequence/tuple order, failure cases and generator input.

Gate: exact-head CI (six platform/runtime combinations), OCR Platform Smoke
(three OS), architecture guard and manual representative scanned-page checks.
Passing unit tests does **not** complete the pending GUI/Profile/crop/export
manual parity review. PR #663 must remain Draft and unmerged.
