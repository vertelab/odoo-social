# Design: creator-render-parity

## Context

render-engine-os applies inline markdown, case transform and overflow autofit at render time, after token substitution (`render/server.mjs:66-130`, `:299-330`). The Odoo port moved transform and autofit into the editor's capture path (`_applyTextPropsToAll` in the dialog), which is where the two bugs live: token text gets uppercased before substitution so `{{name}}` no longer matches the case-sensitive token regex, and autofit is measured against placeholder text so longer bound values overflow. Markdown was never ported at all. The codebase already has a strict editor/render mirror convention (TOKEN_RE, cover-fit math) with parity tests, and render_core functions are pure with injectable dependencies (the fonts module uses an injectable registerFont).

## Goals / Non-Goals

**Goals:**
- Bound text renders markdown bold/italic correctly in both editor preview and server output.
- Transform and autofit operate on resolved values at render time; tokens survive capture intact.

**Non-Goals:**
- Full markdown (headings, links, lists); only `**bold**` and `*italic*` inline markers.
- Editor toolbar buttons that insert markers (a later convenience; markers can be typed).
- Changing the existing edit-time autofit behavior for purely static text.

## Decisions

### D1: Markdown parser as a pure function in render_core, mirrored in editor utils

`parseMarkdownSegments(text)` returns plain text plus segment ranges with weight/style. render_core applies it to every substituted text object by merging into the existing `styles` map (only overriding fontWeight/fontStyle per segment, preserving other per-char attributes). The editor utils carry the identical function for preview, and a parity test feeds both implementations the same fixtures. Ported from `render/server.mjs:66-130` with the same unmatched-marker and escape semantics.

### D2: Transform and autofit inside the binding pipeline, with injected measurement

`applyBindingsToScene` grows two post-substitution steps: apply `_textTransform` to the resolved text, then, when `_overflow` is autofit, recompute `fontSize` by binary search using a `measure(text, style) => width` function passed in options. server.mjs supplies a node-canvas 2d-context measurement with the object's font; tests inject a fake. The binary search mirrors the editor's `computeAutofitFontSize` so both sides converge on the same size for the same text; a shared pure implementation is preferred and copied per the mirror convention, with a parity fixture pinning identical outputs.

Alternative considered: letting the editor send a fitted fontSize per record at render request time. Rejected: it would move substitution knowledge into the editor and break the render service's independence.

### D3: Editor capture stops mutating text

`_applyTextPropsToAll` no longer rewrites `obj.text` at capture; the inspector copy for case transform and autofit states they apply at render. The live canvas may still show transformed/fitted text for WYSIWYG comfort, restored from the raw stored values on load (the existing preview snapshot mechanism already demonstrates restore-on-exit).

## Risks / Trade-offs

- [Markdown markers in user data meant literally] → escaped `\*` support and unmatched-marker pass-through; documented in the help copy.
- [Autofit measurement divergence between node-canvas and browser] → same algorithm plus a parity fixture with a fixed measure function; residual glyph differences accepted (same class of variance as today).
- [Old scenes with baked transformed text] → they keep working (no tokens left to break); only token-bearing scenes gain the fix.

## Migration Plan

Deploy render_service first (backward compatible: new behavior only triggers on the existing props), then the module assets. Staging verification: render a template with markdown, transform and autofit against a long bound value and compare editor preview, PNG output and reloaded scene text.

## Open Questions

None blocking. The minimum autofit font size (suggested 4 px) is a tuning constant recorded in tasks.
