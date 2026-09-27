# Proposal: editor-grid-dynamic-elements

## Why

The template editor in social_image_creator is the module's core workspace, and the first community feedback round produced three gaps that block real template work. First, precise layout is hard: there is no grid, and the existing smart guides only help while another object is nearby. Second, data binding is powerful but nearly invisible: the only entry points are small panels deep in the dialog, so users do not discover that a template can render hundreds of personalized images from Odoo records. Third, brand content beyond text, shapes and images is missing: no tables, no charts and no QR codes, which community users expect from a Canva-class editor.

## What Changes

- **Grid**: toggleable grid overlay in the editor canvas, with configurable spacing, optional snap-to-grid for move and resize, and the toggle placed in the toolbar.
- **Insert Dynamic Data**: a toolbar button "Insert Dynamic Data" that opens a focused step-by-step flow: choose the binding model, choose a field, then insert a `{{field}}` text token or bind an image layer, all reusing the existing `model_id` and `get_binding_fields` infrastructure.
- **Tables**: a table element built as a fabric Group of cell objects, with row/column count, header styling and cell text, editable after insertion.
- **Charts**: a chart element backed by an embedded data table. Data cells may be static values or `{{field}}` tokens resolved per record at render time. Chart types at launch: vertical bar, horizontal bar, line, area, pie, donut. The chart renders as vector fabric objects in the editor and as equivalent drawing instructions in the render service, so editor and server output stay consistent.
- **QR codes**: a QR element whose content can be static text/URL or token-bound, rendered as an image layer; a generated QR is baked into the scene at insertion and at render time for bound content.
- No breaking changes to scene JSON: new element types persist through the existing `_`-namespaced custom property convention and `loadFromJSON` round-trips.

## Capabilities

### New Capabilities

None. All behavior extends existing capabilities.

### Modified Capabilities

- `template-editor`: add grid overlay with toolbar toggle and snap-to-grid; add "Insert Dynamic Data" toolbar flow; add table, chart and QR element types with insertion, editing and scene persistence.
- `data-binding`: extend binding application to chart data cells and QR content so templates rendered per record resolve those elements at render time; document the insert flow entry point.

## Impact

- **social_image_creator**: editor dialog JS/XML/SCSS (new toolbar entries, grid drawing, wizard flow, table/chart/QR builders), utils JS (grid math, chart geometry), new shape/element modules, static Node tests.
- **render_service**: chart drawing parity in render_core.mjs or a new module, QR generation for bound content at render time, new static tests. Fabric version lock with the editor bundle is preserved via check_fabric_sync.py.
- **Models**: no new Odoo models required; chart data lives inside scene JSON. If chart data should be reusable across templates, a follow-up change can promote it to a model.
- **Docs**: docs/knowledge/social_image_creator.md updated for new element types; knowledge doc update is mandatory because editor behavior changes module capabilities.
