## ADDED Requirements

### Requirement: Bound text supports inline markdown character styles

After token substitution, the render service SHALL convert `**bold**` and `*italic*` segments in each text object into per-character fabric styles, preserving any existing character styles on other attributes, and SHALL leave unmatched or escaped markers as literal text. The editor preview SHALL produce the same text and styles for the same input.

#### Scenario: Bold segment styled

- **WHEN** a bound text layer resolves to `Price: **1 299 kr**`
- **THEN** the rendered image shows "Price: " in the base style and "1 299 kr" bold, with no asterisks visible

#### Scenario: Unmatched marker stays literal

- **WHEN** a text contains a single `**` with no closing pair
- **THEN** the asterisks render as typed and the rest of the text keeps its styles

#### Scenario: Editor preview parity

- **WHEN** the editor resolves the same bound text in preview mode
- **THEN** the preview shows the identical styling as the server-rendered output

### Requirement: Text transform applies at render time

When a text object carries `_textTransform`, the render service SHALL apply it to the resolved text after token substitution. The persisted scene SHALL keep the untransformed token text so bindings continue to resolve.

#### Scenario: Token survives, output transforms

- **WHEN** a text layer contains `{{name}}` with `_textTransform` set to upper and the record name is "Acme"
- **THEN** the rendered image shows "ACME" and the saved scene still contains `{{name}}` so later renders resolve

### Requirement: Overflow autofit applies at render time

When a text object carries `_overflow` set to autofit, the render service SHALL recompute the font size against the resolved text so it fits the object's box, using real text measurement, never going below the minimum font size. The editor's edit-time autofit remains a convenience for static text only.

#### Scenario: Long bound value shrinks to fit

- **WHEN** a textbox autofit layer resolves to a value longer than the placeholder it was sized with
- **THEN** the rendered text fits the box at a smaller font size instead of overflowing

#### Scenario: Short value keeps size

- **WHEN** the resolved text is shorter than or equal to the fitted placeholder
- **THEN** the font size is not increased beyond the designed size
