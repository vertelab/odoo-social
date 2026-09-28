## ADDED Requirements

### Requirement: The template form shows only meaningful design state

The template form SHALL NOT show the raw variants JSON or the never-written PNG master preview, and the binding model field SHALL prevent creating or opening models from the template form.

#### Scenario: Form without internals

- **WHEN** a user opens a template form
- **THEN** the design section shows the live SVG preview and the editor field, without raw JSON or an empty PNG preview

### Requirement: The template list guides first-time users

When no templates exist, the list SHALL show guidance explaining what an image template is and how to create the first one.

#### Scenario: Empty list explains the feature

- **WHEN** a user opens Image Studio with no templates
- **THEN** an empty-state message explains templates and points to the create action
