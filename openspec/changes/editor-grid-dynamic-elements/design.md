# Design: editor-grid-dynamic-elements

## Context

The editor is an OWL dialog (social_image_creator) on Fabric.js 6.9.1, version-locked to the Node render service in render_service. Overlay drawing already has an established mechanism: guides and distance labels are painted on `contextTop` and hooked to `after:render`, which never enters exported PNG/SVG output. Data binding already has a full contract: template `model_id`, `get_binding_fields`, `{{field}}` tokens with pipes, `_dataBinding` on image layers, and token substitution in render_core.mjs before `loadFromJSON`. Custom element state persists via `_`-namespaced properties listed in EXTRA_PROPS with per-object serialization. The vendored fabric bundle in `static/lib/fabric/` sets the pattern for third-party JS: vendor the file plus its LICENSE, keep the render-side counterpart version-compatible.

## Goals / Non-Goals

**Goals:**
- Grid overlay and snap-to-grid that feel native to the existing move/resize flow and export clean.
- An Insert Dynamic Data flow discoverable from the toolbar, built on the existing binding contract.
- Table, chart and QR elements that survive save/load and render correctly server-side, including per-record bindings for chart cells and QR content.

**Non-Goals:**
- Chart types beyond vertical bar, horizontal bar, line, area, pie and donut.
- Chart/table styling depth (no themes, no 3D, no per-cell borders beyond a simple header treatment).
- QR styling beyond size and one foreground color.
- Reusable chart datasets as Odoo models (chart data lives in scene JSON for now).
- Snap during rotate.

## Decisions

### D1: Grid drawn on contextTop, snap applied in the existing move handler

The grid is painted on `contextTop` through the same `after:render` hook as the snap guides, so it can never leak into exports. Snap-to-grid is a separate toggle; when active it runs after the smart-guide candidate selection in the existing `object:moving` handler, so a guide that already won keeps priority and grid rounding only applies when no guide candidate is within threshold. Resize snapping hooks `object:scaling` with the same rounding. Spacing presets: 8, 16, 32, 64 px.

Alternative considered: grid as a background pattern on the lower canvas. Rejected: it would require stripping before every export and complicates the render service, which shares scene JSON.

### D2: Insert Dynamic Data is an in-dialog stepped panel

The flow is a small stepped dropdown panel inside the editor dialog, following the existing ShapeMenu/FontPicker interaction pattern, not a separate Odoo wizard. Steps: model (from `get_binding_fields` metadata; if the template has no `model_id`, step one offers the models and setting one persists through the normal template save), then field, then target: insert token into active/new text layer or bind active image layer.

Alternative considered: standalone wizard in a new dialog. Rejected: leaving the editor breaks the visual feedback loop that makes token insertion understandable.

### D3: Charts are generated from a shared pure data-to-SVG module

A chart element stores a `_chartSpec` custom property `{type, categories, series, options}` and its visible objects are a fabric group generated from a pure function `chartSpecToSvg(spec)` that returns SVG markup. The editor converts the SVG to fabric objects via the existing `loadSVGFromString` path; render_service ships a copy of the same pure module, substitutes bound cell values, regenerates the SVG and loads it the same way. This mirrors the established parity convention (TOKEN_RE, computeCoverFit) and is enforced the same way: a parity check in the static test suite plus a check script comparing the two copies, so drift fails the build rather than corrupting output.

For record-bound cells, substitution happens before generation on both sides (editor preview uses the existing preview snapshot mechanism; render uses render_core). This means chart geometry always reflects the resolved data.

Alternative considered: hand-placed fabric primitives with baked geometry. Rejected: bound cells could not re-layout. Considered: a full chart library. Rejected: bundle weight and a second implementation to keep in sync server-side.

### D4: Tables are fabric groups backed by a `_tableData` property

A table element is a group of cell rectangles and text objects, regenerated from a `_tableData` property `{rows, cols, widths, cells}` whenever structure changes (insert, add/remove row/column), preserving existing cell text. Double-click enters an edit-isolation mode: the group is temporarily ungrouped for text editing and reassembled on exit, the same lifecycle as the existing ungroup/regroup code path.

### D5: QR via vendored generator on both sides

The editor vendors a small MIT-licensed QR generator (single file in `static/lib/`, file plus LICENSE committed, same pattern as fabric). render_service adds the matching npm package. A QR element stores `_qrContent`; the rendered code is regenerated from content at render time, which keeps static and bound content on one code path. Tokens in content are substituted first, per D3.

### D6: All new state via EXTRA_PROPS, no schema change

`_tableData`, `_chartSpec` and `_qrContent` are plain-data properties with no `type` key, added to EXTRA_PROPS, so scenes round-trip through the existing loadFromJSON flow with no migration. Old scenes without the new properties load unchanged.

## Risks / Trade-offs

- [Chart editor/render divergence] → shared pure module plus parity test and check script; any drift fails CI the way check_fabric_sync does today.
- [Table group editing feels fiddly] → isolation mode reuses the proven ungroup/regroup path; if feedback says otherwise, cells can become standalone snap-aligned objects in a follow-up.
- [Grid redraw cost on large canvases] → draw only the visible viewport region, spacing floor of 8 px.
- [Vendored QR lib maintenance] → single stable file, MIT, pinned like the fabric bundle; render side uses the npm equivalent and a fixture test asserts identical matrix output for sample content.
- [Token substitution in chart cells producing non-numeric values] → parse failure maps to 0 per spec; render never aborts.

## Migration Plan

Additive and backward compatible: new properties are optional, old scenes load unchanged. Deploy order: render_service first (new modules and npm dependency), then the Odoo module assets. Rollback: revert the module; scenes containing the new elements from newer sessions would show as missing layers only if a rollback happens after users saved new element types, which is acceptable during the feature window.

## Open Questions

None blocking. Chart color palettes and default spacing presets are product-tuning details that can change without touching specs or tasks.
