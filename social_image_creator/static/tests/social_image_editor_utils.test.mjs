// Node smoke test for the pure editor helpers.
// Run: node social_image_creator/static/tests/social_image_editor_utils.test.mjs
//
// The utils module is an Odoo-flavored ES module; Node treats .js as CJS
// here, so copy it to a .mjs temp file before importing.

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
    join(here, "../src/js/dialog/social_image_editor_utils.js"),
    "utf8"
);
const tmp = join("/tmp", "social_image_editor_utils.smoke.mjs");
writeFileSync(tmp, source);
const utils = await import(tmp);

let failures = 0;
function check(name, actual, expected) {
    const ok = JSON.stringify(actual) === JSON.stringify(expected);
    if (!ok) {
        failures += 1;
        console.error(`FAIL ${name}: got ${JSON.stringify(actual)}, want ${JSON.stringify(expected)}`);
    } else {
        console.log(`ok ${name}`);
    }
}

// buildLayerLabel
check(
    "label explicit name",
    utils.buildLayerLabel({ _layerName: "Headline", type: "Textbox", text: "Hello" }),
    "Headline"
);
check(
    "label text preview trimmed",
    utils.buildLayerLabel({ type: "Textbox", text: "  Big   sale\nnow  " }),
    "Big sale now"
);
check(
    "label media name",
    utils.buildLayerLabel({ type: "Image", _mediaName: "logo.png" }),
    "logo.png"
);
check(
    "label per type",
    utils.buildLayerLabel({ type: "Rect" }),
    "Rectangle"
);
check(
    "label unknown type falls back",
    utils.buildLayerLabel({ type: "Star" }),
    "Star"
);

// buildLayerDescriptors: topmost first, visible/locked flags
const fakeObjects = [
    { _layerId: "a", type: "Rect", selectable: true, visible: true },
    { _layerId: "b", type: "Textbox", text: "Hi", selectable: false, visible: false },
];
const descriptors = utils.buildLayerDescriptors(fakeObjects);
check(
    "descriptors reversed order",
    descriptors.map((d) => d.id),
    ["b", "a"]
);
check("descriptor locked", descriptors[0].locked, true);
check("descriptor hidden", descriptors[0].visible, false);
check("descriptor label", descriptors[0].label, "Hi");

// moveItem
check("moveItem down", utils.moveItem([1, 2, 3, 4], 0, 2), [2, 3, 1, 4]);
check("moveItem up", utils.moveItem([1, 2, 3, 4], 3, 1), [1, 4, 2, 3]);
check("moveItem noop out of range", utils.moveItem([1, 2], 0, 5), [1, 2]);
check("moveItem does not mutate", (() => {
    const list = [1, 2, 3];
    utils.moveItem(list, 0, 1);
    return list;
})(), [1, 2, 3]);

// computeDisplayScale
check("scale fits width", utils.computeDisplayScale(1200, 630, 600, 630), 0.5);
check("scale never upscales", utils.computeDisplayScale(800, 400, 2000, 2000), 1);
check("scale degenerate", utils.computeDisplayScale(0, 400, 100, 100), 1);

// stashSceneProps: object props with a string `type` are held aside,
// scalars pass through untouched.
const scene = {
    version: "6.9.1",
    objects: [
        { type: "Textbox", text: "Hello", _layerId: "x", _layerName: "Title" },
        {
            type: "Image",
            _layerId: "y",
            _dataBinding: { model: "product", field: "image", type: "image" },
            _scalarProp: 42,
        },
        null,
    ],
};
const { sanitized, stashed } = utils.stashSceneProps(scene);
check("stash keeps scalar custom prop", sanitized.objects[0]._layerName, "Title");
check(
    "stash removes enliven-risk prop",
    "_dataBinding" in sanitized.objects[1],
    false
);
check("stash keeps scalar on same object", sanitized.objects[1]._scalarProp, 42);
check(
    "stashed binding content",
    stashed[1][0] ? stashed[1][0].value.field : null,
    "image"
);
check("stash null object", stashed[2], []);
check("original scene untouched", "_dataBinding" in scene.objects[1], true);

// restoreSceneProps
const reloaded = [{ type: "Textbox" }, { type: "Image" }, null];
utils.restoreSceneProps(reloaded, stashed);
check(
    "restore re-attaches binding",
    reloaded[1]._dataBinding,
    { model: "product", field: "image", type: "image" }
);

// newLayerId uniqueness
const ids = new Set(Array.from({ length: 200 }, () => utils.newLayerId()));
check("layer ids unique", ids.size, 200);

// DASH_PRESETS + detectStrokePattern
check("dash preset solid is null", utils.DASH_PRESETS.solid, null);
check("dash preset dashed", utils.DASH_PRESETS.dashed, [10, 6]);
check("dash preset dotted", utils.DASH_PRESETS.dotted, [2, 5]);
check("detect solid", utils.detectStrokePattern(null), "solid");
check("detect solid empty", utils.detectStrokePattern([]), "solid");
check("detect dashed", utils.detectStrokePattern([10, 6]), "dashed");
check("detect dotted", utils.detectStrokePattern([2, 5]), "dotted");

// gradientAngleToCoords: 0 degrees points right, 90 points down,
// endpoints centered on the object, span = max(w, h)
// len = max(w, h) = 200, so the endpoints span past the short sides
const coords0 = utils.gradientAngleToCoords(0, 200, 100);
check("gradient 0 x1", coords0.x1, 0);
check("gradient 0 x2", coords0.x2, 200);
check("gradient 0 y centered", coords0.y1, 50);
const coords90 = utils.gradientAngleToCoords(90, 200, 100);
check("gradient 90 y1", coords90.y1, -50);
check("gradient 90 y2", coords90.y2, 150);

// gradientRadialCoords
const radial = utils.gradientRadialCoords(200, 100);
check("radial r2", radial.r2, 100);
check("radial centered", [radial.x1, radial.y1, radial.x2, radial.y2], [100, 50, 100, 50]);

// gradientToConfig from a live-instance-shaped gradient
const gradCfg = utils.gradientToConfig({
    type: "linear",
    coords: { x1: 50, y1: 50, x2: 150, y2: 50 },
    colorStops: [
        { offset: 0.1, color: "#ff0000" },
        { offset: 0.9, color: "#0000ff" },
    ],
});
check("gradient config type", gradCfg.type, "linear");
check("gradient config angle", gradCfg.angle, 0);
check("gradient config colors", [gradCfg.startColor, gradCfg.endColor], ["#ff0000", "#0000ff"]);
check("gradient config positions", [gradCfg.startPos, gradCfg.endPos], [0.1, 0.9]);
// ... and from Fabric 6 serialized form (type: "gradient", gradientType)
const gradSerialized = utils.gradientToConfig({
    type: "gradient",
    gradientType: "radial",
    coords: { x1: 50, y1: 50, r1: 0, x2: 50, y2: 50, r2: 100 },
    colorStops: [
        { offset: 0, color: "#111111" },
        { offset: 1, color: "#eeeeee" },
    ],
});
check("serialized gradient type", gradSerialized.type, "radial");
check("serialized gradient angle defaults 0", gradSerialized.angle, 0);
// negative angles normalize to 0-360
const gradNeg = utils.gradientToConfig({
    type: "linear",
    coords: { x1: 50, y1: 50, x2: 50, y2: 0 },
    colorStops: [{ offset: 0, color: "#000000" }],
});
check("gradient angle normalized", gradNeg.angle, 270);
check("solid fill returns null", utils.gradientToConfig("#ff0000"), null);
check("null fill returns null", utils.gradientToConfig(null), null);

// parseShadowColor / buildShadowColor
check("parse null shadow", utils.parseShadowColor(null), { hex: "#000000", alpha: 30 });
check("parse hex shadow", utils.parseShadowColor("#ff8800"), { hex: "#ff8800", alpha: 100 });
check("parse short hex shadow", utils.parseShadowColor("#f80"), { hex: "#ff8800", alpha: 100 });
check(
    "parse rgba shadow",
    utils.parseShadowColor("rgba(255,136,0,0.45)"),
    { hex: "#ff8800", alpha: 45 }
);
check(
    "parse rgb shadow",
    utils.parseShadowColor("rgb(10, 20, 30)"),
    { hex: "#0a141e", alpha: 100 }
);
check(
    "build shadow color",
    utils.buildShadowColor("#ff8800", 45),
    "rgba(255,136,0,0.45)"
);
check(
    "shadow color round trip",
    utils.parseShadowColor(utils.buildShadowColor("#0a141e", 30)),
    { hex: "#0a141e", alpha: 30 }
);

// computeAlignmentDeltas
const alignRects = [
    { left: 0, top: 0, width: 10, height: 10 },
    { left: 50, top: 40, width: 20, height: 20 },
];
check(
    "align left",
    utils.computeAlignmentDeltas(alignRects, "left"),
    [{ dx: 0, dy: 0 }, { dx: -50, dy: 0 }]
);
check(
    "align center h",
    utils.computeAlignmentDeltas(alignRects, "cx"),
    [{ dx: 30, dy: 0 }, { dx: -25, dy: 0 }]
);
check(
    "align right",
    utils.computeAlignmentDeltas(alignRects, "right"),
    [{ dx: 60, dy: 0 }, { dx: 0, dy: 0 }]
);
check(
    "align top",
    utils.computeAlignmentDeltas(alignRects, "top"),
    [{ dx: 0, dy: 0 }, { dx: 0, dy: -40 }]
);
check(
    "align center v",
    utils.computeAlignmentDeltas(alignRects, "cy"),
    [{ dx: 0, dy: 25 }, { dx: 0, dy: -20 }]
);
check(
    "align bottom",
    utils.computeAlignmentDeltas(alignRects, "bottom"),
    [{ dx: 0, dy: 50 }, { dx: 0, dy: 0 }]
);

// computeDistributePositions: three 10-wide boxes spanning 0..70 get
// 20-unit gaps; input order is preserved in the output.
check(
    "distribute three",
    utils.computeDistributePositions([
        { start: 0, size: 10 },
        { start: 25, size: 10 },
        { start: 60, size: 10 },
    ]),
    [0, 30, 60]
);
// fewer than 3 is a no-op
check(
    "distribute noop below 3",
    utils.computeDistributePositions([{ start: 5, size: 10 }, { start: 40, size: 10 }]),
    [5, 40]
);

// closestSnap: smallest absolute delta wins, threshold gates
check(
    "closestSnap picks nearest",
    utils.closestSnap([{ at: 100 }, { at: 52 }], [50], 6),
    { delta: 2, at: 52, found: true }
);
check(
    "closestSnap respects threshold",
    utils.closestSnap([{ at: 100 }], [50], 6).found,
    false
);
check(
    "closestSnap first on tie",
    utils.closestSnap([{ at: 54 }, { at: 46 }], [50], 6),
    { delta: 4, at: 54, found: true }
);

// snapBoxToGuides: canvas-center snap + object edge snap
const movingBox = { left: 97, right: 103, top: 10, bottom: 20, centerX: 100, centerY: 15 };
check(
    "snap to canvas center",
    utils.snapBoxToGuides(movingBox, [{ at: 100 }, { at: 400 }], [], 6),
    { dx: 0, dy: 0, vAt: 100, hAt: null }
);
check(
    "snap box applies delta",
    utils.snapBoxToGuides(
        { left: 45, right: 100, top: 0, bottom: 10, centerX: 72.5, centerY: 5 },
        [{ at: 300 }, { at: 50 }],
        [],
        6
    ),
    { dx: 5, dy: 0, vAt: 50, hAt: null }
);
check(
    "snap vertical guide",
    utils.snapBoxToGuides(
        { left: 97, right: 103, top: 196, bottom: 206, centerX: 100, centerY: 201 },
        [],
        [{ at: 200 }],
        6
    ),
    { dx: 0, dy: -1, vAt: null, hAt: 200 }
);

// computeSmartSpacing: equal-gap snap between immediate neighbors
const gapBox = { left: 44, right: 56, top: 0, bottom: 10, centerX: 50, centerY: 5 };
const gapOthers = [
    { left: 0, right: 40, top: 0, bottom: 10, centerX: 20, centerY: 5 },
    { left: 62, right: 102, top: 0, bottom: 10, centerX: 82, centerY: 5 },
];
const spacing = utils.computeSmartSpacing(gapBox, gapOthers, 6);
check("smart spacing equalizes gap dx", spacing.dx, 1);
check("smart spacing no dy", spacing.dy, 0);
check(
    "smart spacing labels",
    spacing.distances.map((d) => d.label),
    ["5px", "5px"]
);
// far from equal: no snap, labels show the actual gaps
const uneven = utils.computeSmartSpacing(gapBox, [
    { left: 0, right: 40, top: 0, bottom: 10, centerX: 20, centerY: 5 },
    { left: 70, right: 110, top: 0, bottom: 10, centerX: 90, centerY: 5 },
], 6);
check("smart spacing uneven no snap", [uneven.dx, uneven.dy], [0, 0]);
check(
    "smart spacing uneven labels",
    uneven.distances.map((d) => d.label),
    ["4px", "14px"]
);
// vertical sandwich
const vGap = utils.computeSmartSpacing(
    { left: 0, right: 10, top: 44, bottom: 56, centerX: 5, centerY: 50 },
    [
        { left: 0, right: 10, top: 0, bottom: 40, centerX: 5, centerY: 20 },
        { left: 0, right: 10, top: 62, bottom: 102, centerX: 5, centerY: 82 },
    ],
    6
);
check("smart spacing vertical dy", vGap.dy, 1);
check("smart spacing vertical labels", vGap.distances.every((d) => d.kind === "v"), true);
// single neighbor: label only, no snap
const single = utils.computeSmartSpacing(gapBox, [gapOthers[0]], 6);
check("smart spacing single no snap", [single.dx, single.dy], [0, 0]);
check("smart spacing single label count", single.distances.length, 1);

if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
}
console.log("all checks passed");
