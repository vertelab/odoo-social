/** @odoo-module **/

/**
 * Font data + lazy Google Fonts loading for the social image editor,
 * ported from render-engine-os (ui/src/data/googleFonts.js, design D11).
 * Browser-only: everything touching document lives inside functions that
 * the dialog calls at runtime, so the module stays importable in Node.
 */

/**
 * Curated Google Fonts list, ~80 popular families. Weights 400 and 700 are
 * requested in the single CSS link; browsers fetch woff2 files lazily per
 * glyph render.
 */
export const GOOGLE_FONTS = [
    // Sans-serif workhorses
    "Roboto", "Open Sans", "Noto Sans", "Montserrat", "Lato", "Poppins",
    "Inter", "Roboto Condensed", "Source Sans 3", "Oswald", "Raleway",
    "PT Sans", "Ubuntu", "Nunito", "Mukta", "Rubik", "Work Sans",
    "Quicksand", "Heebo", "Fira Sans", "Cabin", "Titillium Web", "Karla",
    "Josefin Sans", "Mulish", "Lexend", "Manrope", "DM Sans", "Outfit",
    "Plus Jakarta Sans", "Sora", "Urbanist", "Albert Sans", "Hind",

    // Display / impact
    "Anton", "Bebas Neue", "Dosis", "Yanone Kaffeesatz", "Archivo Black",
    "Russo One", "Black Ops One", "Bungee", "Fjalla One", "Staatliches",

    // Serif
    "Roboto Slab", "Merriweather", "PT Serif", "Playfair Display",
    "Lora", "Crimson Text", "Libre Baskerville", "Bitter", "Arvo",
    "Source Serif 4", "Cinzel", "Cormorant Garamond", "EB Garamond",
    "Vollkorn", "DM Serif Display", "IBM Plex Serif", "Noto Serif",

    // Monospace
    "Roboto Mono", "IBM Plex Mono", "Source Code Pro", "Fira Code",
    "JetBrains Mono", "Space Mono", "Inconsolata", "Courier Prime",
    "Ubuntu Mono", "DM Mono",

    // Script / handwritten
    "Dancing Script", "Pacifico", "Permanent Marker", "Lobster",
    "Indie Flower", "Shadows Into Light", "Caveat", "Satisfy",
    "Great Vibes", "Sacramento", "Kalam", "Architects Daughter",
    "Amatic SC", "Comfortaa",
];

/**
 * System fonts offered alongside the Google Fonts list, no loading needed.
 */
export const SYSTEM_FONTS = [
    "Arial",
    "Georgia",
    "Verdana",
    "Tahoma",
    "Trebuchet MS",
    "Times New Roman",
    "Courier New",
];

export function isGoogleFont(family) {
    return GOOGLE_FONTS.includes(family);
}

const LINK_ID = "social-image-creator-google-fonts";

/**
 * Inject one <link> tag containing every curated family at weight 400 and
 * 700. Returns a Promise that resolves once the CSS has loaded (not the
 * woff2 files themselves). Fail-soft: on error the preview falls back to
 * system fonts.
 */
export function loadAllGoogleFontsCss() {
    if (typeof document === "undefined") {
        return Promise.resolve();
    }
    if (document.getElementById(LINK_ID)) {
        return Promise.resolve();
    }
    return new Promise((resolve) => {
        const link = document.createElement("link");
        link.id = LINK_ID;
        link.rel = "stylesheet";
        const families = GOOGLE_FONTS.map(
            (f) => `family=${encodeURIComponent(f)}:wght@400;700`
        ).join("&");
        link.href = `https://fonts.googleapis.com/css2?${families}&display=swap`;
        link.onload = () => resolve();
        link.onerror = () => resolve();
        document.head.appendChild(link);
    });
}

/**
 * Wait for a specific family's actual font file to be ready in the
 * document. Called after picking a font so Fabric renders with the real
 * glyphs instead of a fallback.
 */
export async function ensureFontLoaded(family) {
    if (!family || !isGoogleFont(family)) {
        return;
    }
    await loadAllGoogleFontsCss();
    if (typeof document !== "undefined" && typeof document.fonts?.load === "function") {
        try {
            await document.fonts.load(`16px "${family}"`);
        } catch (_) {
            // Fail-soft: Fabric renders with a fallback until the file arrives.
        }
    }
}
