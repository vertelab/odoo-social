# Proposal: creator-render-parity

## Why

Two behaviors from render-engine-os were never ported, and the Odoo editor's adaptation of them introduced two live bugs. Bound text carrying markdown markers (`**bold**`, `*italic*`) renders the markers literally because the render service never converts them to character styles. And the editor bakes text case transform and overflow autofit into the scene at capture time, which uppercases the insides of `{{tokens}}` so they stop resolving, and sizes autofit against placeholder text so longer bound values overflow. This change ports both behaviors to render time where the source applies them.

## What Changes

- **Inline markdown to character styles**: after token substitution, the render service parses `**bold**` and `*italic*` segments in each text object into fabric per-character styles, preserving existing character styles for other attributes and leaving unmatched markers literal. The editor preview resolves markdown identically, keeping the established editor/render mirror convention.
- **Text transform at render time**: `_textTransform` (upper, lower, title) is applied to the resolved text in the render service after substitution. The editor stops transforming token text at capture, so `{{name}}` keeps resolving; the transform still previews in the editor through the same preview path.
- **Overflow autofit at render time**: when `_overflow` is autofit, the render service recomputes the font size against the resolved text with a real text measurement, using the same binary-search algorithm the editor already has, with a minimum font size floor. The editor's edit-time autofit remains as a convenience for static text but no longer dictates bound output.

No scene format change: both properties already persist via EXTRA_PROPS, and scenes saved before this change load unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `render-pipeline`: bound text supports inline markdown character styles; text transform and overflow autofit apply at render time on resolved values.
- `template-editor`: the editor defers case transform and autofit to render instead of baking them into the persisted scene.

## Impact

- **render_service**: render_core.mjs gains markdown parsing, transform application and autofit recomputation with an injectable measure function; new pure tests cover both plus parity fixtures. server.mjs passes a node-canvas measurement into the binding pipeline.
- **social_image_creator**: editor capture stops mutating token text (dialog js), inspector copy notes render-time application, the preview path mirrors markdown/transform/autofit, utils gains the mirrored pure helpers, static tests cover capture behavior and parity.
- **docs/knowledge/social_image_creator.md** updated for the render-time semantics.
