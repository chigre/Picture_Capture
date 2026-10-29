# G3 R5 score/q parity boundary audit — 2026-10-30

Status: **source-grounded audit / next work only**. No R5.1/R5.2 production change, no training, no R4 priority queue enablement.

## Two distinct score semantics

- In `src/picture_capture/ocr/candidate_filter.py`, `filter_headword_records()` computes candidate **score** using parser presence, source-relative left alignment, selected POS/inflection/variant/pronunciation/descriptor, leading structure, typography, line gap, and CJK right-context evidence. Its subsequent acceptance gate also depends on header/column bounds, Profile policy, continuation/noise rejection, CJK visual requirements, user filter rules and `paddle_min_candidate_score`. A plain score-only comparison is not acceptance parity.
- In `src/picture_capture/ocr/pairing_arbitration.py`, `_engine_quality()` computes multi-engine **q** from the already available per-engine score, OCR confidence, accepted bit, structural/visual/typography flags, independently paired image boundary, forced accept/reject and repair penalties. `_arbitrate_pair()` compares per-engine q for Paddle/Tesseract/Lens under agreement, user-configured review margin, engine availability and Lens diagnostic-only rules. **q is not the same as candidate score**, and neither is a probability or a verified ground-truth label.
- `src/picture_capture/ocr/headword_core_runtime.py` and current OCR facades expose patchable historical callbacks into these physical owners. Preserve their call-time injection and `__module__`/public signatures where tested.

## Proposed minimal R5.1 implementation boundary (not executed)

1. Characterize current candidate score and acceptance diagnostics with synthetic Latin/POS, continuation/repair, CJK single glyph/marker and structural-veto controls; characterize q and chosen-engine output independently.
2. Introduce an immutable, serializable primitive-only feature snapshot for candidate **score** first. It must contain explicit booleans for the existing terms, and must not include mutable images, OCR engine objects, `Entry` or file handles. Add a pure scorer that exactly reproduces existing terms and floats; retain the current call-time source collector and the exact acceptance/gate ordering.
3. Only after source-head score parity, consider independently extracting the q math, retaining its existing `_engine_quality(deps,pair,prefix)` callback contract and `_arbitrate_pair` tie/equality semantics. Do not combine the two scores or retune weights.

## Before calling any R5 work verified

Assert exact candidate score, accepted flag, reject reason, `features` and image/source coordinate fields; independently assert q, chosen engine, needs-review and decision reason across Paddle/Tesseract/Lens (including diagnostic-only Lens), missing keys, invalid boundary strength, forced overrides, repaired OCR and close ties. Both unit-level old/new parity and integrated golden tests must pass on Windows/macOS/Ubuntu Python 3.10/3.13, OCR Smoke, CodeQL, architecture guard unchanged. All experiments default OFF; existing PDIC/PPP/SECTION and source image pixels remain byte-stable.

This audit neither bypasses deferred real Windows R3 E3 / #483 W1-W11 nor authorizes R6 training or R8 private scan benchmarking. Continue in the same Draft PR #663; do not auto-merge.
