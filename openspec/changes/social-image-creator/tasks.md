# Tasks: social-image-creator

## 1. Module scaffold and migration from social_marketing

- [x] 1.1 Create `social_image_creator` module skeleton (manifest depending on `social_marketing`, models/views/security/static dirs) and verify it installs on a test DB with `checkmodule` (statically verified: py_compile, pfile sync OK; live install pending test host, no Odoo runtime on this machine)
- [x] 1.2 Migrate `social.image.template` + placeholder model, views, access rules, `res.config.settings` fields from `social_marketing` to `social_image_creator`; remove them from `social_marketing` and verify no stale imports/references remain (`grep -r social.image.template social_marketing/` is empty)
- [x] 1.3 Migrate the Fabric editor OWL field, fabric loader, lib assets and the render wizard into `social_image_creator`; verify the E2E flow in `docs/social-image-editor-test.md` still passes against the new module (code migration done and statically verified; E2E run pending test host)

## 2. Template model: variants, binding model, size presets

- [x] 2.1 Add `model_id` (ir.model) to the template with field-picker support data; verify switching models warns on tokens referencing missing fields (spec: image-templates)
- [x] 2.2 Add `variants` JSONB (name, width, height, scene_json, is_primary) with legacy width/height/scene_json mirroring variant[0]; add duplicate-variant-with-scale; verify add/copy/delete-variant scenarios including refusal to delete the last variant (spec: image-templates)
- [x] 2.3 Create `social.image.size` preset model with data for Open Graph, Facebook, Instagram square/portrait/story, LinkedIn post, X post; verify users can add custom sizes and variant creation offers presets (spec: image-templates)

## 3. Editor: workspace, layers, history

- [x] 3.1 Convert the editor to a full-screen modal action launched from the template form (canvas center, layer panel, properties panel); verify the modal opens on saved records and is disabled on new records (design D4)
- [x] 3.2 Implement layer panel: drag reorder, rename, visibility, lock, duplicate, delete; verify each control changes z-order/render output accordingly (spec: template-editor)
- [x] 3.3 Implement undo/redo (bounded snapshot stack, keyboard shortcuts) and debounced autosave with flush on close; verify undo restores deleted objects and autosave persists after idle (spec: template-editor)

## 4. Editor: objects, typography, effects, alignment

- [x] 4.1 Port object toolbox additions from render-engine-os: corner-radius rect, arrow, path-shape library, parametric shapes, pen tool; verify each object type round-trips through save/reload (spec: template-editor)
- [x] 4.2 Port typography controls: font picker with Google Fonts via CDN plus brand/system fonts, line height, char spacing, alignment, case transform, autofit overflow; verify autofit behaves identically in a server-rendered PNG (spec: template-editor, design D11)
- [x] 4.3 Port effects: gradients, shadows, stroke styles, opacity, image filters, shape-filled-with-image with revert; verify each renders identically server-side (golden-scene parity check, spec: render-pipeline)
- [x] 4.4 Port snapping with guides and smart spacing, align/distribute, group/ungroup with shortcuts; verify snap and align behaviors in the modal editor (spec: template-editor)
- [x] 4.5 Port icon picker (searchable, recolorable SVG) and media/brand-asset pickers scoped to company; verify icons recolor and brand colors appear in pickers (spec: template-editor)

## 5. Data binding

- [x] 5.1 Implement Python binding resolution: scene walk, field collection, dotted-path record read, `{token: value}` payload to render service; verify `{{name}}` and `{{categ_id.name}}` resolve against a chosen record (spec: data-binding)
- [x] 5.2 Add pipe transforms (upper, lower, title, capitalize, trim, chained); verify each transform and chaining in rendered output (spec: data-binding)
- [x] 5.3 Port `_hideIfEmpty` conditional layers and `_required` bindings with abort-and-report behavior; verify empty-value scenarios in render (spec: data-binding)
- [x] 5.4 Port image `_dataBinding` with cover-fit re-fit (verbatim from render-engine-os editor and server fit logic, including clipPath compensation); verify bound product images match editor preview in PNG output (spec: data-binding)
- [x] 5.5 Add live preview mode in the editor with record switcher and token restore; verify preview swaps text/images and restores tokens after (spec: template-editor)

## 6. Render pipeline

- [x] 6.1 Add server-side font registration (registerFont from bundled/uploaded fonts, `/fonts/reload` endpoint); verify a template in a non-system font renders that font in the PNG, not DejaVu (design D6)
- [x] 6.2 Implement render-at-creation vs render-at-publish options on the wizard/flow; verify approval sees the image when rendering at creation and that a failed render blocks publish with an error flag (spec: render-pipeline)
- [x] 6.3 Keep Fabric version lock between editor and render service; verify `render_service/package.json` and the editor lib report the same Fabric version in CI or a check script (design D4 risks)
- [x] 6.4 Verify security scenarios: XML-escaped binding values in SVG output, 401 on bad token, clear error when service URL unset (spec: render-pipeline)

## 7. Wizard and bulk creation

- [x] 7.1 Rework the single-post wizard: template picker (filtered by binding model), record picker with search view, live preview, render; verify the rendered PNG lands in `post.image_ids` and post preview (spec: wizard-bulk-create)
- [x] 7.2 Add "Create Posts from Image Template" list action using `active_ids` with model-match validation; verify selecting 54 products creates 54 draft posts each with its own rendered image on a seeded test DB (spec: wizard-bulk-create)
- [x] 7.3 Implement per-record transaction isolation and a result summary listing created posts and per-record failures; verify a batch with 3 broken records yields 51 posts and a readable failure list (spec: wizard-bulk-create)
- [x] 7.4 Verify bulk-created drafts schedule through `social_planner` unchanged (assign slots, approval flow shows the rendered image)

## 8. Agency glue module

- [x] 8.1 Create `social_image_creator_agency` adding `brand_id` to templates with record rules consistent with existing brand scoping; verify brand A users do not see brand B templates (spec: agency-brand-kit)
- [x] 8.2 Add brand kit to `social.brand`: palette, font attachments (registered with render service), reuse existing logo; verify fonts render server-side and the brand palette appears in the editor for that brand's templates (spec: agency-brand-kit)
- [x] 8.3 Verify record pickers respect brand scope where the binding model is brand-scoped (spec: agency-brand-kit)

## 9. Knowledge docs and final validation

- [x] 9.1 Write `docs/knowledge/social_image_creator.md` and `docs/knowledge/social_image_creator_agency.md` per repo convention; verify arc-kb indexing picks them up
- [x] 9.2 Run `openspec validate --change social-image-creator --strict` and the module test suite; verify zero failures
