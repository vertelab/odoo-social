# Spec: render-pipeline

## Purpose

The render pipeline produces final PNG images from template scenes,
identically to the editor preview, via the Node render service.

## ADDED Requirements

### Requirement: Server render matches editor output
Rendering a scene server-side SHALL produce output visually identical to the
editor for all supported features (typography including brand and Google
fonts, gradients, shadows, filters, cover-fit image bindings, conditional
layers). Fabric versions in editor and render service MUST stay in lockstep.

#### Scenario: Font parity
- **WHEN** a template uses an uploaded brand font and is rendered
  server-side
- **THEN** the PNG uses that font (registered server-side), not a fallback

#### Scenario: Filter parity
- **WHEN** a scene contains a grayscale filter and brightness -10 on an
  image layer
- **THEN** the server PNG shows the same adjustments as the editor

### Requirement: Binding values are injected safely
Values substituted into scenes SHALL be treated as plain text. SVG output
MUST XML-escape binding values so markup cannot be injected. PNG output is
raster and inert.

#### Scenario: Markup in value
- **WHEN** a product name contains `<script>alert(1)</script>` and the
  template renders to SVG
- **THEN** the value appears as escaped text and no script executes

### Requirement: Configurable render timing
A rendered image SHALL be producible either when a post is created (so the
approval flow sees the final image) or at publish time, selectable per
render flow. Failed renders MUST NOT publish; the post MUST be flagged with
the error and kept out of the publishing queue.

#### Scenario: Render at creation
- **WHEN** a post is created from a template with render-at-creation
- **THEN** the PNG is generated immediately and attached to the post

#### Scenario: Render failure blocks publish
- **WHEN** the render service is unreachable at publish time
- **THEN** the post is not published and shows a render error

### Requirement: Render service configuration
The render service URL and token SHALL be configured in Settings
(config parameters), never hardcoded. Unauthenticated or wrong-token
requests to the service MUST be rejected.

#### Scenario: Missing configuration
- **WHEN** a render is requested but no service URL is configured
- **THEN** the user gets a clear message pointing to the settings

### Requirement: Rendered images are stored as attachments
Rendered PNGs SHALL be stored as `ir.attachment` records linked to their
post (or template for previews), served through standard Odoo attachment
URLs.

#### Scenario: Attachment serving
- **WHEN** a rendered PNG is attached to a post
- **THEN** `/web/image/<id>` returns the PNG and the post preview shows it
