## ADDED Requirements

### Requirement: Closing the editor never silently discards work

When the editor dialog is closed while unsaved changes exist or a save is in flight or failing, the dialog SHALL block closing, tell the user what happened and offer to retry; work SHALL only be lost if the user explicitly discards it.

#### Scenario: Failed save blocks close

- **WHEN** the user closes the editor and the final save fails
- **THEN** the dialog stays open with a clear error and a retry affordance, and the edits remain

#### Scenario: Successful save closes cleanly

- **WHEN** the user closes the editor and the final save succeeds
- **THEN** the dialog closes without prompting

### Requirement: The editor is keyboard reachable

The editor SHALL support Delete/Backspace to remove the active selection, Escape to close open pickers first and then the dialog, visible focus styles on layer action buttons, and real focusable buttons with accessible names for the image and SVG upload controls.

#### Scenario: Delete removes the selection

- **WHEN** a layer is selected and the user presses Delete
- **THEN** the layer is removed and the change is undoable

#### Scenario: Escape unwinds focus

- **WHEN** a picker is open and the user presses Escape
- **THEN** the picker closes first, and a second Escape closes the dialog (subject to the close-safety rule)

#### Scenario: Focus reveals layer actions

- **WHEN** the user tabs to a layer row
- **THEN** its action buttons become visible without hovering

### Requirement: The editor UI is translatable

Every user-facing string in the editor JavaScript and templates SHALL be translatable through Odoo's translation machinery, and the Swedish catalog SHALL cover the current editor strings.

#### Scenario: Editor in Swedish

- **WHEN** a user switches the interface language to Swedish
- **THEN** the editor toolbar, panels and messages render in Swedish
