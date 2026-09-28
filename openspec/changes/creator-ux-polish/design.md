# Design: creator-ux-polish

## Context

The UX audit rated the module feature-strong but cold-start-hostile. The specific gaps are well bounded: the close path flushes the save but closes regardless of the outcome (dialog js), keyboard handling exists only for a few shortcuts, no JS string goes through `_t()` and the shipped sv.po predates the modal editor, the form renders the raw `variants` JSON field and `png_master` (never written anywhere), wizards expose a 0-based `variant_index` integer, and the agency palette is a free-text JSON field. All changes ride on existing patterns (snapshot/restore, keymap, onchange previews).

## Goals / Non-Goals

**Goals:**
- No silent work loss, basic keyboard reachability, translatable UI.
- Forms and wizards show human-meaningful state only.
- Friendly validation where users currently get raw errors.

**Non-Goals:**
- Adopting the full standard Dialog component or a redesign of the editor layout (bigger effort, separate decision).
- A visual palette widget (validation now, widget later).
- Mobile/responsive redesign of the dialog.

## Decisions

### D1: Close guard via flush result plus dirty flag

`close()` awaits the flush; on failure it stays open with the existing message line plus a retry button, and sets a dirty flag so a second explicit close asks for confirmation. The pending-save timer is not cleared while a flush is in flight. This reuses the existing autosave machinery instead of adding a confirmation dialog on every close.

### D2: Keymap and focus fixes layered on current markup

Delete/Backspace and Escape join the existing keydown handler; the pickers already close on Escape so the handler unwinds in reverse order. The two upload togglers are converted from bare `<i>` elements to `<button type="button">` wrapping the icon, keeping the FileUploader slot intact. Layer actions get a `:focus-within` rule mirroring the existing `:hover` rule, and icon-only buttons receive `aria-label`.

### D3: Translation sweep by extraction, not by hand

All user-facing string literals in the dialog JS/XML are wrapped in `_t()` / `t-esc` translation-aware output, then the Swedish catalog is regenerated with Odoo's export tooling and pruned of dead entries from the removed inline editor. The agency module gets its first export. This is mechanical and enforced by a lint check in the static test suite (no raw alert/throw strings on the touched paths).

### D4: Wizard variant selection by name

The wizards' `variant_index` integer is replaced by a computed selection populated from the chosen template's `variants` names (stored name, resolved to index server-side at render time). Existing records and API callers keep working because the stored field becomes name-based while the render path resolves the index.

### D5: Palette validation constraint

A constraint on `social.brand` parses the palette JSON, requires a list of `#rrggbb` strings and raises ValidationError with an example on failure. Kept as a constraint (not an onchange) so imports fail loudly too.

## Risks / Trade-offs

- [Keymap conflicts with text editing] → shortcuts are suppressed while a text object is in editing mode, mirroring the existing guard for other shortcuts.
- [Translation churn in one sweep] → large diff but mechanical; the lint check keeps it from regressing.
- [Variant rename breaks stored wizard defaults] → names resolve at render time and fall back to the primary variant with a warning, never a hard failure.

## Migration Plan

Purely additive UX and view changes; no data migration. Rollback is a plain revert. Staging verification covers the close guard, the keymap, a Swedish interface pass, both wizards' variant selection and the palette error path.

## Open Questions

None blocking. Toast styling details are product tuning handled in implementation.
