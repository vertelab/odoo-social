# Spec: image-templates

## Purpose

Image templates are reusable, multi-size designs that produce social and Open
Graph images inside Odoo, replacing external tools like Canva or Photoshop.

## ADDED Requirements

### Requirement: Templates are managed in a dedicated module
Templates SHALL live in the `social_image_creator` module (migrated from
`social_marketing`) and SHALL be manageable through standard Odoo views
(list, form, kanban with thumbnail) by users with the corresponding access
rights.

#### Scenario: Open template list
- **WHEN** a user opens Social Marketing, Image Templates
- **THEN** the user sees all templates they have access to, with name,
  thumbnail, size and binding model

#### Scenario: Access control
- **WHEN** a user without template edit rights opens a template form
- **THEN** the editor is read-only and save actions are unavailable

### Requirement: A template declares its binding model
Each template SHALL declare exactly one Odoo model (`model_id`, e.g.
`product.template`) that its dynamic tokens resolve against. The model
SHALL be changeable only while no bindings depend on fields that do not
exist on the new model, and the system MUST warn when switching would
invalidate existing tokens.

#### Scenario: Create a product template
- **WHEN** a user creates a template and selects `product.template` as
  binding model
- **THEN** token insertion offers product fields (name, list_price, image)

#### Scenario: Switch binding model with stale tokens
- **WHEN** a user switches the binding model and existing text layers
  reference fields missing on the new model
- **THEN** the system lists the affected layers and requires confirmation

### Requirement: Templates support multiple size variants
A template SHALL hold one or more named variants, each with its own canvas
size and scene (e.g. "Instagram Square" 1080x1080 and "LinkedIn Post"
1200x627). One variant SHALL be primary. Deleting the last remaining
variant MUST be rejected. Adding a variant MAY copy an existing variant's
scene scaled to the new size.

#### Scenario: Add a variant from existing scene
- **WHEN** a user adds a 1080x1920 Story variant copying the 1080x1080 scene
- **THEN** a new variant is created with all object positions, sizes and
  font sizes scaled by the size ratio

#### Scenario: Refuse to delete the only variant
- **WHEN** a template has exactly one variant and the user deletes it
- **THEN** the system rejects the action with a clear message

### Requirement: Size presets are user-extensible
The system SHALL ship standard size presets as data (Open Graph, Facebook,
Instagram square/portrait/story, LinkedIn post, X post). Users with
configuration rights SHALL be able to add, rename and archive custom sizes.
Presets MUST supply width, height and platform label.

#### Scenario: Use a preset for a new variant
- **WHEN** a user creates a variant and picks "LinkedIn Post"
- **THEN** the variant canvas is set to 1200x627

#### Scenario: Add a custom size
- **WHEN** an admin creates a size "Banderoll" 2500x800
- **THEN** the size appears in the variant creation picker for all users

### Requirement: Templates store scene and masters
Each variant SHALL persist its Fabric scene JSON and a generated SVG master.
Saving a scene SHALL regenerate the SVG master automatically.

#### Scenario: Save template
- **WHEN** a user saves a template in the editor
- **THEN** the scene JSON and the SVG master attachment are both updated
