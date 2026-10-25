# Issue #562 — real dictionary scan release-acceptance gate (2026-10-25)

**Status: MANUAL GATE OPEN / NOT PASSED.** Draft PR #663 must remain Draft
and unmerged until a human tests the actual target scanned dictionary.
The repository does **not** contain the original full-resolution dictionary
scans. Screenshots and annotated image crops cannot substitute for source
pages or source-coordinate PDIC/PPP evidence.

## Automated baseline (not manual acceptance)

`scripts/gui_project_roundtrip_smoke.py` builds a *temporary synthetic*
two-page 640×460 managed-v2 project and exercises the **real Tk/bootstrap**
and project-load worker, editable PDIC markers, in-memory PPP polygons,
canonical PDIC/PPP publication, page navigation and disk reload, settings
JSON, idempotent PPP save, and source-image SHA-256 immutability. As of Round
60, it ALSO uses the **unmocked production** `processing.split_whole_entries`
pipeline on the reopened page: it asserts published original-coordinate PNG
boxes/dimensions, pixel-for-pixel RGB comparisons with source-image
cropping (opaque normal export), nonempty synthetic ink, PWWords and width
manifests, the CropPlan JSON, no orphan temporary files, unchanged
PDIC/Profile/source PNG hashes, plus byte-for-byte PNG/manifest stability on
a second identical export. **Round 62** additionally invokes the real
`PictureCaptureApp.split_whole_current()` Tk action into
`ui/controllers/crop.CropController`, with canonical on-disk project
`_CropSettings.json`, the unmocked threaded batch worker, Tk queue poll
and asynchronous PNG-width completion callback. On job completion it compares
the GUI-generated PWWords, width manifest and PNG content SHA-256 with the
previous direct-production baseline; validates the 100% batch-progress state,
unchanged source-PDIC/PPP vertices and Profile sidecar, and original source
image immutability. This is programmatically activated UI logic, **not** a
human button click or manual Crop Preview approval. It exercises
`write_project_profile`/`load_dictionary_profile` for a real project-local
Profile v3 sidecar without opening the human Profile wizard.

It uses no installed OCR model and never invokes automated ordinary/OCR/
combined detection or *human GUI crop preview*. It now exercises a **real
production crop export**, but without a real scanner page, manual CropController
button interaction, image quality approval or OCR inference. The six-job CI
matrix runs it on
Windows/macOS/Ubuntu with Python 3.10 and 3.13 (Linux uses Xvfb). The
existing GUI construction, proofreading/R3, unit and OCR smoke are retained.

Local smoke invocation after installing locked project dependencies:

- Windows/macOS: `uv run --locked python scripts/gui_project_roundtrip_smoke.py`
- Linux GUI: `xvfb-run -a uv run --locked python scripts/gui_project_roundtrip_smoke.py`

A green result establishes **synthetic UI/persistence/export wiring only**.
It does not prove line-finding accuracy, external OCR availability, original
real-scan image performance, or real-world crop/export visual appearance.

## Manual evidence required before Ready-for-review/merge

Use a **copy** of the real dictionary project and its full-resolution image
pages, Profile, existing PDIC, PPP and PageSections data. Preserve originals.
Record the application commit SHA and OS/Python, engine/GPU availability,
software version and Profile identity; record source-image SHA-256 values
before and after all operations.

| Gate | Required actions | Evidence / pass condition |
| --- | --- | --- |
| GUI bootstrap + Profile | Open real source pages; inspect SettingsDialog, Profile and relevant language/layout presets; close/reopen project | Screenshot of page and Profile; effective settings and page dimensions stable |
| Ordinary drawing | On a representative 2+ column page, execute normal drawing, then save/reopen | Screenshot before/after, saved PDIC; marker order and original-source XY, no dropped/duplicated heads |
| OCR drawing | With configured OCR engine, execute OCR-only draw on the **copy**; revisit after cache hit or re-run | OCR candidate/PDIC screenshots and saved artifacts; source XY, cache and review decisions remain consistent |
| Combined drawing | Run combined draw separately from a clean project copy with identical source image and Profile | PDIC and OCR-cache evidence; text-fill cannot move original marker coordinates; no accidental override of manual edits |
| PPP + SECTION | Edit/associate and save one actual polygon, reopen, then switch page and return; inspect SECTION | PPP labels/provenance and source vertices stable; SECTION sort/selection does not swap marker identities |
| Review + save | Edit a real headword in ReviewWindow and main editor, save, switch away/back, reopen app | Edited word stays linked to **its Entry coordinates**, not a reordered index; PDIC/PPP reopen matches expected snapshot |
| Crop/export | Preview word-piece and illustration crops, export an ordinary crop, verify special/associated polygon crop | Capture pixel-dimension, filename, source region and output image screenshot; neither original scan nor headword linkage changes |
| Cancellation/failure | Cancel an overwrite prompt; test missing/unconfigured OCR engine and an intentional invalid page/scope without touching the original | No partially replaced PDIC/PPP, no false success status; explanatory UI errors |
| Final integrity | Compare backups with updated copies for changed/unchanged pages and settings | Source-image hashes unchanged; unexpected PDIC/PPP/SECTION changes absent; no orphan `.tmp` or unresolved transaction marker |

**Do not run destructive draw operations on the only original copy.**
For each mode, start from the same copied source/backup snapshot and note
OCR engine availability and when a mode is skipped. A skipped mode is an
**unmet acceptance criterion**, not a pass.

## Reviewer sign-off

Attach to PR #663: tested OS and version, commit SHA, pseudonymous page
identifiers, evidence screenshots, selected copy-only PDIC/PPP/SECTION diffs,
sample exported PNGs, concise expected-versus-actual table and any failures.
Keep source dictionary pages and sensitive dictionary/project content out of
public commits; the human operator can share evidence through an approved
private review channel.

Only once these manual checks are actually performed and failures resolved
should a reviewer consider marking the PR Ready. Neither architecture CI nor
this synthetic Tk smoke authorizes merge on its own.
