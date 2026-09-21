// Node smoke test for the pure shape library and typography helpers.
// Run: node social_image_creator/static/tests/social_image_editor_shapes.test.mjs
//
// The source modules are Odoo-flavored ES modules; Node treats .js as CJS
// here, so copy them to .mjs temp files before importing (same trick as
// social_image_editor_utils.test.mjs).

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

const shapes = await importAsMjs(
    "../src/js/dialog/shape_library.js",
    "social_image_editor_shapes.smoke.mjs"
);
const utils = await importAsMjs(
    "../src/js/dialog/social_image_editor_utils.js",
    "social_image_editor_utils.smoke.mjs"
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
// Shape library: catalog integrity
// ------------------------------------------------------------------

check("17 path shapes plus 5 parametric", shapes.SHAPES.length, 22);
for (const shape of shapes.SHAPES) {
    checkTrue(`shape ${shape.kind} has label`, !!shape.label);
    checkTrue(`shape ${shape.kind} has path`, typeof shape.path === "string" && shape.path.length > 0);
}
check("burst8 path is closed", shapes.SHAPE_META.burst8.path.trim().endsWith("Z"), true);
check("burst8 has 16 vertices", (shapes.SHAPE_META.burst8.path.match(/[ML]/g) || []).length, 16);
check("burst12 has 24 vertices", (shapes.SHAPE_META.burst12.path.match(/[ML]/g) || []).length, 24);
check("gem has a hole/subpath", shapes.SHAPE_META.gem.path.includes("M"), true);

const parametricKinds = shapes.SHAPES.filter((s) => s.parametric).map((s) => s.kind);
check(
    "parametric kinds",
    parametricKinds,
    ["polygon", "pstar", "pburst", "pflower", "psunny"]
);
for (const kind of parametricKinds) {
    const meta = shapes.SHAPE_META[kind];
    checkTrue(`${kind} has defaults`, !!meta.defaults);
    checkTrue(
        `${kind} default path matches builder`,
        shapes.PARAM_SHAPES[kind].build(meta.defaults) === meta.path
    );
    checkTrue(
        `${kind} params carry slider defs`,
        shapes.PARAM_SHAPES[kind].params.every(
            (p) => typeof p.min === "number" && typeof p.max === "number" && typeof p.step === "number"
        )
    );
}

// ------------------------------------------------------------------
// Parametric generators
// ------------------------------------------------------------------

const tri = shapes.pathParametricPolygon({ sides: 3, cornerRadius: 0 });
checkTrue("polygon path starts with M", tri.startsWith("M "));
checkTrue("polygon path closed", tri.trim().endsWith("Z"));
check("polygon vertex count", (tri.match(/L /g) || []).length, 2);
check(
    "polygon sides clamp to 3",
    (shapes.pathParametricPolygon({ sides: 1, cornerRadius: 0 }).match(/L /g) || []).length,
    2
);
check(
    "polygon sides clamp to 12",
    (shapes.pathParametricPolygon({ sides: 99, cornerRadius: 0 }).match(/L /g) || []).length,
    11
);
const rounded = shapes.pathParametricPolygon({ sides: 6, cornerRadius: 0.3 });
checkTrue("rounded polygon uses quadratic curves", rounded.includes("Q "));
const sharp = shapes.pathParametricPolygon({ sides: 6, cornerRadius: 0 });
checkTrue("sharp polygon has no curves", !sharp.includes("Q"));

const star = shapes.pathParametricStar({ points: 5, innerRatio: 0.45, cornerRadius: 0 });
check("star has 10 vertices", (star.match(/[ML] /g) || []).length, 10);
checkTrue("soft star uses curves", shapes.pathParametricStar({ points: 5, innerRatio: 0.45, cornerRadius: 0.5 }).includes("Q"));

const burst = shapes.pathParametricBurst({ rays: 12, depth: 0.35 });
check("burst has 24 points", (burst.match(/[ML] /g) || []).length, 24);
checkTrue("burst closed", burst.trim().endsWith("Z"));

const flower = shapes.pathParametricFlower({ petals: 6, depth: 0.7 });
checkTrue("flower closed", flower.trim().endsWith("Z"));
checkTrue("flower dense sampling", (flower.match(/[ML] /g) || []).length > 120);

const sunny = shapes.pathParametricSunny({ rays: 16, length: 0.4 });
check("sunny has 32 points", (sunny.match(/[ML] /g) || []).length, 32);

// Determinism: same params, same path.
check(
    "polygon deterministic",
    shapes.pathParametricPolygon({ sides: 8, cornerRadius: 0.2 }),
    shapes.pathParametricPolygon({ sides: 8, cornerRadius: 0.2 })
);

// ------------------------------------------------------------------
// Case transform
// ------------------------------------------------------------------

check("transform upper", utils.applyCaseTransform("Big Sale", "upper"), "BIG SALE");
check("transform lower", utils.applyCaseTransform("Big Sale", "lower"), "big sale");
check("transform none", utils.applyCaseTransform("Big Sale", "none"), "Big Sale");
check("transform null", utils.applyCaseTransform("Big Sale", null), "Big Sale");
check("transform non-string", utils.applyCaseTransform(undefined, "upper"), undefined);
check("transform swedish chars", utils.applyCaseTransform("ÅÄÖ abc", "upper"), "ÅÄÖ ABC");

check("widest line", utils.widestLine("ab\nabcd\nabc"), "abcd");
check("widest line empty", utils.widestLine(""), "");

// ------------------------------------------------------------------
// Autofit font size
// ------------------------------------------------------------------

// Linear measure: width = 2 * fontSize per character.
const measure = (fontSize, line) => 2 * fontSize * line.length;

// 10 chars at size 40 -> 800 wide; box 400 -> fits at 20.
check(
    "autofit shrinks to half",
    utils.computeAutofitFontSize({
        text: "0123456789",
        boxWidth: 400,
        startSize: 40,
        measure,
    }),
    20
);
// Already fits: no change.
check(
    "autofit keeps size when it fits",
    utils.computeAutofitFontSize({
        text: "abc",
        boxWidth: 400,
        startSize: 40,
        measure,
    }),
    40
);
// Impossibly narrow: floors at minSize.
check(
    "autofit floors at minSize",
    utils.computeAutofitFontSize({
        text: "0123456789",
        boxWidth: 5,
        startSize: 40,
        minSize: 6,
        measure,
    }),
    6
);
// Multi-line: widest line drives the fit.
check(
    "autofit uses widest line",
    utils.computeAutofitFontSize({
        text: "abc\n0123456789",
        boxWidth: 400,
        startSize: 40,
        measure,
    }),
    20
);
// Empty text: no shrink.
check(
    "autofit empty text",
    utils.computeAutofitFontSize({ text: "", boxWidth: 10, startSize: 40, measure }),
    40
);
// Degenerate box: no shrink.
check(
    "autofit zero box width",
    utils.computeAutofitFontSize({ text: "abc", boxWidth: 0, startSize: 40, measure }),
    40
);
// Never grows: text narrower than the box at a smaller start size.
check(
    "autofit never grows",
    utils.computeAutofitFontSize({
        text: "abc",
        boxWidth: 400,
        startSize: 10,
        measure,
    }),
    10
);
// Start at or below the floor: returned unchanged.
check(
    "autofit start below floor",
    utils.computeAutofitFontSize({
        text: "0123456789",
        boxWidth: 1,
        startSize: 4,
        minSize: 6,
        measure,
    }),
    4
);

// ------------------------------------------------------------------
// toHexColor
// ------------------------------------------------------------------

check("hex passthrough", utils.toHexColor("#4f46e5"), "#4f46e5");
check("short hex expands", utils.toHexColor("#abc"), "#aabbcc");
check("rgb converts", utils.toHexColor("rgb(79, 70, 229)"), "#4f46e5");
check("rgba converts ignoring alpha", utils.toHexColor("rgba(79, 70, 229, 0.5)"), "#4f46e5");
check("garbage falls back", utils.toHexColor("not-a-color"), "#000000");
check("null falls back", utils.toHexColor(null), "#000000");

// ------------------------------------------------------------------
// Arrow / group layer labels via shapeMeta
// ------------------------------------------------------------------

const meta = { arrow: { label: "Arrow" } };
check(
    "arrow group label from shapeMeta",
    utils.buildLayerLabel({ type: "group", _shapeKind: "arrow" }, meta),
    "Arrow"
);
check(
    "explicit name still wins over shapeMeta",
    utils.buildLayerLabel({ type: "group", _shapeKind: "arrow", _layerName: "Pil" }, meta),
    "Pil"
);
check(
    "group without shapeKind falls back to type label",
    utils.buildLayerLabel({ type: "group" }, meta),
    "Group"
);
const descriptors = utils.buildLayerDescriptors(
    [
        { _layerId: "a", type: "group", _shapeKind: "arrow" },
        { _layerId: "b", type: "Rect" },
    ],
    meta
);
check("descriptor arrow label", descriptors[1].label, "Arrow");

if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
}
console.log("all checks passed");
