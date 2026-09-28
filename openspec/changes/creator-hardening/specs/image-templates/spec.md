## ADDED Requirements

### Requirement: Templates are company-scoped

A marketing user SHALL only see templates belonging to their companies (or with no company); the marketing manager group SHALL see all templates regardless of company. The rule MUST apply to read, write and unlink.

#### Scenario: Cross-company template hidden

- **WHEN** a user in company A lists image templates and company B owns a template
- **THEN** the company B template is not visible or accessible to that user

#### Scenario: Manager sees all

- **WHEN** a marketing manager lists image templates
- **THEN** templates of all companies are visible

### Requirement: Preview attachments do not accumulate

At most one live preview attachment SHALL exist per template at any time, and a scheduled cleanup SHALL remove leftover preview attachments daily. The render wizard SHALL NOT offer a manual refresh button that reloads the whole dialog.

#### Scenario: Repeated previews keep one attachment

- **WHEN** a user triggers two previews in a row for the same template
- **THEN** only the most recent preview attachment exists

#### Scenario: Leftovers are cleaned

- **WHEN** the scheduled cleanup runs and preview attachments older than 24 hours exist
- **THEN** those attachments are removed

### Requirement: Menus group the studio

The module's menus SHALL be grouped under a parent menu named "Image Studio" containing Templates, and Image Sizes SHALL live under Configuration.

#### Scenario: Top-level structure

- **WHEN** a user opens the Social Marketing app menu
- **THEN** the top level shows Feed, Posts, Image Studio and Configuration, with Image Sizes under Configuration
