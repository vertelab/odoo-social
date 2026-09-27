## ADDED Requirements

### Requirement: Grid overlay with toolbar toggle

The editor SHALL provide a grid overlay on the canvas that the user can toggle from the toolbar. The grid spacing SHALL be configurable (spacing in pixels, e.g. 8, 16, 32, 64). The grid SHALL be a view aid only: it MUST NOT appear in exported PNG/SVG output or in the rendered post images. The toggle state and spacing SHALL persist per template session and SHOULD persist per user.

#### Scenario: Toggle grid on and off

- **WHEN** the user activates the grid toggle in the toolbar
- **THEN** the canvas shows the grid overlay at the configured spacing without affecting the scene content, and deactivating the toggle hides it again

#### Scenario: Export is clean

- **WHEN** the user exports or saves a design while the grid is visible
- **THEN** the exported image and the server-rendered output contain no grid lines

### Requirement: Snap to grid

When the grid is visible, the user SHALL be able to enable snap-to-grid for moving and resizing objects. Snap-to-grid SHALL be a separate toggle from the grid overlay. When enabled, object positions and sizes snap to the nearest grid intersection during move and resize. Smart guides (object-to-object snapping) keep priority: when both would apply, the guide snap wins because it is the closer candidate.

#### Scenario: Move snaps to intersections

- **WHEN** snap-to-grid is enabled and the user drags an object near a grid intersection
- **THEN** the object origin snaps to the intersection instead of the raw pointer position

#### Scenario: Guides take priority

- **WHEN** snap-to-grid is enabled and a smart guide candidate is within the guide threshold
- **THEN** the object snaps to the guide position, not the grid intersection

### Requirement: Insert Dynamic Data flow

The editor SHALL provide a toolbar button labeled "Insert Dynamic Data" that opens a focused step-by-step flow. Step 1 SHALL offer the binding models available on the template. Step 2 SHALL offer the bindable fields of the chosen model. The final step SHALL let the user insert the selected field as a `{{field}}` text token into the active text layer or into a new text layer, or bind it to the active image layer. The flow MUST reuse the template's configured binding model and field metadata, and MUST NOT require leaving the dialog.

#### Scenario: Insert a text token

- **WHEN** the user picks a model and a field and chooses text insertion with no active text layer
- **THEN** a new text layer containing the `{{field}}` token is added at the canvas center

#### Scenario: Bind an image layer

- **WHEN** the user picks a binary field while an image layer is active
- **THEN** the image layer receives the field binding and preview/render resolves it per record

#### Scenario: Template has no binding model

- **WHEN** the user opens Insert Dynamic Data on a template without a binding model
- **THEN** step 1 offers to set one, and the flow continues once a model is chosen

### Requirement: Table element

The editor SHALL offer a table element: a group of cells with configurable rows and columns, inserted with a chosen width. The user MUST be able to edit cell text after insertion, and the table MUST persist through save/load round-trips as one layer. Row and column counts SHOULD be adjustable after insertion by adding or removing rows/columns while preserving entered cell text.

#### Scenario: Insert a table

- **WHEN** the user chooses the table element and confirms rows, columns and width
- **THEN** a table layer with evenly sized cells appears at the canvas center as a single layer in the panel

#### Scenario: Edit cell text

- **WHEN** the user double-clicks a cell
- **THEN** the cell text can be edited in place and the change is part of the table layer

#### Scenario: Round-trip

- **WHEN** the design containing a table is saved and reloaded
- **THEN** the table restores with cell text and structure intact as one layer

### Requirement: Chart element

The editor SHALL offer a chart element backed by an embedded data table with named series and categories. Chart types at launch: vertical bar, horizontal bar, line, area, pie and donut. The user MUST be able to edit the data table after insertion. Each data cell MAY hold a static value or a `{{field}}` token. The chart MUST render as vector objects in the editor and MUST render equivalently server-side for record-bound cells.

#### Scenario: Insert a chart

- **WHEN** the user chooses a chart type and confirms a starter data table
- **THEN** a chart layer appears at the canvas center and the data table can be reopened for editing

#### Scenario: Bound cells resolve per record

- **WHEN** a template with a chart containing `{{field}}` cells is rendered for a record
- **THEN** the server-rendered chart shows the record's values in place of the tokens

#### Scenario: Round-trip

- **WHEN** the design containing a chart is saved and reloaded
- **THEN** the chart data table and type restore intact as one layer

### Requirement: QR element

The editor SHALL offer a QR code element whose content is a text or URL value. The content MAY be static or a `{{field}}` token resolved per record at render time. The QR MUST be scannable in exported and rendered output.

#### Scenario: Insert a static QR

- **WHEN** the user enters content and confirms
- **THEN** a QR layer appears at the canvas center and scans to the entered content in export

#### Scenario: Bound QR resolves per record

- **WHEN** a template with a QR bound to a field is rendered for a record
- **THEN** the rendered image contains a QR encoding the record's value

#### Scenario: Invalid content

- **WHEN** the user enters content that cannot be encoded
- **THEN** the editor shows an inline error and does not insert the element
