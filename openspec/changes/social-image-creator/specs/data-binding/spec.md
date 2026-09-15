# Spec: data-binding

## Purpose

Data binding connects template layers to fields on real Odoo records so one
template renders personalised images for any record of its binding model.

## ADDED Requirements

### Requirement: Tokens reference record fields
Text layers SHALL support `{{field}}` tokens resolved against the record
chosen at render time, where `field` is a field of the template's binding
model. Nested paths across relations (e.g. `{{categ_id.name}}`) SHALL be
supported for readable (non-computed x2many) relations. Token insertion
SHALL be offered as a field picker so users need not memorise field names.

#### Scenario: Insert a field token
- **WHEN** a user clicks a field chip in the Data panel with a text layer
  selected
- **THEN** the token is inserted at the cursor as `{{list_price}}`

#### Scenario: Resolve nested field
- **WHEN** a scene contains `{{categ_id.name}}` and the record's category
  is "Chairs"
- **THEN** the rendered image contains "Chairs"

### Requirement: Pipe transforms on tokens
Tokens SHALL support chained pipe transforms, at minimum: `upper`, `lower`,
`title`, `capitalize`, `trim`.

#### Scenario: Uppercase transform
- **WHEN** a layer contains `{{name|upper}}` and the record name is "Stol"
- **THEN** the rendered text is "STOL"

### Requirement: Conditional layers
Any layer SHALL be able to declare a hide-if-empty rule bound to a field or
token: when the resolved value is empty, the layer MUST be excluded from
render output.

#### Scenario: Hide empty badge
- **WHEN** a "New!" badge layer is bound to hide-if-empty on `is_new` and
  the record's `is_new` is false
- **THEN** the badge does not appear in the rendered image

### Requirement: Image layers bind to record fields
Image layers SHALL be bindable to binary/image fields or attachment fields
of the binding model (e.g. `{{image_1920}}`). The bound image SHALL be
fitted to the layer's frame with cover semantics in both editor preview and
server render, so visual output matches.

#### Scenario: Bound product image
- **WHEN** an image layer is bound to `image_1920` on a product record
- **THEN** the rendered image fills the layer frame with cover fit,
  cropping overflow consistently in editor and server output

### Requirement: Empty binding handling
When a bound field resolves to empty for the chosen record, text tokens
SHALL render as empty strings and bound images SHALL hide the layer unless
the layer is explicitly marked required; required layers with empty
bindings MUST abort the render with a clear error naming the layer.

#### Scenario: Required binding missing
- **WHEN** a layer is marked required, bound to `sale_ok` which is empty
  for the record
- **THEN** rendering is aborted and the user is told which layer failed
