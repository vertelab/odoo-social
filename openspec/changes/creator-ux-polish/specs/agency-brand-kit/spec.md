## ADDED Requirements

### Requirement: Palette input is validated with friendly errors

The brand palette field SHALL accept only a JSON list of hex color strings and SHALL reject anything else with a clear, user-facing validation error instead of a traceback.

#### Scenario: Typo gets a friendly error

- **WHEN** a user saves a palette with invalid JSON or a non-hex entry
- **THEN** the save is refused with a message explaining the expected format with an example

#### Scenario: Valid palette accepted

- **WHEN** a user saves a well-formed list of hex colors
- **THEN** the palette stores and the editor swatches show the colors as before
