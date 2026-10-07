# Picture Capture Refactor Status

This is the crash-recovery checkpoint for the modular-architecture refactor. GitHub live state is authoritative: before any production write, revalidate `main`, open PRs, relevant callers/import order, and current tests.

## Current phase
**Phase 5 — runtime-patch cleanup. Phase 5A through Phase 5Z are complete.**

Phase 4 controller decomposition is complete. Phase 5 is progressively replacing dynamic installer/runtime ownership with explicit/static ownership while preserving behavior and keeping each slice independently reversible and reviewable.

Controllers on `main`: Canvas, Crop, Detection, Export, Headword, Illustration, Page, Project, Review, Session.

## Latest architecture checkpoint — Phase 5Z
- production PR: **#285 — make Page Understanding illustration masking static**
- production base: `66bd321800120f5b7fb01009fc0dfe365d54115a`
- clean production head: `7b53054148517bf6651cefa53c026e8732149a77`
- validated production tree: `5b6951b4ef3946ef6761957c21d9fd3b40d40c6d`
- merge commit / current architecture main: `805e5c9814cbfa5d4a53f171d9c3b1c3dea67ae1`
- merge tree: `5b6951b4ef3946ef6761957c21d9fd3b40d40c6d`

### Static Page Understanding illustration masking
Phase 5Z removed the Page Understanding callable-replacement responsibility from `layout_illustration_mask_runtime.py`.

The pure masking policy and diagnostics now live in ordinary non-runtime `layout_illustration_mask.py`:
- `IllustrationMaskStats`;
- size/headlike guard policy;
- `mask_large_illustrations_for_layout(...)`;
- historical `layout.reason` diagnostic formatting.

`processing._understand_page_current(...)` now statically owns optional illustration-mask preprocessing. The preserved contract is:
1. disabled masking passes the original image object through unchanged;
2. enabled masking uses the shared static detector/policy;
3. any mask/filter exception fails open to the original image;
4. both `layout_only=True` and full Page Understanding routes preserve their existing page index/section arguments;
5. mask diagnostics remain appended to `layout.reason` with the same fields/format;
6. a disposable masked image is closed only when it is a separate object, including when downstream understanding raises;
7. the historical outer failure contract still returns `None`.

Core composition no longer imports/calls `install_layout_illustration_mask_runtime(...)`, and `_pc_layout_illustration_mask_installed` no longer exists. Training-export Page Understanding now imports the same static masking helper directly.

The runtime file is intentionally **not yet deleted**. After Phase 5Z it owns only the final GUI compatibility seam:
- insertion of the `layout_mask_illustrations` checkbox/label/help into Settings Center;
- inclusion of that setting in `layout_visualization_ui._layout_cache_key`.

### Phase 5Z isolated validation
Temporary migration/validation assets were removed before publication.

Two early validation failures were tooling-only and did not publish production code:
- the first temporary workflow embedded large source text directly in YAML and failed before jobs were created;
- the next fail-closed diff check did not initially account for the newly created untracked module;
- after the diff gate was corrected, focused validation exposed an escaping bug in the temporary migration script's generated Chinese help string. This was corrected in the migration tool; it was not an application-design failure.

Final isolated validation:
- exact intended production/test diff: **7 paths, passed**;
- no production reference to `install_layout_illustration_mask_runtime` or `_pc_layout_illustration_mask_installed`;
- architecture guard: passed;
- focused regressions: **39 passed**;
- full pytest suite: **1296 passed, 1 existing warning**;
- compileall: passed;
- Ruff F821: passed.

The temporary workflow and migration script were deleted. The exact validated production tree `5b6951b4ef3946ef6761957c21d9fd3b40d40c6d` was then re-anchored to the live main base as one clean production commit `7b53054148517bf6651cefa53c026e8732149a77`.

### Phase 5Z PR gate
Fixed-head PR #285:
- CI run **2115** Ubuntu/Windows/macOS: passed, including platform GUI smoke, compatibility runner, compile, F821, and wheel build;
- CodeQL run **2096** Actions/Python: passed;
- Advanced Security run **1850**: passed;
- PR remained mergeable with one commit and seven changed files;
- no comments, review threads, review submissions, or objections.

PR #285 was merged with fixed-head protection on `7b53054148517bf6651cefa53c026e8732149a77`.

### Phase 5Z post-merge verification
On `main@805e5c9814cbfa5d4a53f171d9c3b1c3dea67ae1`:
- merge tree exactly matched validated production tree `5b6951b4ef3946ef6761957c21d9fd3b40d40c6d`;
- push CI run **2116** passed on Ubuntu, Windows, and macOS;
- GUI smoke passed on all applicable platforms;
- compatibility runner / compile / F821 / wheel passed on all three platforms;
- CodeQL run **2097** Actions: passed;
- CodeQL run **2097** Python: passed.

No post-merge behavior, packaging, or security regression was observed.

## Completed Phase 5 ownership milestones
- Phase 5L: Windows NVIDIA/Paddle DLL preparation became ordinary call-time `windows_gpu.py` ownership.
- Phase 5M: Windows/Tk supplementary Unicode repair moved into explicit `PictureCaptureApp` lifecycle ownership.
- Phase 5N: one-sided overlay geometry moved to non-runtime `overlay_line_anchor.py`.
- Phase 5O: guide/headword line opacity became native settings + static UI/rendering ownership.
- Phase 5P: illustration fill opacity became native settings + static UI/rendering ownership.
- Phase 5Q: long-band logical row recovery became static.
- Phase 5R: character-height fallback became static.
- Phase 5S: column-drift remeasurement became static.
- Phase 5T: identity-only spawn-layout wrapper was removed.
- Phase 5U: spawn-safe ordinary worker became static `processing.detect_entries_job`.
- Phase 5V: guarded oversized-head detection and row/fusion authorization became static.
- Phase 5W: unlined physical-row fast worker became static.
- Phase 5X: Layout-entry classification and existing-marker crop/OCR became static processing ownership.
- Phase 5Y: illustration-mask setting became native and the shared PPP/Layout detector became static `processing_core` ownership.
- Phase 5Z: illustration masking policy/diagnostics and Page Understanding preprocessing became static; core callable replacement was removed.

Earlier Phase 5A–5K details remain available in checkpoint history; they are complete and are not reopened by this checkpoint.

## Current explicit illustration-mask ownership
- setting schema/default/persistence: native `AppSettings.layout_mask_illustrations`;
- detector: static `processing_core.detect_illustration_regions_from_image(...)`;
- mask policy and diagnostics: non-runtime `layout_illustration_mask.py`;
- Page Understanding preprocessing/lifetime/fail-open behavior: static `processing._understand_page_current(...)`;
- training-export masking: static `layout_illustration_mask.mask_large_illustrations_for_layout(...)`;
- remaining compatibility debt: `layout_illustration_mask_runtime.py` only mutates Settings Center metadata and the Layout visualization cache key.

## Recommended next slice — Phase 5AA
**Staticize the final SettingsDialog/cache-key illustration-mask seam and delete `layout_illustration_mask_runtime.py`.**

Fresh read-only inspection after Phase 5Z shows that the final runtime file has no processing/detector ownership left. Its remaining behavior is small and separable.

### Safest Phase 5AA architecture
- add the `layout_mask_illustrations` checkbox directly to static Settings Center metadata in `ui/settings/schema.py`, preserving its current position immediately after `ordinary_auto_layout`;
- preserve the exact current Chinese label and dedicated help text;
- add the setting directly to `layout_visualization_ui._layout_cache_key(app)`, preserving the historical wrapper's tuple contribution: the literal setting name followed by its boolean value;
- remove `install_layout_illustration_mask_ui(app_module)` from GUI bootstrap; generic settings-help composition must still see the checkbox without installer ordering;
- delete `layout_illustration_mask_runtime.py` only after all production/test consumers are migrated;
- ratchet the architecture guard so the deleted runtime file is no longer permitted debt;
- keep `layout_illustration_mask.py`, detector logic, masking thresholds, settings persistence, Page Understanding behavior, training export, PPP format, and GUI appearance/wording otherwise unchanged.

### Required Phase 5AA characterization
Before publication, prove at minimum:
- bare/static `SettingsDialog` metadata already contains the checkbox in the same relative position without GUI bootstrap mutation;
- `SETTING_LABELS` and `SETTING_HELP` contain the same dedicated content;
- generic Settings Center help sees the control with no ordering dependency on an illustration installer;
- `_layout_cache_key` changes when only `layout_mask_illustrations` changes and preserves the previous tuple shape contribution;
- GUI composition no longer imports/calls the illustration runtime installer;
- zero production references to `layout_illustration_mask_runtime` remain and the file is deleted;
- architecture guard ratchets the removed runtime debt;
- full cross-platform CI, GUI smoke, compatibility runner, compile, F821, wheel, CodeQL, and security gates remain green.

Any checkbox-order/help-text/cache-key semantic change is a stop condition rather than a reason to broaden the slice.

## Remaining runtime seams after Phase 5Z
For the illustration-mask feature, exactly one compatibility seam remains:
- `layout_illustration_mask_runtime.py` — SettingsDialog metadata + Layout visualization cache-key mutation only.

Phase 5AA should remove this final illustration-mask runtime file. Do not mix unrelated remaining Phase 5 compatibility installers into that deletion.

## Standing continuation authorization
The user explicitly authorized continued Phase 5 work along the recommended architecture path without pausing at normal ownership decision points. Continue automatically after each successful checkpoint and fresh live-state revalidation.

Stop production writes only for genuine anomalies: unexplained behavior/test/CI failure, file-format/archive/public-API change outside the approved slice, merge conflict/concurrent architecture work, checkpoint mismatch, materially large cross-core redesign, or irreversible compatibility deletion whose impact cannot be established.
