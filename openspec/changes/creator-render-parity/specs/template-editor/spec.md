## ADDED Requirements

### Requirement: Editor defers transform and autofit to render

The editor SHALL persist token text untransformed at capture time while still storing the `_textTransform` and `_overflow` properties, and SHALL indicate in the inspector that these apply at render.

#### Scenario: Capture keeps the token

- **WHEN** a user saves a design whose text layer has a case transform and contains `{{name}}`
- **THEN** the stored scene text is `{{name}}` (not uppercased) and the transform property persists

#### Scenario: Reload keeps behavior

- **WHEN** such a scene is reloaded into the editor
- **THEN** the layer shows the raw token text, the transform setting is intact, and rendering still applies the transform
