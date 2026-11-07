# Round 49 — Settings Center help catalog is a real physical owner (2026-10-25)

Draft PR #663; based on commit `b91ea46f6c576188650c3367d05a5ccd76ea1885`.

## Scope

Four **complete literal dictionaries** were moved without editing their contents:

- `SETTING_LABELS`
- `SETTING_HELP` (including `REFINEMENT_SETTING_HELP` expansion)
- `SETTING_HELP_IMAGES`
- `CHECK_HELP` (including `REFINEMENT_CHECK_HELP` expansion)

Canonical owner: `ui/settings/help_catalog.py`; the control registry,
field definitions, checks/groups, choices, units and spin rules remain in
`ui/settings/schema.py`.

`schema.py` keeps direct aliases pointing to the **same mutable dictionary
objects**, so the public `schema` and `SettingsDialog` class properties, ordering,
text, keys and any existing runtime extension remain unchanged. No import of
Tk or `app.py` was introduced. No settings/default changes, OCR behavior,
Profile logic, project files, PDIC, PPP or SECTION changes.

The static `audit_settings_runtime.schema_help_keys()` must now inspect the
actual `help_catalog.py` AST, rather than returning false negatives after
the relocation; the field/group AST remains in `schema.py`.

Regression: `tests/test_issue562_settings_help_catalog_round49_20261025.py`
plus existing Settings/UI/audit suites. Full exact-head CI and OCR smoke required.
Manual scanned-page UI/Profile/ordinary/OCR/combined and export/save/reopen
parity remains outstanding. Keep PR #663 Draft and unmerged.
