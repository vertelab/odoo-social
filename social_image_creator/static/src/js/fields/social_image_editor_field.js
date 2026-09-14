/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { SocialImageEditorDialog } from "@social_image_creator/js/dialog/social_image_editor_dialog";

/**
 * Launcher for the full-screen image editor (design decision D4).
 *
 * The widget no longer hosts the editor inline. It renders an SVG master
 * preview (when one exists) plus an "Edit Design" button that opens
 * SocialImageEditorDialog through the dialog service. The dialog owns
 * editing, history and autosave and writes back to the saved record.
 *
 * The editor targets a saved record (variants are persisted on it), so
 * the button is disabled while the record is new/unsaved.
 */
export class SocialImageEditorField extends Component {
    static template = "social.SocialImageEditorField";
    static props = { ...standardFieldProps };

    setup() {
        this.dialogService = useService("dialog");
    }

    get isNew() {
        return !this.props.record.resId;
    }

    get previewSrc() {
        const data = this.props.record.data.svg_master;
        return data ? `data:image/svg+xml;base64,${data}` : null;
    }

    openEditor() {
        if (this.isNew) {
            return;
        }
        this.dialogService.add(SocialImageEditorDialog, {
            resModel: this.props.record.resModel,
            resId: this.props.record.resId,
        });
    }
}

SocialImageEditorField.props = { ...standardFieldProps };

export const socialImageEditorField = {
    component: SocialImageEditorField,
};

registry.category("fields").add("social_image_editor", socialImageEditorField);
