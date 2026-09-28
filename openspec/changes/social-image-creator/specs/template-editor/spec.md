# Spec: template-editor

## Purpose

The template editor is a full workspace for composing image designs: layers,
objects, typography, effects and alignment, at parity with the proven
render-engine-os editor.

## ADDED Requirements

### Requirement: Editor opens in a modal workspace
The editor SHALL open in a modal dialog large enough for canvas, layer
panel and properties panel side by side, launched from the template form.
Canvas display SHALL be scaled to fit while keeping pixel dimensions exact.

#### Scenario: Open editor
- **WHEN** a user clicks "Edit Design" on a template
- **THEN** the modal opens with the canvas at the variant's exact pixel
  size, display-scaled to fit

### Requirement: Layer panel controls the scene
The editor SHALL provide a layer panel listing all objects with: selection,
drag reorder, rename (double-click), visibility toggle, lock toggle,
duplicate and delete. Reordering SHALL change z-order.

#### Scenario: Toggle layer visibility
- **WHEN** a user clicks the eye icon on a text layer
- **THEN** the layer is hidden on canvas and excluded from render output

#### Scenario: Locked layer
- **WHEN** a user locks a background image layer
- **THEN** it cannot be selected or moved until unlocked

### Requirement: History and autosave
The editor SHALL support undo and redo of canvas changes (bounded history)
and SHALL autosave the scene with a short debounce after changes. Closing
the editor SHALL flush pending changes.

#### Scenario: Undo text deletion
- **WHEN** a user deletes a text layer and presses Ctrl+Z
- **THEN** the layer reappears in its previous position and style

#### Scenario: Autosave on pause
- **WHEN** a user stops editing for the debounce interval
- **THEN** the scene is saved without further user action

### Requirement: Object toolbox
The editor SHALL support adding: text boxes, rectangle (with corner
radius), circle, triangle, line, arrow, a library of path-based shapes,
parametric shapes (polygon, star, burst with adjustable parameters),
freehand polygon via a pen tool, raster images, SVG graphics (recolorable)
and a searchable icon library.

#### Scenario: Add and morph a star
- **WHEN** a user adds a star shape and changes the points slider to 6
- **THEN** the shape updates live while position and size are preserved

#### Scenario: Insert icon
- **WHEN** a user searches "heart" in the icon picker and inserts a result
- **THEN** a recolorable SVG heart appears on the canvas

### Requirement: Typography controls
Text objects SHALL support: font family (including brand fonts), size,
bold, italic, underline, color, alignment, line height, character spacing,
case transform (upper/lower) and autofit overflow (shrink to fit width).
Font lists SHALL be searchable.

#### Scenario: Autofit long product name
- **WHEN** a bound product name exceeds the text box at render time
- **THEN** the rendered text shrinks to fit, matching the editor preview

### Requirement: Effects and styling
Objects SHALL support: fill color, two-stop linear or radial gradients,
stroke with solid/dashed/dotted style and width, drop shadow (color,
alpha, blur, offset), opacity, and raster image adjustments (brightness,
contrast, blur, grayscale). A shape SHALL be fillable with an image
(clipped to the shape) with a reversible "back to color" action.

#### Scenario: Gradient fill
- **WHEN** a user applies a 45-degree two-stop gradient to a rectangle
- **THEN** the gradient renders identically in the editor and in the
  server-rendered PNG

### Requirement: Alignment, snapping and grouping
The editor SHALL snap objects to canvas edges, canvas center and other
objects, with visual guides and smart-spacing indicators; provide
align/distribute for multi-selection; and support group/ungroup with
standard keyboard shortcuts.

#### Scenario: Snap to center
- **WHEN** a user drags a logo near the horizontal canvas center
- **THEN** a guide line appears and the object snaps to the center line

### Requirement: Brand assets in the editor
Users SHALL be able to pick brand colors from the brand palette and insert
brand logos/images from the media library, scoped to the template's
company (and brand, when the agency glue module is installed).

#### Scenario: Pick brand color
- **WHEN** a user opens the color picker on a shape fill
- **THEN** the brand palette is offered alongside the free color picker

### Requirement: Live data preview
When the template has a binding model, the editor SHALL offer a preview
mode that renders text and image layers with real record data, with a
record switcher, and SHALL restore the token view afterwards.

#### Scenario: Preview with record
- **WHEN** a user enables preview mode and picks a product
- **THEN** `{{name}}` layers show the product name and image bindings show
  the product image
