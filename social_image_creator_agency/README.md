# Social Image Creator Agency Glue

Glue module between `social_image_creator` and `social_marketing_agency`
(design decision D8 in the social-image-creator change). The base image
creator module stays agency-agnostic; this module adds:

- `brand_id` on `social.image.template` (optional) plus record rules
  copied from the agency pattern in `social_marketing_agency`.
- A brand kit on `social.brand`: `palette` (JSON list of hex colors) and
  `social.brand.font` lines (family name + uploaded font file, max 5 MB,
  ttf/otf/woff/woff2).
- Editor integration: brand palette colors become color swatches and brand
  fonts become font picker entries via the registries in
  `social_image_creator/static/src/js/dialog/brand_assets.js`.
- Brand-constrained binding record pickers (render wizard + editor live
  preview) via `social.image.template.get_binding_domain()`.

## Deploying brand fonts to the render service

The render service cannot read Odoo attachments; it registers every file
in its local `render_service/fonts/` directory, where the family name must
equal the file basename without extension (see
`render_service/fonts/README.md`). Uploading a font in Odoo therefore does
NOT make it available server-side by itself. Sync manually:

1. On the brand form, Brand Kit page, click the font line's download
   button ("Download for render service"). It serves the file with its
   original basename.
2. Copy the file into `render_service/fonts/` (in the deployed container
   or image build).
3. `POST /fonts/reload` to the render service (bearer token), or restart
   it. `GET /fonts` lists the registered families; check that the family
   name matches what the editor's fontFamily uses.

The Salt/Docker font sync is a manual copy for now; automating it (e.g.
an export script or a shared volume) is a possible later change.

## Scope notes

- Visibility of templates and fonts is enforced by record rules
  (`security/security.xml`), consistent with the agency module: customer
  users see their own brands' data plus unbranded company-level templates;
  agency brand users see their assigned brands; managers see all.
- Record selection for binding is limited to the template's brand on the
  render wizard (onchange domain + server-side guard) and in the editor
  preview picker (name_search domain). The bulk wizard needs no extra
  rule: it operates on records the user already selected in a list view,
  which the agency record rules already scoped.
