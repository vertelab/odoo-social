# Design: social-image-creator

## Context

`social_marketing` already contains a working proof of concept:
`social.image.template` (model + placeholder submodel), a Fabric 6.9.1
editor OWL field (`static/src/js/fields/social_image_editor_field.js`),
a render wizard, and `render_service/` (Node + Fabric 6.9.1 + node-canvas,
`POST /render` with `{{placeholder}}` substitution and `_hideIfEmpty`).
No production data exists on any of it. A standalone SaaS,
render-engine-os, proved the full feature set this change ports; its
editor is one 4952-line React file and its render worker a 417-line Node
file. Fabric is pinned to 6.9.1 in both runtimes in both projects, so
scene JSON is portable as-is. See proposal.md for scope and motivation.

## Goals / Non-Goals

**Goals:**
- One Odoo-native binding model: template `model_id`, tokens resolve
  against real records.
- Editor output and server render stay pixel-identical.
- Two entry points (post wizard, bulk `active_ids` action) over one engine.
- Code migration from `social_marketing` is clean and breaking only
  pre-release.

**Non-Goals:**
- No dynamic mini-database, CSV import, workspace tenancy, bulk export UI
  (see proposal, Impact).
- No scheduling logic; posts are drafts for `social_planner`.
- No live re-flow of designs across sizes (variants are separate scenes;
  duplicate-with-scale is the migration aid, as in render-engine-os).

## Decisions

### D1: Binding resolution happens in Odoo, substitution in Node
The Python side walks the scene JSON, collects referenced fields, reads
them from the chosen record (dotted-path walker for relation fields,
readability-checked), and sends plain `{token: value}` bindings to the
render service. The service only substitutes text and swaps bound image
URLs. Rationale: Odoo owns field semantics, access rights and record
scoping (company/brand); the Node service stays a dumb, safe renderer.
Alternative considered: sending record IDs to the service and letting it
query Odoo (rejected: doubles the API surface, bypasses ACL if not careful,
and the render service deliberately has no Odoo dependency).

### D2: Scene JSON stays Fabric `canvas.toJSON()` plus namespaced custom props
Custom metadata (`_hideIfEmpty`, `_dataBinding`, `_required`, text
transform, autofit) uses the `_` namespacing already proven in
render-engine-os. Both runtimes sanitize before `loadFromJSON` because
props shaped like `{type: ...}` get enlivened as Fabric classes.
Alternative considered: a custom scene schema (rejected: throws away
Fabric round-trip compatibility and the render service's `loadFromJSON`).

### D3: Variants as JSONB column on the template, not child records
`variants` is a JSONB list `[{name, width, height, scene_json, is_primary}]`
mirroring render-engine-os's `Template.variants`. Legacy `width`, `height`,
`scene_json` fields mirror variant[0] during migration and are removed.
Rationale: variants are edited one-at-a-time in the editor, never searched
or related to; a child table adds joins and ORM overhead for no query
benefit. Alternative considered: one record per variant (rejected: every
save touches N records, form views get awkward).

### D4: Editor as OWL modal action, not a form-field widget
The editor becomes a full-screen modal launched from the template form
("Edit Design"), with canvas center, layer panel left, properties right.
The current inline field widget cannot host layer/properties panels.
The modal owns autosave and history; the form still shows thumbnail +
masters. Rationale: Canva-style workspace needs the pixels; a modal gives
full viewport without leaving the record context.

### D5: Undo/redo as bounded scene-JSON snapshots
Full `canvas.toJSON()` snapshots (cap 80, 500ms debounce), exactly as
render-engine-os. Fabric has no native history. Snapshot cost is a few KB
per step; fine for 80 steps. Alternative considered: command/operation log
(rejected: far more code, must handle every op type, and snapshot restore
is one `loadFromJSON`).

### D6: Fonts registered server-side in the render service
Brand and Google fonts used by templates are downloaded once (attachment or
bundled TTFs) and registered via node-canvas `registerFont` at service
start and on font upload; the service exposes `/fonts/reload`. This fixes
the known weakness in both prior systems (silent DejaVu fallback).
Rationale: font parity is the single biggest "looks broken" risk; it is
cheaper to do now than to debug mismatches later.

### D7: Bulk creation loops posts, one transaction per record
The bulk action creates each post in its own transaction (savepoint per
record), renders its image, and collects per-record success/failure into a
summary at the end. Rationale: matches the spec's retry safety; rendering
54 images inline is seconds each, acceptable synchronously for wizard UX;
large batches can later move to queue_job without changing the contract.

### D8: `social_image_creator` is agency-agnostic; glue module adds brand
Base module knows `company_id` only. `social_image_creator_agency` adds
`brand_id` (and its record rules), brand kit fields on `social.brand`
(palette, fonts via a font attachment model, reuse existing `logo`), and
injects the brand palette/fonts into the editor through the same extension
points the base module exposes for company assets.
Rationale: keeps the base module installable without the agency stack,
per requirement.

### D9: Size presets as data-driven records
`social.image.size` (name, width, height, platform, active) ships with
standard presets in `data/`. Variant creation offers preset or custom.
Replaces the current hardcoded selection field.

### D10: Bulk rendering is synchronous in v1
The bulk action renders inline per record. No queue_job dependency in this
change; if a real batch turns out to hurt, the per-record savepoint design
(D7) lets a later change move rendering to queue_job without touching the
contract.

### D11: Editor fonts load via Google Fonts CDN
Google Fonts are lazy-loaded in the editor via the standard Google Fonts
CSS link (weights 400/700), quick and dirty for v1. Brand fonts uploaded
as attachments are applied by name and, per D6, registered server-side.
Self-hosting fonts for GDPR tidiness is a possible later change, not v1.

## Risks / Trade-offs

- **Editor/render divergence** for exotic Fabric features (blend modes are
  explicitly out; SVG export quirks) → keep to the render-engine-os proven
  feature list; parity covered by rendering each template server-side in
  tests and diffing against editor output for a golden set of scenes.
- **Cover-fit image binding is mathematically finicky** (cropX/cropY
  compensation with clipPath) → port the mirrored implementations verbatim
  from render-engine-os (`render/server.mjs` fit logic and
  `TemplateEditor.jsx` `applyImageCoverFit`), including its tests.
- **53k-record models in pickers** → never offer unfiltered many2one
  dropdowns for record selection; always search views / name_search with
  limits; bulk path uses `active_ids` so selection happens in list views.
- **Modal editor + unsaved record** → editor requires a saved template
  (button disabled on new records); autosave targets the saved record.
- **Fabric version skew** → both `package.json` files pin the exact same
  version; a `check_pfile_sync.py`-style check could guard this later.
- **JSONB variants lose per-variant attachments** → SVG masters are
  regenerated per save; PNG masters are derived, not stored per variant.

## Migration Plan

1. Create `social_image_creator` with migrated models/views/editor/wizard
   from `social_marketing`; remove them there in the same change
   (pre-release, no data migration needed beyond the code move).
2. Extend model: `model_id`, variants JSONB, size preset model; drop legacy
   width/height mirror after editor/wizard switched.
3. Port render-engine-os editor capabilities incrementally (layers ->
   history -> typography/effects -> snapping/groups -> shapes/icons ->
   preview mode), keeping the render service in lockstep.
4. Add binding resolution (Python) + font registration (Node).
5. Add bulk action + wizard rework; then agency glue module.
Rollback: feature branches per step; modules uninstall cleanly since the
new module owns its tables.
