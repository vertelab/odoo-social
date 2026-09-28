## ADDED Requirements

### Requirement: Binding resolution enforces record access

Before any binding resolution, preview or render against a record, the system SHALL verify the current user has read access to that record (`check_access_rights` and `check_access_rule` on the binding model) and SHALL refuse with a clear error that names the record or model without leaking field values. Every entry point MUST apply this check: editor preview, render wizard, bulk wizard, publish-time rendering and direct model render calls.

#### Scenario: Denied record is refused

- **WHEN** a user without read access to the bound record triggers a preview or render
- **THEN** the operation aborts with a clear access error and no field value is resolved or exposed

#### Scenario: Allowed record resolves normally

- **WHEN** a user with read access triggers the same operation
- **THEN** resolution proceeds and the image renders

### Requirement: Binding traversal enforces access on every hop

When a dotted token path traverses relations, the system SHALL verify read access on each traversed record, including the first record of an x2many traversal, and SHALL refuse with an error naming the token when any hop is unreadable.

#### Scenario: Unreadable related record blocks the token

- **WHEN** a token traverses into a related record the user cannot read
- **THEN** resolution aborts with an error naming the token and no value from that record is exposed

### Requirement: Binding models are curated

The template's binding model SHALL be validated server-side: transient and abstract models MUST be rejected, and an optional administrator-configured allowlist SHALL restrict which models may be bound. The editor's field picker SHALL only offer fields the current user is allowed to read.

#### Scenario: Transient model rejected

- **WHEN** a user saves a template with a transient or abstract binding model
- **THEN** the save is refused with a clear validation error

#### Scenario: Restricted field not offered

- **WHEN** a binding model has a field limited to groups the user does not belong to
- **THEN** the field picker does not list that field
