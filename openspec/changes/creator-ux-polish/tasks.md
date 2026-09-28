# Tasks

## 1. Editor close safety

- [x] 1.1 Make close() honor flush failures: stay open with message and retry, keep dirty state, block while a save is in flight; verify with a static test driving the close path with a failing save
- [x] 1.2 Add explicit-discard flow for a second close attempt after failure; verify by test that edits survive until discard is confirmed

## 2. Keyboard and accessibility

- [x] 2.1 Add Delete/Backspace (suppressed during text editing) and layered Escape handling to the existing keydown handler; verify with static tests asserting handlers fire and unwind in order
- [x] 2.2 Convert the image/SVG upload togglers to real buttons with aria-labels and add aria-labels to icon-only toolbar buttons; verify by template lint test on the dialog XML
- [x] 2.3 Add :focus-within visibility for layer action buttons matching the hover rule; verify by SCSS diff

## 3. Translations

- [x] 3.1 Wrap all user-facing dialog JS/XML strings in _t()/translation-aware output and add a lint check flagging new untranslated literals; verify the lint check fails on a planted raw string
- [ ] 3.2 Regenerate social_image_creator sv.po from current sources and prune dead entries; create the agency module sv.po; verify both export cleanly and Swedish renders for a sample of editor strings on staging

## 4. Forms and wizards

- [x] 4.1 Remove the raw variants JSON field and png_master preview from the template form and add no_create/no_open to model_id; verify by view diff and staging form render
- [x] 4.2 Replace variant_index with name-based variant selection in both wizards (resolve to index at render, primary fallback with warning); verify with TransactionCase renders using the first, a named and a renamed variant
- [x] 4.3 Add the empty-state guidance to the template list; verify by view diff and staging render

## 5. Palette validation

- [x] 5.1 Add the palette JSON constraint to social.brand with a friendly example-bearing error; verify with unit tests for valid, malformed and non-hex input

## 6. Error and onboarding polish

- [x] 6.1 Convert the persistent editor error line into a dismissible message that auto-clears after a timeout; verify by static test of the message lifecycle

## 7. Docs and verification

- [x] 7.1 Update docs/knowledge/social_image_creator.md for the wizard variant selection and form changes
- [x] 7.2 Run all mjs suites and check scripts; all green
- [ ] 7.3 Staging smoke: close-guard with a forced save failure, keymap pass, Swedish UI pass, variant selection in both wizards, palette error path; record results in the run note
