# Phase 13A — Explicit Layout Composition API design

Status: **design/characterization only; no production behavior change**

Base: `main@388eb6965f267f3e34e14744b9563b2ff93e160b`

Phase 12 closed the small/bounded ownership seams. The largest remaining
architecture debt is no longer a local installer; it is the composed Layout
runtime formed by two ordered Page Design hook installers plus Profile/policy
and Page Understanding finalizers.

This document defines the target ownership model and a staged migration that
preserves raw Page Design behavior while removing process-global mutation from
product composition.

## Current behavior that must be preserved

### Three product consumers

1. **GUI/full Page Understanding**
   - GUI startup installs robust line starts, then physical-indent inference.
   - ordinary/full detection also prepares the same order idempotently inside
     `processing._ensure_layout_runtime()`.
   - the resulting process-global Page Design hooks feed policy, Layout Core and
     full Page Understanding.

2. **ordinary/spawn detection**
   - spawn workers do not rely on GUI startup;
   - `processing._ensure_layout_runtime()` explicitly prepares the same
     robust -> physical chain before Layout/Page Understanding work.

3. **physical-only unlined-row escalation**
   - `unlined_physical_rows_resolver` installs the same chain independently;
   - it intentionally stops at physical policy/layout and does not need sampled
     symbols, large-head evidence, or full semantic Page Understanding.

### Ordered primitive hook composition

The installed product order is:

1. raw `dictionary_page_design._line_feature`;
2. robust-line-start wrapper around that raw feature;
3. physical line feature around the already-robust feature.

Physical-indent installation also replaces:
- `_line_runs` -> `projection_line_runs`;
- `_indent_modes` -> `physical_indent_modes`;
- `_assign_indent_semantics` -> `assign_binary_roles`.

The order is observable. `physical_line_feature(...)` currently delegates via
`_BASE_LINE_FEATURE`, which is captured only after robust-line-start
installation.

### Higher-level composed behavior

Physical-indent installation additionally:
- installs Project Profile anchoring around
  `dictionary_page_layout_policy.resolve_page_layout_policy`;
- wraps `dictionary_page_layout_policy.infer_dictionary_page_layout` so final
  physical roles are normalized;
- wraps `page_understanding.understand_page` so final roles are normalized
  there as well.

Raw `resolve_page_layout_policy(...)` is a real lower-level contract. Existing
tests intentionally observe unanchored per-page estimates for auto-selected
fields. Profile anchoring therefore cannot simply be moved into the raw policy
function.

## Why a top-level service wrapper alone is insufficient

Several internal modules directly read the mutable Page Design hook names:
- `dictionary_page_design`;
- `dictionary_page_design_refined` guard-band recovery;
- `dictionary_page_layout_policy`;
- `page_x_registration`;
- `layout_column_drift`.

A new top-level `infer_layout()` wrapper that leaves these internal reads
unchanged would only hide the same global dependency behind another facade.

No repository tests currently monkeypatch the four private primitive hook names
(`_line_runs`, `_line_feature`, `_indent_modes`,
`_assign_indent_semantics`). That makes explicit dependency injection feasible,
but raw direct Page Design tests remain a compatibility contract and must keep
their current default behavior.

## Target model

Use two explicit layers.

### 1. LayoutPrimitiveOps

Introduce one immutable composition object containing the four primitive
operations consumed by Page Design internals:

- `line_runs`;
- `line_feature`;
- `indent_modes`;
- `assign_indent_semantics`.

The target raw/default object must point to the native
`dictionary_page_design` implementations and remain the long-term default for
direct raw calls.

During the **13B transition only**, however, `ops=None` must preserve today's
installer semantics by snapshotting the four *currently bound* Page Design hook
callables at call time. That means an unprepared/raw process still sees raw
behavior, while a process already prepared by the historical installers still
sees the installed physical behavior. This temporary compatibility bridge is
required so 13B can be plumbing-only. It must disappear only after all product
entry paths pass explicit physical ops.

A physical/composed object must encode the historical order explicitly:
- `line_runs = projection_line_runs`;
- `line_feature = physical(robust(raw_line_feature))`;
- `indent_modes = physical_indent_modes`;
- `assign_indent_semantics = assign_binary_roles`.

The physical line-feature composition must not rely on a process-global
`_BASE_LINE_FEATURE`. Prefer a closure/factory that receives its inner feature
explicitly.

### 2. LayoutComposition service

The higher-level service owns product composition rather than raw primitives.

It should expose explicit operations for at least:
- composed policy/layout inference;
- full Page Understanding;
- physical-only policy/layout inference for unlined QA.

Responsibilities:
- select `LayoutPrimitiveOps`;
- apply Profile anchoring only for composed product policy;
- apply physical role normalization at the same historical boundaries;
- keep raw policy/page-design functions available without product composition.

The service should not own OCR execution, symbol detection, PDIC I/O, GUI state,
or LayoutRows persistence. Those remain separate layers.

## Required propagation points

The primitive ops object must be threaded through every path that currently
reads the mutable hook globals.

Minimum propagation set:
- `dictionary_page_design.infer_dictionary_page_layout(...)`;
- refined guard-band row/feature recovery in
  `dictionary_page_design_refined`;
- `dictionary_page_layout_policy.resolve_page_layout_policy(...)`;
- `dictionary_page_layout_policy.infer_dictionary_page_layout(...)`;
- `page_x_registration.register_page_manual_x(...)` and its line-family
  candidate helper;
- `layout_column_drift.finalize_layout_column_drift(...)` /
  `remeasure_layout_indents_from_ink(...)`.

Default arguments must preserve raw behavior. Product composition must pass the
physical ops explicitly.

## Staged migration

### Phase 13B — introduce primitive ops without behavior change

Goal: dependency plumbing only.

- define the immutable ops type and an explicit `RAW_LAYOUT_OPS` instance;
- add a temporary `current_layout_ops()` compatibility snapshot that captures
  the four currently-bound Page Design hook callables;
- add optional ops parameters through the minimum propagation set;
- while 13B is active, resolve `ops=None` through
  `current_layout_ops()`, not directly through `RAW_LAYOUT_OPS`;
- replace downstream internal reads of the four global hook names with the
  resolved ops object;
- preserve both raw/unprepared and installer-prepared behavior exactly;
- keep both historical installers active;
- extend any existing compatibility wrapper signatures only as needed to pass
  `ops` through unchanged (notably the Profile-anchor wrapper around
  `resolve_page_layout_policy`); this is dependency plumbing, not a change in
  anchoring/finalization behavior;
- do not route product consumers to the new explicit physical ops yet.

Gate:
- direct raw Page Design tests remain behavior-equivalent;
- a focused transition test proves `ops=None` observes a temporarily rebound
  legacy hook while `ops=RAW_LAYOUT_OPS` remains raw;
- policy/raw tests remain unchanged;
- full existing suite passes;
- architecture guard forbids new consumers of the mutable hook names outside the
  known compatibility modules.

The temporary `current_layout_ops()` bridge is migration scaffolding, not the
target architecture. Phase 13E must delete it (or reduce it to an explicitly
named compatibility-only path) after normal product consumers pass explicit
physical ops.

### Phase 13C — explicit physical primitive composition

Goal: encode robust -> physical primitive order without global capture.

- add explicit robust line-feature composition;
- add explicit physical line-feature composition around the robust feature;
- construct the physical ops object;
- route one narrow internal characterization/test path through physical ops and
  prove parity with the currently installed runtime;
- do not yet remove installers.

Gate:
- parity tests compare installed-runtime output vs explicit physical-ops output
  for row runs, first-X values, indent modes and assigned roles;
- oversized-band recovery and slant-normalized indent tests remain unchanged.

### Phase 13D — explicit composed policy boundary

Goal: remove Profile/policy mutation from the product path.

- create an explicit composed policy function/service that calls raw policy with
  physical ops;
- apply `anchor_resolved_layout_to_profile(...)` only in that composed
  boundary;
- normalize physical roles at the same point currently provided by the policy
  wrapper;
- route physical-only unlined escalation through this composed physical-policy
  surface;
- keep raw `resolve_page_layout_policy(...)` semantics unchanged.

Gate:
- raw policy tests continue to observe unanchored estimates;
- composed policy parity matches the installed runtime;
- unlined resolver source/behavior remains physical-only.

### Phase 13E — explicit full Page Understanding composition

Goal: remove Page Understanding mutation and retire the installers from normal
product execution.

- make full Page Understanding explicitly consume composed policy/layout;
- preserve the current final role-normalization timing;
- route ordinary/spawn detection and GUI/full understanding through the explicit
  service;
- remove installer calls from GUI, processing and unlined resolver only after
  parity is proven;
- retain installer names as compatibility shims only if needed for historical
  direct callers.

Gate:
- GUI, spawn and unlined consumers all use explicit service surfaces;
- no normal product path depends on process-global Page Design hook mutation;
- architecture guard rejects reintroduction of those assignments/install calls;
- all current Layout, Page Understanding, worker, visualization and QA tests pass
  on all supported CI platforms.

## Cache and side-effect invariants

The migration must not change:
- `layout_core_understanding` cache keys or cache-hit publication behavior;
- explicit `capture_layout_rows(...)` scope semantics;
- Layout visualization snapshot cache identity;
- raw policy diagnostics/estimate reporting;
- Page Understanding symbol/large-head evidence timing;
- unlined QA cache -> fast projection -> physical detector escalation order.

Composition objects/services must be stateless or effectively immutable. Do not
replace process-global mutation with hidden mutable singleton state.

## Compatibility invariants

Preserve:
- raw direct `dictionary_page_design.infer_dictionary_page_layout(...)`;
- raw `resolve_page_layout_policy(...)`;
- public/refined detector forwarding;
- Phase 9 facade compatibility;
- existing file formats and persisted settings;
- existing reason/diagnostic text unless a later phase explicitly updates its
  contract.

Do not combine this migration with:
- PDIC raw/composed I/O redesign;
- OCR-boundary runner redesign;
- Phase 8 OCR performance optimization;
- unrelated GUI refactoring.

## Phase 13A decision

A staged explicit composition API is feasible.

The first production slice should be **Phase 13B: introduce and propagate
LayoutPrimitiveOps while leaving every current installer and product entry path
active**. This is intentionally plumbing-only and should produce no observable
behavior change.

Only after 13B parity is green should the project construct explicit physical
ops and begin removing process-global composition.
