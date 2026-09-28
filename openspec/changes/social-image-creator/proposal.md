# Proposal: social-image-creator

## Why

odoo-social covers publishing, planning and analytics well, but creating the
actual image for a post is left to external tools (Photoshop, Canva). There is
a working prototype (`social.image.template` in `social_marketing`, plus the
Node render service in `render_service/`), but it is a minimal proof of
concept: a flat toolbar, no layer panel, no undo, no data binding to real
records. Meanwhile a standalone SaaS, render-engine-os, already proved what a
full Fabric-based image creator looks like. This change ports that proven
feature set into Odoo, natively: templates bind to real Odoo records, images
render inside the stack, and posts carry them into the existing planner and
approval flow.

## What Changes

- **New module `social_image_creator`** (depends on `social_marketing`,
  agency-agnostic) receiving the migrated `social.image.template` model,
  Fabric editor field, render wizard and render service integration from
  `social_marketing` (no live data exists, this is code migration only).
- **Template model gains binding and variant support**: `model_id` (ir.model)
  declares which Odoo model a template binds to; tokens like
  `{{name}}` or `{{list_price}}` resolve against records of that model;
  multi-size variants (one design, several platform sizes) replace the
  single width/height pair.
- **User-extensible size presets** (`social.image.size`): standard platform
  sizes (Facebook, Instagram, LinkedIn, X, Open Graph) ship as data;
  users can add their own.
- **Full editor depth in a modal workspace** (Fabric 6.9.1): layer panel
  (visibility, lock, rename, duplicate, drag-reorder), undo/redo with
  autosave, typography (line height, char spacing, align, case transform,
  autofit overflow), gradients, shadows, stroke styles, corner radius,
  image filters, snapping with smart guides, align/distribute, group/ungroup,
  shape library, icon picker, brand colors and fonts.
- **Two render entry points sharing one engine**: single-post wizard on the
  post form (pick template, pick record, preview, render) and a bulk action
  on any list view (`active_ids`, so 54 products out of 53k are selected
  with Odoo's own search, then "Create Posts from Image Template" creates
  one draft post per record).
- **Render timing is flexible**: preview renders live in the editor; the
  actual PNG is produced at post creation or at publish time (configurable
  per flow), so approval always sees the real image.
- **Font parity fix in the render service**: fonts used by templates are
  registered server-side (today both systems silently fall back to DejaVu
  for anything but system fonts).
- **New glue module `social_image_creator_agency`** (depends on
  `social_marketing_agency`): `brand_id` on templates, brand kit (palette,
  fonts, logos) on `social.brand`.
- **BREAKING (within this repo, pre-release)**: `social.image.template`,
  its views, the editor field and the render wizard move out of
  `social_marketing` into `social_image_creator`. Any code depending on
  those models must depend on the new module.

## Capabilities

### New Capabilities

- `image-templates`: Template and size-preset models, variants, CRUD,
  migration from `social_marketing`.
- `template-editor`: Modal Fabric editor workspace: layers, history,
  objects, typography, effects, alignment, icons, brand assets.
- `data-binding`: Tokens bound to Odoo records, placeholder substitution,
  pipe transforms, conditional layers, record selection at render time.
- `render-pipeline`: Server-side rendering via the Node service with font
  registration, variant rendering, timing options (at creation vs publish).
- `wizard-bulk-create`: Single-post wizard and bulk list-view action that
  turn records into draft posts with rendered images.
- `agency-brand-kit`: Glue module: brand scoping and brand kit on
  `social.brand`.

### Modified Capabilities

None (no spec directory exists yet; this repo has no prior specs).

## Impact

- **Code**: new modules `social_image_creator`,
  `social_image_creator_agency`; code moved out of `social_marketing`
  (models, views, editor JS/XML, wizard, security CSV entries); render
  service (`render_service/`) gains font registration and binding
  resolution for Odoo record fields.
- **Dependencies**: Fabric pinned to 6.9.1 in both editor and render
  service (unchanged); no new runtime dependencies beyond what
  render-engine-os already validated.
- **Deliberate non-goals**: no dynamic mini-database (Odoo models are the
  data source), no CSV import, no bulk image export, no scheduling logic
  (that stays in `social_planner`), no template marketplace/sharing.
