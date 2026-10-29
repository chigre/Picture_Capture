# PC-CQ v1.3.0: real Windows R3 E3 local evidence runbook (2026-10-30)

Status: OPEN / NOT PERFORMED. This runbook and tool are NOT human E3.
PR #663 remains Draft/Open/Unmerged. Issue #503 E3 and issue #483
W1-W11 remain OPEN / NOT PERFORMED. Never upload private dictionary
images, extracted contents or local evidence into a public repository.

## Prepare an authorized Windows test copy

On the actual Windows PC choose an authorized real scanned dictionary
and preserve an independently backed-up original. Record the Windows
build, application version, project storage mode and the complete Git
commit SHA from git rev-parse HEAD. Confirm the executable under test
was built from that SHA. Resolve the ACTUAL six artifact paths for
the chosen source image, PDIC, PPP, SECTION, manual_selection and
simplified_review. Paths differ in legacy and managed-v2 projects.
Pass expected paths even when sidecar files do not yet exist.

The Python standard-library helper scripts/r3_e3_local_evidence.py
reads source files without modifying or copying them. It captures
only six labels, existence, byte length and SHA-256. It refuses
symlink inputs, existing output names and any output path colliding
with one of the six input file slots (including not-yet-created
sidecars), records the commit revision,
does NOT record the original paths or dictionary words, and cannot
declare acceptance. Its JSON outputs must be kept LOCAL outside the
repository and must not be auto-uploaded.

## Sample PowerShell procedure

Replace ALL six placeholder paths below with the active project's
actual file locations. Do NOT assume the sample SECTION path is the
current project's canonical path.

    $REV = (git rev-parse HEAD).Trim()
    $EVID = "D:\Private-E3-Evidence"
    New-Item -ItemType Directory -Force -Path $EVID | Out-Null
    $SOURCES = @(
        "--image", "D:\Authorized\scan\001.png",
        "--pdic", "D:\Authorized\scan\001.pdic",
        "--ppp", "D:\Authorized\scan\001.ppp",
        "--section", "D:\Authorized\section\001.json",
        "--manual", "D:\Authorized\QT\PaddleOCR\001_manual_selection.json",
        "--simplified", "D:\Authorized\QT\Simplified\001.json"
    )

    python scripts/r3_e3_local_evidence.py capture --stage before --revision $REV @SOURCES --output "$EVID\before.json"
    # Perform the human steps and save in the running application.
    python scripts/r3_e3_local_evidence.py capture --stage after --revision $REV @SOURCES --output "$EVID\after.json"
    # Quit the app entirely and reopen the same page; do not alter the source.
    python scripts/r3_e3_local_evidence.py capture --stage reopen --revision $REV @SOURCES --output "$EVID\reopen.json"
    python scripts/r3_e3_local_evidence.py compare --before "$EVID\before.json" --after "$EVID\after.json" --reopen "$EVID\reopen.json" --output "$EVID\comparison.json"

Comparison exit 0 means input manifests were valid, original-image
hashes matched and after-reopen file hashes matched: NOT human PASS.
Exit 1 indicates source-image or after-reopen byte instability. Exit 2
indicates an invalid input / report / access error. All require a human
worksheet. The comparison cannot establish correct Chinese text,
original image integer X/Y, correct crops, OCR provenance or valid
Undo/Redo history.

## Actual E3 manual action checklist

| Step | Real operator action and verification |
|---|---|
| E3-01 | Record SHA, OS/build, authorized source and initial six-artifact hashes; verify image remains unchanged |
| E3-02 | Chinese IME composition, paste, Return, FocusOut and autosave with actual Tk inputs; verify saved words |
| E3-03 | Candidate checkboxes and unique candidate IDs; verify saved manual_selection, PDIC and simplified sidecar |
| E3-04 | Rename and delete normal and candidate-owned entries; verify no wrong-XY or stale owner |
| E3-05 | Make 20 individually SAVED edits; Undo 20 and Redo 20 in one open session; inspect each saved revision |
| E3-06 | Undo then save a new edit, confirm Redo branch is cleared; an unsaved checkbox must not enter Undo history |
| E3-07 | In a backed-up copy inject a controlled write error / incomplete R3 journal; verify quarantine and safe recovery |
| E3-08 | Change page and SECTION/column, close the app completely, reopen, verify byte-exact persisted values |
| E3-09 | Manually compare original-source integer X/Y and crop boundaries against the true source pixels at zoom/rotation |
| E3-10 | Inspect PPP/SECTION boundary, polygon edit and reopen; unrelated sidecars must be unmodified |
| E3-11 | Complete #483's own W1-W11 worksheet separately, not by inheriting these results |

For each item, keep a LOCAL worksheet with: item ID, revision,
Windows version, source-page reference, timestamp, operator action,
expected, observed, integer source X/Y, crop checked, evidence ID,
manual outcome PASS/FAIL/BLOCKED, and notes. Screenshots of genuine
scans stay in the authorized local directory. An unmet prerequisite
is BLOCKED, not PASS. Undo history is in-session; do not expect
20 Undo steps to remain after restart.

## Gate

These tests are a way to COLLECT evidence. They do not perform the
actual actions. Until a Windows operator completes and reviews all
required observations, label R3 E3 NOT PERFORMED and #483 W1-W11
NOT PERFORMED even if all GitHub CI is green. This helper does not
provide cross-process OS CAS, a filesystem lock or multi-file
power-loss atomicity.

## Failed command output and privacy

When a file cannot be opened or a report is malformed, the tool exits
with code 2 and deliberately prints only the **exception class** and
a numeric OS error code (where available). It does not echo the
operating-system exception's original string, which may otherwise
include an absolute dictionary/project path in terminal logs. Use
the original locally issued command to identify the failing slot.

**Important:** PowerShell command history, screenshots, shell transcripts
and user-created diagnostics may themselves include the six input
paths. Do not upload these to GitHub or paste them into public issues.
The SHA-256 of a private scan can also serve as a file identifier:
even JSON hash-only manifests remain sensitive local evidence and
require independent permission before sharing.
