# Design: creator-hardening

## Context

`social_image_binding.py` is deliberately free of Odoo imports so it can run under plain `python3` (scripts/check_social_image_binding.py); access checks therefore cannot live inside it. Entry points today take a user-controlled record id and call `browse()` plus direct field reads, which skip ACLs, record rules and field groups in Odoo 18. The render service loads scenes through Fabric's node build, whose JSDOM instance fetches arbitrary URLs (`resources: 'usable'`), so every image src in a scene is a potential server-side fetch. Templates carry `company_id` but no record rule exists. The bulk wizard's server action has a NULL `binding_model_id`, which Odoo 18 excludes from every Action menu. See proposal.md for the motivating findings.

## Goals / Non-Goals

**Goals:**
- Close the access-control bypass without breaking the standalone check script.
- Stop the render service from fetching anything except Odoo web images and inline data.
- Company-scope templates, tighten brand font access, validate font bytes.
- Make bulk creation reachable and stop preview attachment growth.

**Non-Goals:**
- Row-level publishing of record data beyond read access (write access is not granted anywhere here).
- Changing how bound images are encoded (binary field bindings producing data URLs remain the recommended path for non-public images).
- Rate limiting or authentication changes on the render service beyond the placeholder-token removal.

## Decisions

### D1: Access checks injected, not embedded

`social_image_binding.py` gains an optional `guard(record)` callback on `resolve_field_path` and `build_bindings`, invoked on the root record and every traversed record. The Odoo layer supplies a guard that runs `check_access_rule('read')` and converts `AccessError` to `BindingError`. A new `_bound_record(model, record_id)` helper in `social.image.template` performs `check_access_rights('read')` plus the rule check, and is used by every entry point (preview RPC, render wizard, bulk wizard, publish hook, direct render calls). This keeps the pure module standalone-testable and puts policy in the ORM layer.

Alternative considered: importing Odoo exceptions into the pure module. Rejected: it would break the standalone check and the mirrored Node tests.

### D2: Curated binding models

A `@api.constrains('model_id')` rejects transient and abstract models server-side (the current restriction lives only in a view domain). An optional `ir.config_parameter` (`social_image_creator.allowed_binding_models`) holds a comma-separated admin-curated model list; when set, only those models may be bound. `get_binding_fields` filters with `field.is_accessible(env)` so group-restricted fields stop appearing in the picker.

Alternative considered: hardcoding an allowlist in code. Rejected: community deployments need different models without code changes.

### D3: URL allowlist plus pre-flight scan

`absolutizeFileUrl` becomes strict: allow `data:` and `/web/image` paths (absolutized against `API_BASE_URL`, host must match). Because JSDOM fetches srcs directly during `loadFromJSON`, a pre-flight `assertSceneImageUrlsAllowed(scene, apiBase)` walks every image object before load and throws naming the layer; server.mjs maps it to HTTP 400. Both layers are needed: normalization catches the paths we rewrite, the pre-flight catches everything else.

Trade-off: `/web/image` without credentials only renders public attachments; bound images for non-public data must come from binary field bindings (data URLs), which the binding engine already produces. This fails closed and is documented.

### D4: Standard company rule pattern

One `ir.rule` for `group_social_marketing_user` on `social.image.template` with the standard `['|', ('company_id','=',False), ('company_id','in', company_ids)]` domain; the manager group gets no rule and sees all. This matches the agency module's established pattern.

### D5: Dynamic server actions for bulk creation

`social.image.template` gains `_sync_bulk_actions()`, called on create/write (and from a Settings button): for each model bound by at least one template it ensures an `ir.actions.server` exists with `binding_model_id` set, `binding_type action`, code opening the bulk wizard; actions for unbound models are unlinked. Actions are created as sudo; the risk is accepted because the wizard itself validates that the chosen template's binding model matches the source model, and only marketing users reach it.

### D6: Preview lifecycle

`_refresh_preview` unlinks existing `(preview)` attachments for the template before creating a new one; a daily cron removes leftovers older than 24 hours as a backstop for crashes between steps. The Refresh button is removed from the wizard footer since every relevant change already triggers the onchange preview.

### D7: Font security

The agency access CSV grants read to the marketing groups plus the customer groups already scoped by record rules, replacing the blanket `base.group_user` line. A constraint validates the decoded bytes against TTF/OTF/WOFF/WOFF2 magic signatures; extension and size checks stay as the UX layer.

## Risks / Trade-offs

- [Guard callback forgotten on a new entry point] → one shared `_bound_record` helper used everywhere; a TransactionCase renders as a low-privilege user to catch regressions.
- [Dynamic actions left behind after module uninstall] → actions carry `noupdate` records tied to module data; uninstall cleans module data, and the sync is idempotent.
- [Allowlist too restrictive for some community user] → parameter is optional and empty means "any non-transient model", documented in settings.
- [Legit external image URLs stop working] -> acceptable: scenes should embed or bind images; documented in README.

## Migration Plan

Staging first: install/upgrade the module, run the new TransactionCase and render service tests, smoke the editor preview, a bulk run from a product list, and a cross-company check with two companies. Render service deploys before or with the module (it is backward compatible for older modules). Rollback: revert both; the new rules and actions are module data and disappear on uninstall.

## Open Questions

None blocking. The exact group xmlids for the font ACL follow the existing agency security.xml groups.
