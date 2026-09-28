# Tasks

## 1. Grid overlay and snap

- [x] 1.1 Add grid state (visible, snapEnabled, spacing) to the editor dialog and a toolbar toggle with spacing presets (8/16/32/64); verify the toggle renders and state round-trips through the existing template lint test
- [x] 1.2 Draw the grid on contextTop via the existing after:render hook, viewport-clipped; verify by static render harness or screenshot test that grid lines never appear in canvas.toDataURL export
- [x] 1.3 Apply grid snapping in the object:moving handler after guide selection (guides keep priority) and in object:scaling; verify with unit tests on the rounding helper and a drag simulation in the static harness

## 2. Insert Dynamic Data flow

- [x] 2.1 Add the toolbar button and a stepped panel component (model, field, target) following the existing ShapeMenu pattern; verify panel opens and lists models from get_binding_fields via the existing RPC mocking approach in static tests
- [x] 2.2 Wire token insertion into the active or new text layer and image binding for binary fields; verify inserted tokens match TOKEN_RE and resolve in the existing binding unit tests
- [x] 2.3 Handle the no-binding-model case (offer model selection that persists via the normal template save); verify with a static test that the flow completes once a model is set

## 3. Table element

- [x] 3.1 Implement the table builder in a new dialog module (group of cells from `_tableData`), toolbar entry with rows/cols/width prompt; verify insert creates one layer with correct dimensions in the static harness
- [x] 3.2 Implement edit isolation (double-click ungroup, edit, reassemble) and row/column add-remove preserving cell text; verify with unit tests on the `_tableData` regenerate helper
- [x] 3.3 Add `_tableData` to EXTRA_PROPS and verify save/load round-trip in a static test

## 4. Chart element

- [x] 4.1 Implement `chartSpecToSvg` pure module (vertical bar, horizontal bar, line, area, pie, donut) with a minimal palette; verify with unit tests covering all six types and empty/single-point data
- [x] 4.2 Vendor the chart module into render_service with a parity check script (same pattern as check_fabric_sync.py); verify both copies pass the parity test
- [x] 4.3 Implement chart insertion in the editor (spec editor UI, group generation via loadSVGFromString) and the data table editor panel; verify insert + reopen-edit in the static harness
- [x] 4.4 Implement render-side regeneration: substitute bound cell values in render_core, regenerate SVG, replace the group before loadFromJSON completes; verify with a render_core test using a token-bound fixture
- [x] 4.5 Add `_chartSpec` to EXTRA_PROPS and verify save/load round-trip; verify editor preview mode resolves bound cells via the existing preview snapshot mechanism

## 5. QR element

- [x] 5.1 Vendor the QR generator (file plus LICENSE) into static/lib and add the matching npm package to render_service with a fixture test asserting identical output on both sides
- [x] 5.2 Implement QR insertion with content input (static or token) and `_qrContent` persistence; verify generated code scans in a static test using a decoder fixture
- [x] 5.3 Implement render-side QR regeneration after token substitution; verify with a render_core test that a bound QR encodes the record value

## 6. Integration and docs

- [x] 6.1 Extend the static test suites for all new pure helpers and run all suites plus check_fabric_sync, check_social_image_binding and the new chart parity check; all must pass
- [x] 6.2 Update docs/knowledge/social_image_creator.md with the new elements, grid and Insert Dynamic Data flow
- [ ] 6.3 Manual smoke pass on a staging Odoo: grid toggle and snap, insert token flow, table edit, chart bound render, QR render; verify exported PNGs match editor appearance
