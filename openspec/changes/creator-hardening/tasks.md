# Tasks

## 1. Access-controlled binding resolution

- [ ] 1.1 Add optional `guard(record)` callback to `resolve_field_path` and `build_bindings` in social_image_binding.py, invoked on the root record and every traversed relation hop; verify the standalone check script still passes and add standalone tests with a recording fake guard
- [ ] 1.2 Add `_bound_record()` helper on social.image.template performing check_access_rights plus record-rule check, converting AccessError to BindingError; verify with a TransactionCase where a user without read access gets a clear error and no value leaks (use a rule-protected model as canary)
- [ ] 1.3 Route every entry point through the guard: get_preview_bindings, render_for_record, wizard _get_bound_record, bulk wizard and the publish hook; verify by grepping call sites and by the 1.2 test through at least two entry points
- [ ] 1.4 Add the model_id constrains (reject transient/abstract) and the optional allowed_binding_models config parameter; verify with TransactionCase saves that a transient model is refused and an allowlisted deployment accepts only listed models
- [ ] 1.5 Filter get_binding_fields with field.is_accessible(env); verify a group-restricted field no longer appears for a user outside that group

## 2. Render service hardening

- [ ] 2.1 Make absolutizeFileUrl strict (data: and API-base /web/image only) and add assertSceneImageUrlsAllowed pre-flight over all image objects, called from applyBindingsToScene and server.mjs before loadFromJSON; verify with test_security.mjs cases for http://127.0.0.1, file:///etc/passwd and a passing /web/image fixture, all mapping to 400 naming the layer
- [ ] 2.2 Cap /render width/height (integers 16..8192, product at most 67108864) in server.mjs; verify with test cases for oversized and valid dimensions
- [ ] 2.3 Remove the RENDER_TOKEN ENV from the Dockerfile and refuse known placeholder tokens at startup; verify test_auth.mjs-style case that change-me fails startup
- [ ] 2.4 Document in render_service/README.md that non-public images must be bound as binary fields (data URLs) and recommend no outbound egress for the container

## 3. Company scoping

- [ ] 3.1 Add the ir.rule for group_social_marketing_user on social.image.template and register it in __manifest__.py (and the .p.py); verify with a two-company TransactionCase that cross-company templates are hidden from users and visible to managers
- [ ] 3.2 Add company_id to the template form (optional group) and a company group-by in the list view; verify by view inspection on staging

## 4. Brand font security

- [ ] 4.1 Replace the base.group_user read line for social.brand.font with the marketing groups plus entitled customer groups in the agency access CSV (and .p.py where applicable); verify a plain internal user is denied and a customer user still loads fonts on staging
- [ ] 4.2 Add the magic-byte font constraint in social_brand_font.py; verify with unit tests accepting TTF/OTF/WOFF/WOFF2 signatures and rejecting a renamed payload

## 5. Bulk creation entry point

- [ ] 5.1 Implement _sync_bulk_actions() on social.image.template (create on create/write, unlink when unbound, Settings button) with sudo; verify a TransactionCase that binds a model, finds the action in the model's action bindings, opens the wizard with active ids, and that removal happens after the last template re-binds
- [ ] 5.2 Correct docs/knowledge/social_image_creator.md where it describes the old binding_model_id behavior

## 6. Preview lifecycle

- [ ] 6.1 Unlink previous (preview) attachments for the template inside _refresh_preview; verify a double-refresh leaves exactly one attachment
- [ ] 6.2 Add the daily cleanup cron for (preview) attachments older than 24h; verify by running the cleanup method in a test with aged fixtures
- [ ] 6.3 Remove the Refresh Preview button from the wizard footer; verify by view diff

## 7. Menus and docs

- [ ] 7.1 Introduce the Image Studio parent menu with Templates beneath it and move Image Sizes under Configuration; verify the menu tree on staging matches the spec
- [ ] 7.2 Update docs/knowledge/social_image_creator.md for the company rule, dynamic bulk actions and preview lifecycle (module shape changed)

## 8. Verification

- [ ] 8.1 Run all Python compiles, check_pfile_sync, check_social_image_binding, check_fabric_sync and all mjs suites; everything green
- [ ] 8.2 Staging smoke: upgrade module, run both TransactionCase suites, preview with a no-access user (expect error), bulk run from a product list, two-company visibility check, render service SSRF fixture check; record results in the run note
