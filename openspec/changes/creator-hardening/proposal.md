# Proposal: creator-hardening

## Why

The 2026-09-27 module audit found two critical-to-high security gaps in a module headed for AGPL community multi-tenant use: binding resolution performs no access checks (any authenticated user can resolve template tokens against any record id, bypassing ACLs, record rules and field groups) and the render service fetches arbitrary URLs from scene content (SSRF). The same audit found two functional defects: the bulk-creation entry point is unreachable from every UI menu, and the render wizard leaks a preview attachment on every refresh. This change closes the security gaps and fixes the defects.

## What Changes

- **Access-controlled binding resolution**: an entry guard checks read access on the bound record before any resolution, render or preview; the dotted-path walker gains an optional per-record guard so traversed relations are checked too; `model_id` is constrained server-side (no transient or abstract models, optional admin-curated allowlist); `get_binding_fields` only lists fields the user may read.
- **Render service hardening**: scene image srcs are restricted to `data:` URLs and `/web/image` paths under the configured API base, enforced both in URL normalization and by a pre-flight scene scan before `loadFromJSON`; `/render` width and height are capped; the shipped `change-me` placeholder token is removed and refused at startup.
- **Multi-company scoping**: record rule on `social.image.template` for the marketing user group; managers are exempt.
- **Brand font security**: read access limited to marketing and entitled customer groups; uploaded font binaries validated by magic bytes, not filename.
- **Reachable bulk creation**: `ir.actions.server` entries are created dynamically per bound model so the bulk wizard appears in the Action menu of the relevant list views, and are removed when no template binds the model anymore.
- **Preview attachment lifecycle**: at most one live preview attachment per template, daily cleanup cron for leftovers, and the redundant Refresh button is removed.
- **Menu structure**: a parent "Image Studio" menu groups Templates; Image Sizes moves under Configuration.
- Knowledge documentation corrections where it currently describes wrong behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `data-binding`: resolution enforces record, traversal and field access; binding models are curated server-side.
- `render-pipeline`: scene image URLs are allowlisted; render dimensions are capped; no placeholder token ships.
- `wizard-bulk-create`: bulk creation is reachable from record list action menus.
- `image-templates`: templates are company-scoped; preview attachments do not accumulate; menus group the studio.
- `agency-brand-kit`: brand fonts are limited to entitled groups and uploads are content-validated.

## Impact

- **social_image_creator**: binding glue in models (entry guard, model_id constrains, field filtering), new security rule XML, cron data for preview cleanup, view changes (form, menus), dynamic server-action sync logic, moved knowledge corrections. Model and security changes require updating `docs/knowledge/social_image_creator.md`.
- **render_service**: URL allowlist and pre-flight in render_core.mjs, dimension caps in server.mjs, Dockerfile token removal, new tests in test_security.mjs and test_core.mjs.
- **social_image_creator_agency**: access CSV changes, font magic-byte constraint. Knowledge doc update.
- **Deployment**: staging verification before push; render container ideally without outbound egress beyond Odoo.
