## ADDED Requirements

### Requirement: Brand fonts are limited to entitled groups

Reading a brand font SHALL require membership in the marketing user or manager groups or in the brand's entitled customer groups. A plain internal user without those groups SHALL NOT read or download brand font binaries.

#### Scenario: Plain internal user denied

- **WHEN** an internal user without marketing or customer groups tries to read a brand font
- **THEN** access is denied

#### Scenario: Entitled customer reads own brand font

- **WHEN** a customer group user of the brand opens the brand kit
- **THEN** the brand's fonts load in the editor as before

### Requirement: Font uploads are content-validated

A font upload SHALL be validated by magic bytes (TTF, OTF, WOFF or WOFF2 signatures) in addition to the existing extension and size limits, and SHALL be rejected with a clear error when the content is not a font.

#### Scenario: Renamed non-font rejected

- **WHEN** a user uploads a non-font file named with a .ttf extension
- **THEN** the save is refused with a clear validation error
