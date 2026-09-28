## ADDED Requirements

### Requirement: Bulk creation is reachable from record lists

For every model bound by at least one image template, an action named "Create Posts from Image Template" SHALL appear in that model's list view Action menu, and invoking it with selected records SHALL open the bulk wizard populated with those records. The action SHALL disappear when no template binds the model anymore.

#### Scenario: Action menu offers bulk creation

- **WHEN** a user selects records of a bound model in a list view and opens the Action menu
- **THEN** "Create Posts from Image Template" is available and opens the bulk wizard with the selection

#### Scenario: Action removed with the last template

- **WHEN** the last template bound to a model is deleted or re-bound to another model
- **THEN** the action for that model no longer appears
