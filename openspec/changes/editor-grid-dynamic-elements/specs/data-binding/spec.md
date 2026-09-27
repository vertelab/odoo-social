## ADDED Requirements

### Requirement: Chart data cells accept bindings

The binding system SHALL resolve `{{field}}` tokens in chart data cells at render time, using the same path grammar and pipe transforms as text tokens. Non-numeric resolved values in numeric chart cells MUST fall back to the token's raw replacement (zero if unparseable) and MUST NOT abort the render.

#### Scenario: Numeric resolution

- **WHEN** a chart cell contains `{{product.weight}}` and the record's weight is 12.5
- **THEN** the chart plots 12.5 for that cell

#### Scenario: Unparseable value

- **WHEN** a chart cell resolves to a non-numeric string
- **THEN** the cell plots as zero and the render completes

### Requirement: QR content accepts bindings

The binding system SHALL resolve `{{field}}` tokens in QR content at render time and regenerate the QR image from the resolved value.

#### Scenario: Resolved QR

- **WHEN** a QR element's content is `{{product.default_code}}` and the record's SKU is ABC-123
- **THEN** the rendered image contains a QR encoding ABC-123

### Requirement: Insert Dynamic Data uses the binding contract

The Insert Dynamic Data flow SHALL present exactly the models and fields that the binding contract exposes through the template's binding model and field metadata, so tokens inserted through the flow are valid without hand-editing.

#### Scenario: Inserted token is valid

- **WHEN** the user inserts a token through the Insert Dynamic Data flow
- **THEN** the token passes the same validation as hand-written tokens and resolves in preview and render
