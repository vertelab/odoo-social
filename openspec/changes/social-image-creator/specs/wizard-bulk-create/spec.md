# Spec: wizard-bulk-create

## Purpose

Turning records into posts with rendered images: one wizard on the post
form for a single record, one bulk action on any list view for many.

## ADDED Requirements

### Requirement: Single-post image wizard
From a post (or template), a wizard SHALL let the user pick a template
compatible with the intended record, pick the record of the template's
binding model, preview the rendered result, and create the image.

#### Scenario: Create image for a post
- **WHEN** a user on a post clicks "Create Image from Template", picks the
  "Sommar-Rea" template and a product, and confirms
- **THEN** the rendered PNG is attached to the post's images and visible in
  the post preview

### Requirement: Bulk action from list views
Any list view of a model SHALL offer "Create Posts from Image Template" on
the action menu using the selected records (`active_ids`). The wizard SHALL
validate that the chosen template's binding model matches the source model
and SHALL create one draft post per selected record, each with its own
rendered image.

#### Scenario: Bulk create from 53k product database
- **WHEN** a user filters products to 54 rows, selects all, and runs the
  action with a product-bound template
- **THEN** 54 draft posts are created, each with the image rendered from
  that product's data

#### Scenario: Model mismatch
- **WHEN** the user runs the action on contacts but picks a
  product-bound template
- **THEN** the wizard rejects the combination before creating anything

### Requirement: Draft posts join the planner flow
Posts created by the wizard or bulk action SHALL be created as drafts and
MUST be schedulable through the standard planner (calendar slots, approval
flow), unchanged. The image creator SHALL NOT implement scheduling itself.

#### Scenario: Schedule bulk-created posts
- **WHEN** 54 draft posts exist and a planner user assigns them to
  Monday/Wednesday/Friday slots
- **THEN** the standard planner scheduling applies, images included

### Requirement: Bulk creation is safe to retry
Bulk creation SHALL be transactional per post: one record failing to render
MUST NOT roll back the other posts. The result MUST report created posts
and failures individually.

#### Scenario: Partial failure
- **WHEN** 3 of 54 records fail to render (e.g. missing required image)
- **THEN** 51 posts exist, and the wizard lists the 3 failed records with
  reasons
