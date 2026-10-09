## Problem and scope
- What user-visible bug or feature is addressed?
- What is expressly **out of scope**?

## Ownership and architecture
- [ ] Traced affected call chain and identified the single source of truth.
- [ ] Logic is in a focused owner (service/controller/helper), not accumulated in `app.py`.
- [ ] No new GUI-shell imports from lower-level modules, runtime patching, global hooks, or compatibility facade copies.
- [ ] Existing architecture ratchets pass without loosening baselines.
- [ ] Persisted formats, setting migrations, section/Entry identity and external callers are preserved or deliberately migrated.

## Verification
- [ ] Reproducing regression (bug) / behavior tests (feature) added.
- [ ] Negative/edge cases and save/reopen round-trip covered as appropriate.
- [ ] Changed GUI wiring tested or manually exercised; note what remains untested.
- [ ] `scripts/architecture_guard.py` and `scripts/change_architecture_guard.py` passed.
- [ ] Windows, Linux, macOS CI passed.

## Risk and rollback
What could regress (e.g. navigation, FocusOut/autosave, section order, OCR, zoom, crop/export)? How can the change be reverted safely?
