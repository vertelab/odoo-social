# Spec: agency-brand-kit

## Purpose

Agency support: templates and brand assets scoped to `social.brand`, so an
agency managing a company with several brands keeps designs and assets
separated per brand.

## ADDED Requirements

### Requirement: Brand scoping on templates
With the agency glue module installed, templates SHALL carry an optional
`brand_id` (social.brand). Users SHALL only see templates of brands they
have access to, enforced by record rules consistent with the existing
brand-scoping of customer data.

#### Scenario: Brand isolation
- **WHEN** a customer user of brand A opens the template list
- **THEN** only brand A (and unbranded company-level) templates are visible

### Requirement: Brand kit on the brand
A brand SHALL hold a kit of: color palette (beyond the existing single
brand color), uploaded fonts (registered for server rendering), and logo
image assets, all manageable from the brand form and offered in the editor.

#### Scenario: Add a brand font
- **WHEN** an agency user uploads "BrandonGrotesque-Bold.ttf" to the brand
- **THEN** the font appears in the editor font picker and renders
  correctly in server-rendered images

#### Scenario: Brand palette in editor
- **WHEN** a user edits a template of brand A
- **THEN** brand A's palette (not brand B's) is offered in color pickers

### Requirement: Template binding to brand customer data
When a template is scoped to a brand, record selection for binding SHALL be
limited to that brand's customer scope where the binding model supports it;
otherwise the full company scope applies.

#### Scenario: Select record within brand scope
- **WHEN** a brand-scoped template binds to a brand-scoped model
- **THEN** the record picker shows only the brand's records
