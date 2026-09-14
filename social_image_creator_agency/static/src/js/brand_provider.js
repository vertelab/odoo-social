/** @odoo-module **/

/**
 * Agency glue for the social image editor (spec: agency-brand-kit).
 *
 * Injects the template's social.brand kit into the editor through the
 * registries of @social_image_creator/js/dialog/brand_assets.js: the brand
 * palette becomes brand color swatches, the uploaded brand fonts become
 * font picker entries (and are loaded into the document so the canvas can
 * render them). Brand data is fetched through the ORM in the patched
 * _loadBrandContext; the providers registered below read the latest fetch,
 * so collectBrandColors / collectBrandFonts pick everything up through
 * the same extension point any other module would use.
 *
 * Also constrains the editor's live-preview record search to the
 * template's brand scope via social.image.template.get_binding_domain().
 * Everything is fail-soft: any ORM error leaves the base editor behavior
 * untouched.
 */

import { patch } from "@web/core/utils/patch";
import { SocialImageEditorDialog } from "@social_image_creator/js/dialog/social_image_editor_dialog";
import {
    collectBrandColors,
    collectBrandFonts,
    registerBrandColorProvider,
    registerBrandFontProvider,
} from "@social_image_creator/js/dialog/brand_assets";

// Latest fetched brand kit, read by the providers below. Reset on every
// brand context load so a template switch never leaks the previous brand.
let brandKit = { colors: [], fonts: [] };

registerBrandColorProvider(() => brandKit.colors);
registerBrandFontProvider(() => brandKit.fonts);

function resetBrandKit() {
    brandKit = { colors: [], fonts: [] };
}

/**
 * Load each brand font into document.fonts from its stored attachment so
 * the Fabric canvas can render it. A font that fails to load is skipped;
 * the rest of the editor works.
 *
 * @param {Object} orm
 * @param {Array<{id: number, name: string}>} fonts
 */
async function loadBrandFontFaces(orm, fonts) {
    for (const font of fonts) {
        try {
            const [attachment] = await orm.search_read(
                "ir.attachment",
                [
                    ["res_model", "=", "social.brand.font"],
                    ["res_id", "=", font.id],
                    ["res_field", "=", "file"],
                ],
                ["id"],
                { limit: 1 }
            );
            if (!attachment) {
                continue;
            }
            const face = new FontFace(
                font.name,
                `url(/web/content/${attachment.id})`
            );
            await face.load();
            document.fonts.add(face);
        } catch (_) {
            // Single font failure must not break the editor load.
        }
    }
}

patch(SocialImageEditorDialog.prototype, {
    /**
     * Extend the brand context load with the template's brand kit: palette
     * colors and uploaded fonts, fetched through the ORM. Also stashes the
     * template's brand binding domain for the preview record search.
     *
     * @param {Object} record the template record as read in _init
     */
    async _loadBrandContext(record) {
        await super._loadBrandContext(record);
        resetBrandKit();
        this._brandId = null;
        this._bindingBrandDomain = [];
        try {
            const [template] = await this.orm.read(
                this.props.resModel,
                [this.props.resId],
                ["brand_id"]
            );
            this._brandId =
                template && template.brand_id ? template.brand_id[0] : null;
            if (!this._brandId) {
                return;
            }
            const [brand] = await this.orm.read(
                "social.brand",
                [this._brandId],
                ["palette", "font_ids"]
            );
            const palette = (brand && brand.palette) || [];
            brandKit.colors = palette
                .filter((color) => typeof color === "string")
                .map((color) => ({ name: color, color }));
            const fontIds = (brand && brand.font_ids) || [];
            if (fontIds.length) {
                const fonts =
                    (await this.orm.read("social.brand.font", fontIds, [
                        "name",
                    ])) || [];
                brandKit.fonts = fonts.map((font) => ({
                    name: font.name,
                    family: font.name,
                }));
                await loadBrandFontFaces(this.orm, fonts);
            }
            this._bindingBrandDomain = await this._fetchBindingBrandDomain();
        } catch (_) {
            resetBrandKit();
        }
        // Re-run the collectors so the providers above contribute; the
        // base implementation already ran them with an empty kit.
        this.state.brandColors = collectBrandColors(this._company);
        this.state.brandFonts = collectBrandFonts();
    },

    /**
     * Brand scope for the preview record picker, from the server so the
     * brand_id detection lives in one place (the binding model may or may
     * not be brand-scoped).
     */
    async _fetchBindingBrandDomain() {
        if (!this._brandId) {
            return [];
        }
        try {
            return (
                (await this.orm.call(
                    "social.image.template",
                    "get_binding_domain",
                    [[this.props.resId]]
                )) || []
            );
        } catch (_) {
            return [];
        }
    },

    /**
     * Preview record picker: same as the base implementation, but the
     * name_search is limited to the template's brand scope when the
     * binding model carries a brand_id.
     */
    async _searchPreviewRecords(term) {
        if (!this.state.bindingModelName) {
            this.state.previewResults = [];
            return;
        }
        try {
            const results = await this.orm.call(
                this.state.bindingModelName,
                "name_search",
                [term || ""],
                { limit: 20, domain: this._bindingBrandDomain || [] }
            );
            this.state.previewResults = (results || []).map(([id, name]) => ({
                id,
                name,
            }));
        } catch (err) {
            this.state.previewResults = [];
            this.state.message = `Record search failed: ${err.message || err}`;
        }
    },
});
