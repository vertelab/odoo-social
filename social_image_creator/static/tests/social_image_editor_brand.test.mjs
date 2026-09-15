// Node smoke test for the icon library search and the brand asset
// registries (spec: template editor "Object toolbox" icons and
// "Brand assets in the editor").
// Run: node social_image_creator/static/tests/social_image_editor_brand.test.mjs

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

function importAsMjs(relSource, tmpName) {
    const source = readFileSync(join(here, relSource), "utf8");
    const tmp = join("/tmp", tmpName);
    writeFileSync(tmp, source);
    return import(tmp);
}

const icons = await importAsMjs(
    "../src/js/dialog/icon_library.js",
    "social_image_editor_icons.smoke.mjs"
);
const brand = await importAsMjs(
    "../src/js/dialog/brand_assets.js",
    "social_image_editor_brand.smoke.mjs"
);
const utils = await importAsMjs(
    "../src/js/dialog/social_image_editor_utils.js",
    "social_image_editor_utils_brand.smoke.mjs"
);

let failures = 0;
function check(name, actual, expected) {
    const ok = JSON.stringify(actual) === JSON.stringify(expected);
    if (!ok) {
        failures += 1;
        console.error(
            `FAIL ${name}: got ${JSON.stringify(actual)}, want ${JSON.stringify(expected)}`
        );
    } else {
        console.log(`ok ${name}`);
    }
}
function checkTrue(name, cond) {
    if (!cond) {
        failures += 1;
        console.error(`FAIL ${name}`);
    } else {
        console.log(`ok ${name}`);
    }
}

// ------------------------------------------------------------------
// Icon library: catalog integrity
// ------------------------------------------------------------------

checkTrue("library is non-trivial", icons.ICON_LIBRARY.length > 400);
const names = new Set();
for (const icon of icons.ICON_LIBRARY) {
    checkTrue(`icon ${icon.name} unique`, !names.has(icon.name));
    names.add(icon.name);
    checkTrue(`icon ${icon.name} has tags`, Array.isArray(icon.tags) && icon.tags.length > 0);
    checkTrue(`icon ${icon.name} has body markup`, icon.body.startsWith("<") && icon.body.includes("/>") || icon.body.includes("</"));
    checkTrue(`icon ${icon.name} body has no outer svg`, !icon.body.startsWith("<svg"));
}
for (const known of ["heart", "star", "camera", "arrow-up", "check"]) {
    checkTrue(`known icon ${known} present`, names.has(known));
}
checkTrue(
    "heart body is a plausible path",
    icons.ICON_LIBRARY.find((i) => i.name === "heart").body.includes('d="M')
);

// ------------------------------------------------------------------
// Icon search: scoring and filtering
// ------------------------------------------------------------------

check("empty query returns first page", icons.searchIcons("").length, 200);
check("empty query respects limit", icons.searchIcons("", 5).length, 5);

const heart = icons.searchIcons("heart");
checkTrue("exact match ranks first", heart[0].name === "heart");
checkTrue(
    "prefix matches before substrings",
    heart.slice(0, 5).every((i) => i.name.startsWith("heart"))
);

const arrows = icons.searchIcons("arrow up");
checkTrue(
    "multi-term AND: every result matches both terms",
    arrows.every((i) => i.name.includes("arrow") && i.name.includes("up"))
);
check("multi-term misses one term", icons.searchIcons("arrow xyz").length, 0);
check("nonsense query", icons.searchIcons("zzzz-not-an-icon").length, 0);

const sale = icons.searchIcons("sale");
checkTrue("tag search finds sale icons", sale.some((i) => i.name === "badge-percent"));
const picture = icons.searchIcons("picture");
checkTrue("synonym search finds image icons", picture.some((i) => i.name === "image"));
checkTrue(
    "tag matches rank after name matches",
    (() => {
        const mixed = icons.searchIcons("image");
        const firstTagOnly = mixed.findIndex((i) => !i.name.includes("image"));
        const lastNameHit = mixed.reduce(
            (acc, i, idx) => (i.name.includes("image") ? idx : acc),
            -1
        );
        return firstTagOnly === -1 || firstTagOnly > lastNameHit;
    })()
);

// ------------------------------------------------------------------
// Brand assets: color normalization
// ------------------------------------------------------------------

check("normalize #rgb", brand.normalizeBrandColor("#F60"), "#ff6600");
check("normalize #rrggbb", brand.normalizeBrandColor("#FF6600"), "#ff6600");
check("normalize rgb()", brand.normalizeBrandColor("rgb(255, 102, 0)"), "#ff6600");
check("normalize garbage", brand.normalizeBrandColor("not-a-color"), null);
check("normalize empty", brand.normalizeBrandColor(""), null);

// ------------------------------------------------------------------
// Brand assets: default company color provider + registry merge
// ------------------------------------------------------------------

brand.resetBrandAssetRegistriesForTests();

check(
    "stock company record yields no brand colors",
    brand.collectBrandColors({ name: "Acme", logo: false }),
    []
);
check(
    "company brand color field picked up when present",
    brand.collectBrandColors({ name: "Acme", brand_color: "#123456" }),
    [{ name: "brand color", color: "#123456" }]
);
check("null company is safe", brand.collectBrandColors(null), []);

// Registered providers merge, dedupe by normalized hex, first wins.
const p1 = (company) => [
    { name: "Primary", color: "#FF0000" },
    { name: "Also red", color: "#f00" },
];
const p2 = () => [{ name: "Secondary", color: "#00ff00" }];
brand.registerBrandColorProvider(p1);
brand.registerBrandColorProvider(p2);
brand.registerBrandColorProvider(p1); // duplicate registration ignored
check(
    "providers merge and dedupe by hex",
    brand.collectBrandColors({}),
    [
        { name: "Primary", color: "#ff0000" },
        { name: "Secondary", color: "#00ff00" },
    ]
);
checkTrue(
    "registered provider runs per company",
    brand.collectBrandColors({}).length === 2
);

// A broken provider must not break the others.
brand.registerBrandColorProvider(() => {
    throw new Error("boom");
});
checkTrue(
    "broken provider tolerated",
    brand.collectBrandColors({}).length === 2
);
brand.resetBrandAssetRegistriesForTests();

// ------------------------------------------------------------------
// Brand assets: font registry
// ------------------------------------------------------------------

check("no brand fonts by default", brand.collectBrandFonts(), []);
brand.registerBrandFontProvider(() => [{ name: "Brandon Bold", family: "Brandon Grotesque" }]);
brand.registerBrandFontProvider(() => ["Brandon Grotesque", { name: "Other", family: "Other Font" }]);
check(
    "fonts dedupe by family",
    brand.collectBrandFonts(),
    [
        { name: "Brandon Bold", family: "Brandon Grotesque" },
        { name: "Other", family: "Other Font" },
    ]
);
brand.resetBrandAssetRegistriesForTests();

// ------------------------------------------------------------------
// Utils: icon custom prop survives serialization round trip
// ------------------------------------------------------------------

checkTrue(
    "EXTRA_PROPS carries _iconName",
    utils.EXTRA_PROPS.includes("_iconName")
);

if (failures) {
    console.error(`\n${failures} check(s) failed`);
    process.exit(1);
}
console.log("\nAll brand/icon checks passed");
