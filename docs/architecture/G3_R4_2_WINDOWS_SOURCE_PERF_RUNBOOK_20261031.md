# G3 R4.2 — Windows local, read-only source fingerprint latency probe (2026-10-31)

**Status: tool and synthetic E2 automation only; Windows operator E3 NOT PERFORMED.** This is a continuation of [focused save source ownership](G3_R4_2_FOCUSED_SAVE_SOURCE_20261031.md) and the existing [G3 operator checklist](G3_R4_2_OPERATOR_ACCEPTANCE_20261030.md). It neither certifies crop correctness nor replaces [#483](https://github.com/chigre/Picture_Capture/issues/483) W1–W11 / [#503](https://github.com/chigre/Picture_Capture/issues/503) Undo/Redo / R3 E3. The sole PR [#663](https://github.com/chigre/Picture_Capture/pull/663) stays Draft/Open/Unmerged; main is unchanged.

## Why this packet exists

The async crop-cache key now hashes the *actual image, PDIC and active SECTION bytes*; an active filtered save additionally hashes the *image and SECTION* before/after PDIC publication. This adds bounded SHA-256 file I/O per source check; synthetic unit tests prove correctness, **not latency on a real Windows SSD/HDD, a real 300–600 DPI TIFF, or UI responsiveness**. The probe calls the **existing** production `focused_crop_source_witness` and `focused_save_source_witness` rather than a benchmark-only surrogate. It deliberately measures direct source-fingerprint wall time, not end-to-end Tk response, OCR or transaction latency.

## Safest first run: disposable synthetic page, no private input

From this exact checkout with the project's locked environment:

```powershell
$REV = (git rev-parse HEAD).Trim()
uv run --locked python scripts/benchmark_g3_focused_source_guard.py --synthetic --side 1024 --rounds 7 --warmups 2
uv run --locked python scripts/benchmark_g3_focused_source_guard.py --synthetic --side 3072 --rounds 7 --warmups 2
```

The probe creates a temporary synthetic BMP, 8-field synthetic PDIC and synthetic **benchmark-only** SECTION fixture in a self-cleaning OS temporary directory; no source witness is persisted, and it does not invoke the GUI or OCR. The synthetic SECTION is not proof of application SECTION-v2 semantics. Treat timings as developer-machine synthetic E2 only.

## Optional real local source: READ-ONLY, without GUI or automatic evidence upload

**NOT PERFORMED / requires the authorized Windows operator.** Make an independently backed-up, disposable *local copy* of one real dictionary project. Choose the actual original-image page directly inside the project root, where the application-managed or legacy PDIC and optional active SECTION paths can be resolved by the existing project storage logic. Keep the project **closed** and ensure no external process is writing. Do not choose a symlink or junction. Verify the exact Git SHA, Windows build, Python and storage mode locally.

```powershell
$REV = (git rev-parse HEAD).Trim()
$PAGE = "D:\\AuthorizedDisposableProject\\001.png" # replace locally; do not paste publicly
uv run --locked python scripts/benchmark_g3_focused_source_guard.py --image "$PAGE" --rounds 7 --warmups 2
```

The CLI has no output-file argument and does not create/write a real-project file. If a private record is required, use shell redirection **only** to a restricted local folder **outside** both the project and repository, for example `> "$EVID\\g3-source-latency.json"`; never upload it to GitHub, ChatGPT, CI, crash reporting or telemetry. The command line and PowerShell history can still contain the private `$PAGE` path: keep that shell private. The probe refuses a missing PDIC, image/PDIC/SECTION symlinks, unreadable source, and changed source bytes; on failure it emits only a generic error without a report or raw exception. Nonzero exit is **NOT a benchmark result**, not a permission to repair or overwrite files.

A successful JSON report has only:
- `schema`, `dataset` (`synthetic` or `local-readonly`), `human_acceptance=NOT_PERFORMED`;
- `rounds`, `warmups`, original image size in MiB and SECTION presence;
- `crop_guard_ms` and `save_guard_ms` with median/nearest-rank p95/maximum, and `source_unchanged=true`.

It never prints project/image path, page stem, PDIC word, raw SECTION, source hash, pixel bytes, OCR text, manual labels or traceback. It *does* return coarse source size and SECTION presence, so the report is still private operational data, not automatically publication-safe. Stopwatch intervals exclude extra cross-checks, Tk render, actual image decoding, OCR, human actions and PDIC disk writes. Warm-up runs are excluded from the reported samples.

## Operator evidence and performance stop rule (still NOT PERFORMED)

Record locally: exact SHA, actual Windows build/Python, storage type (SSD/HDD), image dimensions/formats **without names**, image MiB, source-copy yes/no, number of samples, median/p95 direct crop/source-save milliseconds, any error, observed native Tk responsiveness and the human case outcome **PASS / FAIL / NOT PERFORMED**. Do not impose a fabricated absolute millisecond SLA from synthetic CI; compare ordinary focused-review navigation and autosave with toggles/default-OFF on the *same* disposable project, especially with larger scanned pages, while the operator observes whether the UI freezes. A direct fingerprint benchmark alone never proves UI latency acceptable.

**Stop** rather than retry blindly if `source_unchanged` cannot be established, the benchmark returns nonzero, the real project is changed externally, the underlying PDIC/SECTION is ambiguous, real UI crops map to incorrect original X/Y, an unsaved edit vanishes, or human text has been overwritten. Preserve source bytes and human edits; keep private details local and record only a sanitized outcome in PR #663. Use [R3 E3 local evidence helper](../roadmaps/R3_WINDOWS_E3_LOCAL_EVIDENCE_RUNBOOK_20261030.md) for separate before/after/reopen read-only integrity snapshots; that utility also does **not** pronounce human E3 PASS.

## Test-first source and automation scope

- Test-only `a2c89e692cd199731174862cabd117c627a8dc01` added `tests/test_g3_r4_source_guard_local_benchmark_20261031.py`. [Red-first CI #41171166506](https://github.com/chigre/Picture_Capture/actions/runs/41171166506) Ubuntu Python 3.13 shows **5 expected missing-tool failures**, **5,018 passed, 3 skipped**, i.e. a missing tool rather than a pre-existing production corruption. Two refusal tests initially observed a coincidental failure exit from a missing executable; they were strengthened in `9b60261f2c7e85daf67355034f56472c98adbb22` to require the actual intended generic errors.
- Tool implementation `d3dc69799adfd9ca50434c6f31287e25c6248275` invokes production witnesses, checks byte stability across rounds, reports fixed-schema numeric latency only and runs entirely read-only on real sources. It generates ephemeral files **only** for the explicit synthetic mode.
- Source [CI #41171197847](https://github.com/chigre/Picture_Capture/actions/runs/41171197847) Ubuntu Python3.13 **5,023 passed, 3 skipped** and macOS Python3.13 full suite passed at this audit draft; the other OS/Python jobs remained in progress. [OCR #41171197791](https://github.com/chigre/Picture_Capture/actions/runs/41171197791) passed 3/3 OS. The amended-test source `9b60261f2c7e85daf67355034f56472c98adbb22` also requires exact-head CI.
- **Do not promote E2 to green until this documentation commit's own exact-HEAD CI 6/6, Risk-tier gate, OCR 3/3, CodeQL Analyze Python/Actions 2/2 and PR review are verified.** Skipped documentation-only jobs must not be claimed as passed. No actual real scanned dictionary runtime, source I/O latency, Windows human E3, #483 or #503 work has been executed.

The underlying SHA-256 probes remain discrete optimistic byte guards, **not** atomic cross-file transactions. A later external update can invalidate the measured source; no isolated benchmark is a reliability guarantee.
