/** @odoo-module **/

/**
 * Brand asset registries for the social image editor (spec: template
 * editor "Brand assets in the editor", agency-brand-kit for the glue
 * module side).
 *
 * The base social_image_creator module ships near-empty registries: the
 * only default color source reads a handful of brand color fields on
 * res.company IF they exist on the loaded record (none exist natively
 * in Odoo 18 CE, so the brand row simply stays hidden). The agency glue
 * module registers additional providers that inject the social.brand
 * palette and uploaded brand fonts, scoped to the template's brand.
 *
 * Extension point for the glue module:
 *
 *   import {
 *       registerBrandColorProvider,
 *       registerBrandFontProvider,
 *   } from "@social_image_creator/js/dialog/brand_assets";
 *
 *   registerBrandColorProvider((company) => brand.palette.map(...));
 *   registerBrandFontProvider(() => [{name, family}]);
 *
 * Providers run against the raw res.company record the dialog loaded
 * via the ORM, so they must tolerate missing fields. Everything here is
 * pure (no Odoo, no DOM) so it can be unit-tested under plain Node.
 */

const COLOR_PROVIDERS = [];
const FONT_PROVIDERS = [];

/**
 * Candidate res.company fields consulted by the default color source.
 * Only fields actually present on the record are read, so this is a
 * no-op on stock Odoo and picks up fields added by customization or the
 * agency glue module without any change here.
 */
export const COMPANY_BRAND_COLOR_FIELDS = [
    "brand_color",
    "brand_secondary_color",
    "brand_color_accent",
];

export function registerBrandColorProvider(provider) {
    if (typeof provider === "function" && !COLOR_PROVIDERS.includes(provider)) {
        COLOR_PROVIDERS.push(provider);
    }
}

export function registerBrandFontProvider(provider) {
    if (typeof provider === "function" && !FONT_PROVIDERS.includes(provider)) {
        FONT_PROVIDERS.push(provider);
    }
}

/**
 * Normalize a color to lowercase #rrggbb, or null when unparseable.
 * Accepts #rgb, #rrggbb and rgb()/rgba() strings only; anything else is
 * dropped so a broken provider cannot inject garbage into the pickers.
 */
export function normalizeBrandColor(color) {
    if (!color || typeof color !== "string") {
        return null;
    }
    const c = color.trim().toLowerCase();
    if (/^#[0-9a-f]{3}$/.test(c)) {
        return "#" + [...c.slice(1)].map((x) => x + x).join("");
    }
    if (/^#[0-9a-f]{6}$/.test(c)) {
        return c;
    }
    const m = c.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (m) {
        const h = (n) =>
            Math.max(0, Math.min(255, Number(n)))
                .toString(16)
                .padStart(2, "0");
        return `#${h(m[1])}${h(m[2])}${h(m[3])}`;
    }
    return null;
}

// Default provider: known brand color fields on the company record, in
// declaration order. Fields absent from the record (stock Odoo) yield
// nothing, which is the graceful skip.
registerBrandColorProvider((company) =>
    COMPANY_BRAND_COLOR_FIELDS.filter((f) => company && company[f])
        .map((f) => ({ name: f.replace(/_/g, " "), color: company[f] }))
);

/**
 * All brand colors for the loaded company, every provider merged and
 * deduplicated by normalized hex (first provider wins the label).
 *
 * @param {Object} company raw res.company record (or null/undefined)
 * @returns {Array<{name: string, color: string}>}
 */
export function collectBrandColors(company) {
    const seen = new Map();
    for (const provider of COLOR_PROVIDERS) {
        let entries = [];
        try {
            entries = provider(company) || [];
        } catch (_) {
            // A broken provider must not break the editor pickers.
            continue;
        }
        for (const entry of entries) {
            const color = normalizeBrandColor(entry && entry.color);
            if (color && !seen.has(color)) {
                seen.set(color, {
                    name: (entry.name || color).trim(),
                    color,
                });
            }
        }
    }
    return [...seen.values()];
}

/**
 * All registered brand fonts, deduplicated by family. Providers return
 * [{name, family}] entries or bare family strings.
 *
 * @returns {Array<{name: string, family: string}>}
 */
export function collectBrandFonts() {
    const seen = new Map();
    for (const provider of FONT_PROVIDERS) {
        let entries = [];
        try {
            entries = provider() || [];
        } catch (_) {
            continue;
        }
        for (const entry of entries) {
            const family = typeof entry === "string" ? entry : entry && entry.family;
            if (!family || typeof family !== "string") {
                continue;
            }
            if (!seen.has(family)) {
                seen.set(family, {
                    name:
                        typeof entry === "string"
                            ? entry
                            : entry.name || family,
                    family,
                });
            }
        }
    }
    return [...seen.values()];
}

/**
 * Test helper: reset both registries to the base-module state (the
 * default company color provider re-registered).
 */
export function resetBrandAssetRegistriesForTests() {
    COLOR_PROVIDERS.length = 0;
    FONT_PROVIDERS.length = 0;
    registerBrandColorProvider((company) =>
        COMPANY_BRAND_COLOR_FIELDS.filter((f) => company && company[f])
            .map((f) => ({ name: f.replace(/_/g, " "), color: company[f] }))
    );
}
