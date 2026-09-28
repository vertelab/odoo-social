# Proposal: creator-ux-polish

## Why

The UX audit found the module well engineered internally but hard to approach cold: closing the editor can silently discard work, keyboard users are shut out of core interactions, the entire editor surface is English-only with a stale Swedish catalog, the template form shows raw JSON and a dead field, wizards ask for variant indices instead of names, the brand palette is edited as raw JSON text, and first-time users get no guidance anywhere. None of this needs new capability; it needs polish. This change collects those improvements.

## What Changes

- **Editor close safety**: the dialog blocks closing while a save is failing, offers retry, and keeps dirty state instead of dropping edits.
- **Keyboard and accessibility**: Delete/Backspace removes the selection, Escape closes pickers then the dialog, layer action buttons stay visible on keyboard focus, the image/SVG upload togglers become real focusable buttons with aria-labels, and icon-only controls get labels.
- **Translatable editor**: every user-facing JS and XML string goes through `_t()`, the Swedish catalog is regenerated for both modules, and the agency module gets its first catalog.
- **Template form cleanup**: the raw `variants` JSON and the never-written `png_master` preview are removed from the form, and `model_id` gets no-create/no-open options.
- **Variant selection by name**: both wizards select a variant by its name instead of a 0-based integer index.
- **Palette validation**: the brand kit palette field validates its JSON list of hex colors with a friendly error until a real color widget exists.
- **Error and onboarding polish**: editor errors become dismissible messages with a timeout, and the empty template list explains what an image template is and how to start.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `template-editor`: closing the editor never silently discards work; the editor is keyboard reachable; the editor UI is translatable.
- `image-templates`: the template form shows only meaningful design state; the template list guides first-time users.
- `wizard-bulk-create`: variant selection uses names instead of indices.
- `agency-brand-kit`: palette input is validated with friendly errors.

## Impact

- **social_image_creator**: dialog JS/XML/SCSS (close guard, keymap, focus styles, buttons, aria, toasts), template views, wizard models/views (variant selection), i18n template extraction and sv.po regeneration.
- **social_image_creator_agency**: palette constraint, sv.po catalog created.
- **docs/knowledge/social_image_creator.md** updated where wizard fields change.
- No model shape changes beyond a display-oriented wizard field; no migration.
