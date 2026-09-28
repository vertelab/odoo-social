# Tasks

## 1. Markdown to character styles

- [x] 1.1 Implement parseMarkdownSegments in render_core.mjs and apply it to every substituted text object, merging into existing per-char styles without dropping other attributes; verify with pure tests: bold, italic, mixed, nested-adjacent, unmatched marker literal, escaped asterisk
- [x] 1.2 Mirror the identical function into social_image_editor_utils.js and call it in the preview token-resolution path; verify a parity test asserting identical text and styles output for the same fixtures on both sides

## 2. Transform and autofit at render time

- [x] 2.1 Apply _textTransform to resolved text inside applyBindingsToScene after substitution; verify a pure test that `{{name}}` with upper transform resolves and uppercases while the pre-substitution text is untouched
- [x] 2.2 Implement render-time autofit with an injected measure function and the editor's binary-search algorithm (minimum font size 4 px); verify pure tests where a long resolved value shrinks to fit the box and a short value does not grow
- [x] 2.3 Wire server.mjs to pass a node-canvas measurement into the pipeline with the object's font family and size; verify with a render_core integration fixture under test_binding.mjs

## 3. Editor capture and UX

- [x] 3.1 Remove text mutation from _applyTextPropsToAll at capture so stored scenes keep raw token text while _textTransform/_overflow still persist via EXTRA_PROPS; verify a static test asserting the captured scene text is unchanged
- [x] 3.2 Keep WYSIWYG display transform in the live canvas with restore-on-exit using the existing snapshot mechanism; verify by the existing preview/restore tests still passing
- [x] 3.3 Update inspector help copy to state that case transform and autofit apply at render; verify by template lint test

## 4. Docs and verification

- [x] 4.1 Update docs/knowledge/social_image_creator.md with the render-time semantics and markdown support
- [x] 4.2 Run all mjs suites, check_fabric_sync and check_social_image_binding; all green
- [ ] 4.3 Staging smoke: render a template combining markdown, transform and a deliberately long bound value; compare editor preview, server PNG and reloaded scene text against expectations; record in the run note
