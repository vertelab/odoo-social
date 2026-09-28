# Knowledge: social_image_creator

Social Image Creator: Fabric.js image templates for social posts,
server-side rendering through the Node render service in
`render_service/`.

## Models

- `social.image.template` (`models/social_image_template.py`): one or
  more named size `variants` (JSONB: `{name, width, height, scene_json,
  is_primary}`), binding model `model_id`, placeholders. Rendering:
  `render_template` (manual bindings) and `render_for_record` (bindings
  resolved from a record by `social_image_binding`) both end in
  `_render_scene`, which POSTs to the render service and stores the
  result as an `ir.attachment` on the template. Service URL and token
  come from `ir.config_parameter` (`social_marketing.render_service_url`
  / `_token`); an unset URL raises a UserError pointing to Settings.
  Binding model curation: a constrains rejects transient/abstract
  models, and the optional parameter
  `social_image_creator.allowed_binding_models` (comma-separated)
  restricts which models may be bound when set.
- `social.image.template.placeholder`: named fill-in fields.
- `social.data.binding`: named link between a template token and one field
  of one model; `{{ token }}` is looked up, never evaluated. A binding
  belongs to exactly one owner, either an image template (`template_id`)
  or a post template (`post_template_id`). The pure token helpers
  (`substitute_tokens`, `collect_tokens`, `web_image_source`) live in
  `social_marketing/models/social_data_binding_core.py`, kept there
  because `social_marketing_agency` imports them without depending on
  this module.
- `social.image.template` / `social_marketing.post.template` extensions
  (`models/social_data_binding.py`): `binding_ids` one2many plus
  `get_binding_values` / `render_bound_text`; templates additionally get
  `render_template_for_record`. The "Create Image from Template" button
  on the post form is `views/social_marketing_post_views.xml` here (it
  inherits `social_marketing.social_marketing_post_view_form` and opens
  this module's render wizard action), and the Data Bindings groups on
  both template forms are `views/social_data_binding_views.xml`.
- `social.image.size`: data-driven size presets (menu lives under
  Configuration).
- `social.image.render.wizard` (+ `.line`): render dialog. Fields:
  `template_id`, `format` (png/svg), `render_timing`
  (`on_create` default, `on_publish`), `record_model` + `record_id`
  (Many2oneReference against the template's binding model; empty means
  manual placeholder lines), `variant_name` selection (choices are the
  union of readable templates' variant names; `variant_index` is computed
  from the name server-side, primary variant as fallback with a warning
  when the stored name no longer exists). Computed flags:
  `has_binding_model`, `binding_mismatch` (record picked from the wrong
  model after a template change; warning banner + refused on confirm),
  `show_render_timing` (on_publish only from a post). A live PNG preview
  (attachment named "(preview)") refreshes on every relevant onchange;
  `_refresh_preview` unlinks the template's previous preview attachment
  first, and a daily cron (`data/social_image_preview_cron.xml`) removes
  leftovers older than 24h. Failures land in `preview_error`.
  `on_create` renders immediately and attaches to `post.image_ids` when
  opened from a post. `on_publish` only works from a post and stores a
  pending render on it.
- `social.image.bulk.wizard`: bulk dialog opened from dynamically synced
  per-model server actions (see "Bulk actions" below). Validates that the
  template's binding model matches the source model BEFORE creating
  anything. Creates one DRAFT `social_marketing.post` per record
  (message = record display_name, `image_template_*` provenance fields
  set, account left empty for the planner), rendering each image inside a
  per-record `cr.savepoint()` so one failure cannot roll back the others.
  `action_create_posts` reports into `created_post_ids`,
  `created_count`, `failure_details`; when every record fails it raises
  UserError with the full list instead.
- `social_marketing.post` (`_inherit`, `models/social_marketing_post.py`):
  `image_template_id`, `image_template_record_model`,
  `image_template_record_id`, `image_variant_index`,
  `image_render_pending`, `image_render_error`. `_action_post` override:
  pending renders run before the inherited publish; a failed render
  stores the message in `image_render_error` and removes the post from
  the publish batch. `_action_post` is the publish choke point (reached
  by `action_post` and by the scheduled cron `_cron_publish_scheduled`).

## Security

- Binding resolution is access-controlled: `_bound_record()` checks
  `check_access_rights`/`check_access_rule` before any resolution, and
  the pure resolver in `social_image_binding.py` takes an optional
  per-record `guard` callback invoked on the root record and every
  traversed relation hop. Entry points: preview RPC, render wizard, bulk
  wizard, publish hook, direct render calls.
- Company scoping: `security/company_rules.xml` restricts
  `group_social_marketing_user` to own-company templates
  (`['|', ('company_id','=',False), ('company_id','in',company_ids)]`);
  the manager group gets an explicit permissive rule because group
  implication would otherwise OR-restrict managers too.
- Bulk actions: `_sync_bulk_actions()` on the template creates (sudo,
  idempotent) an `ir.actions.server` per bound model named "Create Posts
  from Image Template" with a real `binding_model_id`, from
  create/write/unlink and from a manual sync action; actions for unbound
  models are removed. The old static NULL-binding action was removed
  (NULL bindings appear in no Action menu in Odoo 18).

## Render pipeline notes

- render_service loads only `data:` URLs and `/web/image` paths under
  `API_BASE_URL` (strict allowlist plus a pre-load scene scan);
  `/render` caps dimensions at integers 16..8192 with a 67108864 pixel
  product; startup refuses empty or placeholder tokens. Non-public
  images must be bound as binary fields (data URLs), since `/web/image`
  fetches are unauthenticated.
- Typography runs at render time after token substitution: `_textTransform`
  (upper/lower/title), inline markdown (`**bold**`, `*italic*`) merged
  into per-character styles, and `_overflow` autofit recomputed with
  measured text (binary search, floor 4 px). The editor mirrors the same
  pipeline in preview via `resolveTextForPreview` and no longer bakes
  transformed text into the stored scene, so `{{tokens}}` survive
  capture intact.

## Menus

"Image Studio" parent menu (marketing groups) holds Templates; Image
Sizes lives under Configuration.

## Conventions

- Fabric version: editor bundle `static/lib/fabric/index.min.js` and
  `render_service/package.json` must match; `make check-fabric`
  (`scripts/check_fabric_sync.py`) guards it.
- Scene custom props are `_`-namespaced (`_hideIfEmpty`, `_required`,
  `_dataBinding`, `_textTransform`, `_overflow`) and survive Fabric
  `loadFromJSON`.
- Fonts: the render service registers files from `render_service/fonts/`
  by basename (D6); CDN-only Google Fonts fall back in rendered PNGs
  (documented D11 trade-off).
