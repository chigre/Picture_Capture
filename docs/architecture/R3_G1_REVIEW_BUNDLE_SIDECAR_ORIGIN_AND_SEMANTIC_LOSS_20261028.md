# G1 / #503: ReviewWindow cached-source ownership and lossless human sidecar (2026-10-28)

## Reproducible data loss

`snapshot_review` correctly froze the current PDIC and simplified
sidecar bytes, but did not prove that `review._simplified_page_records`
had been loaded *from those particular bytes*. If another proofreader
updated the sidecar between ReviewWindow's initial cache load and
`capture_review_before`, the disk snapshot could contain the **newer**
manual text while the UI supplied **older** cached rows. Existing
`_snapshot_sources_match` rechecks all passed and the paired writer
silently overwrote the foreign correction.

Separately, the display-oriented `read_records` drops duplicate coordinate
rows and unknown fields and tolerates malformed records. The paired writer
and one-sidecar guarded writer could serialize that normalized cache to
disk even when the source bytes contained previously saved human data
that was not represented in it. Exact-byte freshness alone is insufficient.

## Owner boundary

The single paired persistence owner
`proofreading/review_bundle.commit_review_bundle` first acquires the UI
cache, requires its frozen `_r3_simplified_source_bytes` path and bytes
to agree exactly with the `SavedSnapshot.simplified_bytes` for the
current page, and rechecks all read-only provenance before any
canonical file mutation. A missing pin is a refusal rather than implicit
authorization to use old cached rows. Successful bundle commits
still advance the source pin to the new verified bytes.

`proofreading/simplified_review.validate_source_for_rewrite` now provides
one strict, narrowly scoped lossless-origin contract shared by this
paired writer and the existing `guarded_write_records`. It accepts a
missing sidecar or a well-formed `format_version=1` standard document;
rejects duplicated JSON members, NaN, unknown top/entry members,
missing members, noninteger or boolean coordinates, nonstring text,
nonboolean manual ownership, duplicate source X/Y, or wrong page.
These conditions can otherwise drop or conflate unowned manual data on
canonical serialization. It does **not** alter the permissive display
reader or migrate unknown user records.

## Failure and normal-path evidence

`tests/test_b3_review_bundle_save_20261017.py` adds a byte-level
failure matrix for third-party same-row edits, other-row additions,
and deletion **before** late disk snapshot; ambiguous sidecar variants
are rejected without PDIC/sidecar publication by both paired and
independent safe writers; missing source pin is quarantined; a healthy
existing human sidecar commits pending edits, preserves the manual text
and advances pinned bytes.

The UI/PDIC original image X/Y, candidate_id, manual_selection,
PPP/SECTION, default OCR quality policies, and recovery marker formats
are not changed. Optimistic provenance and R3 O_EXCL journals are
**not** OS atomic CAS or power-loss durable cross-file transactions.
Real Windows human dictionary E3 (candidate, checkbox, 20× Undo/Redo,
FocusOut, reopen, PDIC/PPP/SECTION, source crop) and R2 #483 W1–W11
remain OPEN / NOT PERFORMED. Only Draft PR #663 remains active.
