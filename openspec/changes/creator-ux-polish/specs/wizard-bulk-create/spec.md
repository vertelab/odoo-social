## ADDED Requirements

### Requirement: Variant selection uses names

Both the render wizard and the bulk wizard SHALL let the user choose a template variant by its name as shown in the template, not by a numeric index.

#### Scenario: Pick variant by name

- **WHEN** a user renders from a template with variants "Post" and "Story"
- **THEN** the wizard offers "Post" and "Story" in a selection, and the render uses the chosen variant

#### Scenario: Single variant needs no choice

- **WHEN** the template has only the primary variant
- **THEN** the wizard preselects it without asking for an index
