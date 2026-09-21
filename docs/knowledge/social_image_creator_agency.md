# Knowledge: social_image_creator_agency

Glue module between social_image_creator and social_marketing_agency
(design decision D8): brand scoping and a brand kit for image templates.
Depends on `social_image_creator` + `social_marketing_agency`.

## Models

- `social.image.template` (`_inherit`, `models/social_image_template.py`):
  optional `brand_id` (social.brand). `get_binding_domain()` returns
  `[('brand_id', '=', brand)]` when the template is branded and the
  binding model has a `brand_id` field (detected via `_fields`), else
  `[]` (company scope). `render_for_record` and `get_preview_bindings`
  raise UserError for records outside the template's brand as a
  server-side guard behind the pickers.
- `social.brand` (`_inherit`, `models/social_brand.py`): brand kit.
  `palette` is a JSON list of hex strings; `font_ids` is a One2many to
  `social.brand.font`. The logo field from the agency module is reused.
- `social.brand.font` (`models/social_brand_font.py`): `brand_id`,
  `sequence`, `name` (family name, must equal the file basename without
  extension, the render_service/fonts convention), `filename`, `file`
  (Binary attachment). Constraints: max 5 MB, extension ttf/otf/woff/woff2.
  `action_download_for_render_service()` serves the attachment under its
  original basename so it can be copied into `render_service/fonts/`.
- `social.image.render.wizard` (`_inherit`,
  `models/social_image_render_wizard.py`): onchange returns
  `{'domain': {'record_id': template.get_binding_domain()}}`; the
  `_get_bound_record` guard raises for out-of-brand records (covers stale
  or hand-crafted record_ids).

## Security

`security/security.xml` mimics the agency patterns: customer approver/editor
read own brands' templates (plus unbranded, via the `brand_id = False` OR
branch), customer editor writes own brands, agency brand users see their
`user.brand_ids` plus unbranded templates; `social.brand.font` follows the
social.brand.credential shape (brand_id required, so no False branch).
Access rights for customer groups on templates and for the font model are
in `security/ir.model.access.csv`. Transient wizards need no rules.

## Editor integration

`static/src/js/brand_provider.js` patches the editor dialog:
`_loadBrandContext` additionally reads the template's `brand_id`, fetches
the brand palette + fonts through the ORM and feeds them through the
`registerBrandColorProvider` / `registerBrandFontProvider` registries in
`social_image_creator/static/src/js/dialog/brand_assets.js` (module-level
kit read by the registered providers; the patch re-runs the collectors
after fetching). Brand fonts are also loaded into `document.fonts` from
their attachments so the canvas renders them. `_searchPreviewRecords` is
patched to pass the `get_binding_domain()` result as the name_search
domain. All fail-soft.

## Where enforcement lives

- Template/font visibility: record rules (server).
- Wizard record picker: onchange domain (UI) + `_get_bound_record` guard
  (server). The bulk wizard needs nothing: its records come from a list
  view already scoped by the agency rules.
- Editor preview picker: name_search domain (UI) +
  `get_preview_bindings` guard (server); `render_for_record` guard for
  every other render path.

## Deployment

Brand fonts are Odoo attachments; the render service reads only its local
`render_service/fonts/` dir. Deploy manually: download via the font line
button, copy into the fonts dir, `POST /fonts/reload`. Documented in the
module README.md.
