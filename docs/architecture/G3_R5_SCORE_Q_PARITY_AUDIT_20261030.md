# G3 R5 score/q parity boundary audit — 2026-10-30

Status: **R5.1 E2 verified; R5.2 q extracted, exact-head E2 currently pending**. No R4 priority queue enablement, training or human acceptance claim.

## Two distinct score semantics

- In `src/picture_capture/ocr/candidate_filter.py`, `filter_headword_records()` computes candidate **score** using parser presence, source-relative left alignment, selected POS/inflection/variant/pronunciation/descriptor, leading structure, typography, line gap, and CJK right-context evidence. Its subsequent acceptance gate also depends on header/column bounds, Profile policy, continuation/noise rejection, CJK visual requirements, user filter rules and `paddle_min_candidate_score`. A plain score-only comparison is not acceptance parity.
- In `src/picture_capture/ocr/pairing_arbitration.py`, `_engine_quality()` computes multi-engine **q** from the already available per-engine score, OCR confidence, accepted bit, structural/visual/typography flags, independently paired image boundary, forced accept/reject and repair penalties. `_arbitrate_pair()` compares per-engine q for Paddle/Tesseract/Lens under agreement, user-configured review margin, engine availability and Lens diagnostic-only rules. **q is not the same as candidate score**, and neither is a probability or a verified ground-truth label.
- `src/picture_capture/ocr/headword_core_runtime.py` and current OCR facades expose patchable historical callbacks into these physical owners. Preserve their call-time injection and `__module__`/public signatures where tested.

## R5.1 implementation checkpoint (2026-10-30)

- Fail-first `9426de03f6193e42bd86e51777335beb1f7aaf14`: absent module produced the expected `ModuleNotFoundError` (Ubuntu job 123766667030), without weakening suite guards.
- Source `33fbef917be6b38bfeb85ea35c5b73edab12786c`: introduced `ocr/candidate_scoring.py`, a frozen 12-boolean `CandidateScoreFeatures` dataclass and a pure `score_candidate` preserving all 12 legacy weights and exact addition order. `candidate_filter.py` collects the same signals and delegates scoring only; no gate, reason, diagnostic schema, XY, Profile or monkeypatch facade change.
- Tests: exhaustive 2^12 = 4,096 primitive input vectors plus JSON roundtrips, no-heavy-import check, and synthetic full-pipeline differential cases for Paddle/Tesseract/Lens, Latin/CJK, forced reject and thresholds comparing entire entries and diagnostics.
- First source CI `33fbef9` had a **test-only expectation failure**: diagnostics includes a page-level `meta` record in addition to scored candidates (Ubuntu 4840 passed/1 failed/3 skipped; macOS 4841 passed/1 failed/2 skipped). The test was corrected without changing production or removing the meta contract in `f63d8805d54100adafb802ed2bedd1ff91dd226f`. **R5.1 E2 subsequently verified** on final checkpoint `234870694bca285117deb6a863c11bd705f3891c`: [CI #40965627205](https://github.com/chigre/Picture_Capture/actions/runs/40965627205) Windows/macOS/Ubuntu Python 3.10/3.13 **6/6 success + Risk-tier**, [OCR Smoke #40965627204](https://github.com/chigre/Picture_Capture/actions/runs/40965627204) **3/3 success**, CodeQL Python+Actions **2/2 success**. Not a real scan accuracy or Windows operator acceptance test.
- Remaining: independent q arithmetic extraction, tie/diagnostic-only Lens parity, then default-OFF R4 optional risk queue. R3 E3 and #483 W1–W11 remain NOT PERFORMED.

## R5.2 implementation checkpoint (2026-10-30)

- **Red-first** tests `5cd39dddc278553b10ded5d0efb57ff54f9375f3`: expected `ModuleNotFoundError` for `ocr.engine_quality_scoring` (Ubuntu CI #40967679050), not a production regression.
- **Source** `e57346968a48372a0cb633cc63c6fce8fe0f0db9`: `ocr/engine_quality_scoring.py` introduces frozen, JSON-serializable primitive-only `EngineQualityFeatures`, with pure `score_engine_quality` preserving the exact ordered q terms and penalties. Existing `pairing_arbitration._engine_quality(deps,pair,prefix)` still converts existing pair fields, clamps/handles image-boundary strength, calculates repair count, then delegates *only* the q arithmetic. No changes to `_arbitrate_pair` branches, thresholds, tie-order, source XY, OCR facades, PDIC or user data.
- **Tests** `tests/test_g3_r5_engine_quality_parity_20261030.py`: all 128 boolean evidence vectors × 4 score/conf/boundary/repair scenarios (512 direct exact-float comparisons), JSON roundtrips, malformed confidence/score preserved exceptions, missing/invalid/clamped boundary strength in Paddle/Tesseract/Lens, 15 full-record historical-vs-extracted three-engine arbitration differential cases (including Lens diagnostic-only, forced overrides, repairs, close ties, source coordinates), live monkeypatch injection and no-heavy-import contract.
- [Source CI #40967756737](https://github.com/chigre/Picture_Capture/actions/runs/40967756737), [OCR Smoke #40967756750](https://github.com/chigre/Picture_Capture/actions/runs/40967756750), CodeQL at source HEAD: OCR Smoke 3/3 success and Risk-tier success at authoring; six-platform CI and Python CodeQL still pending. **R5.2 is implemented but NOT yet E2-verified until exact source and final documentation HEAD checks are all green.**
- Next after green: G3 R4 provenance-safe priority/normal/unknown diagnostics and default-OFF focused review order. Human R3 E3 and #483 W1–W11 remain NOT PERFORMED.

## Before calling any R5 work verified

Assert exact candidate score, accepted flag, reject reason, `features` and image/source coordinate fields; independently assert q, chosen engine, needs-review and decision reason across Paddle/Tesseract/Lens (including diagnostic-only Lens), missing keys, invalid boundary strength, forced overrides, repaired OCR and close ties. Both unit-level old/new parity and integrated golden tests must pass on Windows/macOS/Ubuntu Python 3.10/3.13, OCR Smoke, CodeQL, architecture guard unchanged. All experiments default OFF; existing PDIC/PPP/SECTION and source image pixels remain byte-stable.

This audit neither bypasses deferred real Windows R3 E3 / #483 W1-W11 nor authorizes R6 training or R8 private scan benchmarking. Continue in the same Draft PR #663; do not auto-merge.
