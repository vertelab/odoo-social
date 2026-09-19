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
- `social.image.template.placeholder`: named fill-in fields.
- `social.image.size`: data-driven size presets.
- `social.image.render.wizard` (+ `.line`): render dialog. Fields:
  `template_id`, `format` (png/svg), `render_timing`
  (`on_create` default, `on_publish`), `record_model` + `record_id`
  (Many2oneReference against the template's binding model; empty means
  manual placeholder lines), `variant_index` (0 = primary). Computed
  flags: `has_binding_model`, `binding_mismatch` (record picked from the
  wrong model after a template change; warning banner + refused on
  confirm), `show_render_timing` (on_publish only from a post). A live
  PNG preview (`preview_attachment_id`, attachment named "(preview)")
  refreshes on every template/record/variant/placeholder change;
  failures land in `preview_error`. `on_create` renders immediately and
  attaches to `post.image_ids` when opened from a post. `on_publish`
  only works from a post and stores a pending render on it.
- `social.image.bulk.wizard`: bulk dialog behind the global server
  action "Create Posts from Image Template" (`binding_model_id` empty,
  so it sits on every model's Action menu; `active_model`/`active_ids`
  come through the context). Validates that the template's binding
  model matches the source model BEFORE creating anything. Creates one
  DRAFT `social_marketing.post` per record (message = record
  display_name, `image_template_*` provenance fields set, account left
  empty for the planner), rendering each image inside a per-record
  `cr.savepoint()` so one failure cannot roll back the others.
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

## Conventions

- Fabric version: editor bundle `static/lib/fabric/index.min.js` and
  `render_service/package.json` must match; `make check-fabric`
  (`scripts/check_fabric_sync.py`) guards it.
- Scene custom props are `_`-namespaced (`_hideIfEmpty`, `_required`,
  `_dataBinding`) and survive Fabric `loadFromJSON`.
- Fonts: the render service registers files from `render_service/fonts/`
  by basename (D6); CDN-only Google Fonts fall back in rendered PNGs
  (documented D11 trade-off).
