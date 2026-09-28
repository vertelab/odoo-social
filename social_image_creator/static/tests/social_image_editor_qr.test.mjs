// Node smoke test for the editor QR library (design D5 in
// openspec/changes/editor-grid-dynamic-elements) and the dialog's QR
// insert/edit flow.
// Run: node social_image_creator/static/tests/social_image_editor_qr.test.mjs
//
// Fixture parity: the editor vendors qrcode-generator at
// static/lib/qrcode-generator (loaded here via readFile + Function, the
// same UMD build the browser gets); the render service requires the npm
// package. Both must produce the identical module matrix for the same
// content, which this suite asserts against render_service/qr_matrix.mjs.

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

// The render-side reference (npm qrcode-generator via createRequire).
import * as renderQr from "../../../render_service/qr_matrix.mjs";

const qrLib = await importAsMjs(
    "../src/js/dialog/qr_library.js",
    "social_image_editor_qr.smoke.mjs"
);

// Load the vendored UMD build the way a classic script would: the top
// level `var qrcode` becomes the return value here, the AMD/CJS branches
// of the wrapper stay inert under Function scope.
const vendoredSource = readFileSync(
    join(here, "../lib/qrcode-generator/qrcode.js"),
    "utf8"
);
const vendoredQr = new Function(`${vendoredSource}\nreturn qrcode;`)();
vendoredQr.stringToBytes = vendoredQr.stringToBytesFuncs["UTF-8"];
qrLib.initQrGenerator(vendoredQr);
// The stripped dialog harness reaches the generator through the loadQr stub.
globalThis.__vendoredQr = vendoredQr;

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
function checkTrue(name, cond, detail) {
    if (!cond) {
        failures += 1;
        console.error(`FAIL ${name}${detail ? `: ${detail}` : ""}`);
    } else {
        console.log(`ok ${name}`);
    }
}

// ------------------------------------------------------------------
// Fixture parity: vendored lib vs npm package, via each side's own
// qrContentToMatrix (identical validation, only the generator differs).
// ------------------------------------------------------------------

const FIXTURES = [
    "https://plastshop.se",
    "ABC-123",
    "Återvunnen Reg 100%",
    "0123456789".repeat(20),
    "a",
];
for (const content of FIXTURES) {
    const serviceMatrix = renderQr.qrContentToMatrix(content);
    const editorMatrix = qrLib.qrContentToMatrix(content);
    checkTrue(
        `matrix parity for ${JSON.stringify(content.slice(0, 24))}`,
        JSON.stringify(serviceMatrix) === JSON.stringify(editorMatrix) &&
            serviceMatrix.length === editorMatrix.length &&
            editorMatrix.length > 0 &&
            editorMatrix.length % 2 === 1
    );
}

// Explicit UTF-8 check: the Swedish content must not be byte-wise wrong
// (the stringToBytes override). A spot check on the vendored lib itself:
// encoding "Å" must yield the same matrix as the service side.
{
    const content = "Reg ÅÄÖ";
    checkTrue(
        "UTF-8 content identical on both sides",
        JSON.stringify(renderQr.qrContentToMatrix(content)) ===
            JSON.stringify(qrLib.qrContentToMatrix(content))
    );
}

// qrMatrixToRectSpecs parity with the render side on a real matrix.
{
    const matrix = renderQr.qrContentToMatrix("https://example.se/path?q=1");
    const serviceSpecs = renderQr.qrMatrixToRectSpecs(matrix, 4, "#000000");
    const editorSpecs = qrLib.qrMatrixToRectSpecs(matrix, 4, "#000000");
    check("rect specs parity with render side", editorSpecs, serviceSpecs);
    checkTrue(
        "one rect per dark module",
        editorSpecs.length === matrix.flat().filter(Boolean).length
    );
    check(
        "first rect anchored at a module corner",
        [editorSpecs[0].left % 4, editorSpecs[0].top % 4, editorSpecs[0].size, editorSpecs[0].fill],
        [0, 0, 4, "#000000"]
    );
}

// ------------------------------------------------------------------
// Validation errors (mirroring the render-side contract)
// ------------------------------------------------------------------

function expectError(name, fn, needle) {
    try {
        fn();
        failures += 1;
        console.error(`FAIL ${name}: expected an error`);
    } catch (err) {
        checkTrue(
            `${name} (${needle ? err.message : err.message})`,
            needle ? err.message.includes(needle) : true
        );
    }
}
expectError("empty content throws", () => qrLib.qrContentToMatrix(""), "empty");
expectError(
    "over-long content throws",
    () => qrLib.qrContentToMatrix("x".repeat(4001)),
    "too long"
);
expectError(
    "bad error level throws",
    () => qrLib.qrContentToMatrix("abc", { errorLevel: "Z" }),
    "errorLevel"
);
expectError(
    "rect specs rejects empty matrix",
    () => qrLib.qrMatrixToRectSpecs([], 4),
    "non-empty"
);
expectError(
    "rect specs rejects non-square matrix",
    () => qrLib.qrMatrixToRectSpecs([[true, true]], 4),
    "square"
);
expectError(
    "rect specs rejects bad module size",
    () => qrLib.qrMatrixToRectSpecs([[true]], 0),
    "positive number"
);
check("QR_PROP is _qrContent", qrLib.QR_PROP, "_qrContent");

// ------------------------------------------------------------------
// Dialog insert flow with a fabric stub
// ------------------------------------------------------------------

const utils = await importAsMjs(
    "../src/js/dialog/social_image_editor_utils.js",
    "social_image_editor_utils.qr.mjs"
);
const dialogSource = readFileSync(
    join(here, "../src/js/dialog/social_image_editor_dialog.js"),
    "utf8"
);
const stripped = dialogSource
    .replace(/^import\b[^;]*;/gm, "")
    .replace("export class SocialImageEditorDialog", "class SocialImageEditorDialog")
    .concat("\nexport { SocialImageEditorDialog };\n");
const DIALOG_NAMES = [
    "EXTRA_PROPS",
    "HISTORY_LIMIT",
    "applyImageCoverFit",
    "buildLayerDescriptors",
    "buildToken",
    "computeAlignmentDeltas",
    "computeAutofitFontSize",
    "computeDisplayScale",
    "computeDistributePositions",
    "computeGridLines",
    "computeInsertIndex",
    "computeSmartSpacing",
    "DASH_PRESETS",
    "DEFAULT_GRID_SPACING",
    "detectStrokePattern",
    "gradientAngleToCoords",
    "gradientRadialCoords",
    "gradientToConfig",
    "GRID_SPACING_PRESETS",
    "isEmptyBindingValue",
    "moveItem",
    "newLayerId",
    "opacityPercentFromFraction",
    "parseShadowColor",
    "buildShadowColor",
    "resolveTextForPreview",
    "resolveTokens",
    "restoreSceneProps",
    "roundToGrid",
    "snapBoxFromRect",
    "snapBoxToGuides",
    "stashSceneProps",
    "toHexColor",
    "widestLine",
];
const preamble = [
    `import * as __utils from ${JSON.stringify(join("/tmp", "social_image_editor_utils.qr.mjs"))};`,
    `const { ${DIALOG_NAMES.join(", ")} } = __utils;`,
    `import * as __qr from ${JSON.stringify(join("/tmp", "social_image_editor_qr.smoke.mjs"))};`,
    "const { qrContentToMatrix, qrMatrixToRectSpecs, initQrGenerator, QR_PROP } = __qr;",
    "const chartSpecToSvg = () => '';",
    "const substituteChartSpec = (spec) => spec;",
    "const CHART_SPEC_PROP = '_chartSpec';",
    "const TABLE_PROP = '_tableData';",
    "const addTableColumn = (d) => d;",
    "const addTableRow = (d) => d;",
    "const buildTableGroup = () => null;",
    "const normalizeTableData = (d) => d;",
    "const removeTableColumn = (d) => d;",
    "const removeTableRow = (d) => d;",
    "const starterTableData = () => ({});",
    "const syncTableTexts = (d) => d;",
    "const loadQr = async () => globalThis.__vendoredQr;",
    "const Component = class {};",
    "const FileUploader = class {};",
    "const _t = (term) => term;",
    "const isTextType = (type) => [\"textbox\", \"i-text\", \"text\"].includes((type || \"\").toLowerCase());",
    "const isImageType = (type) => (type || \"\").toLowerCase() === \"image\";",
].join("\n");
const harnessTmp = join("/tmp", "social_image_editor_dialog.qr.mjs");
writeFileSync(harnessTmp, `${preamble}\n${stripped}`);
const dialogMod = await import(harnessTmp);
const DialogClass = dialogMod.SocialImageEditorDialog;

function makeFakeFabric() {
    class FakeRect {
        constructor(opts) {
            this.type = "rect";
            Object.assign(this, opts);
        }
    }
    class FakeGroup {
        constructor(children) {
            this.type = "group";
            this._objects = children;
            this.width = 0;
            this.height = 0;
        }
        getObjects() {
            return this._objects;
        }
        set(opts) {
            Object.assign(this, opts);
        }
    }
    return { Rect: FakeRect, Group: FakeGroup };
}

function makeDialog() {
    const dlg = Object.create(DialogClass.prototype);
    dlg.props = { resModel: "social.image.template", resId: 1, close: () => {} };
    dlg.state = {
        busy: false,
        previewMode: false,
        saveState: "clean",
        message: "",
        hasSelection: false,
        qrMenuOpen: true,
        qrContentDraft: "",
        qrError: "",
        chartMenuOpen: false,
        tableMenuOpen: false,
        tableRowsDraft: 3,
        tableColsDraft: 3,
        tableWidthDraft: 400,
        tableEditing: null,
        insertDataOpen: false,
        gridMenuOpen: false,
        shapesOpen: false,
        fontPickerOpen: false,
        iconPickerOpen: false,
        mediaPickerOpen: false,
        inspector: { isText: false, isImage: false },
    };
    const objects = [];
    let current = null;
    dlg._canvas = {
        getActiveObject: () => current,
        getObjects: () => objects,
        add: (obj) => {
            objects.push(obj);
            current = obj;
        },
        remove: () => {},
        discardActiveObject: () => {
            current = null;
        },
        setActiveObject: (obj) => {
            current = obj;
        },
        requestRenderAll: () => {},
        renderAll: () => {},
    };
    dlg._dimensions = { width: 1200, height: 630 };
    dlg._history = { stack: [], cursor: -1, suspended: false };
    dlg._dirty = false;
    dlg._saving = false;
    dlg._closeFailed = false;
    dlg._historyTimer = null;
    dlg._saveTimer = null;
    dlg._messageTimer = null;
    dlg._previewSnapshot = null;
    dlg._suppressDirty = false;
    dlg._tableEdit = null;
    dlg._snapGuides = { lines: [], distances: [] };
    dlg._fabric = makeFakeFabric();
    dlg._syncSelection = () => {};
    dlg._onCanvasChanged = () => {};
    dlg._syncGlobalPointerListener = () => {};
    return dlg;
}

{
    // Successful insert: one centered group carrying _qrContent.
    const dlg = makeDialog();
    dlg.state.qrContentDraft = "https://plastshop.se";
    await dlg.insertQr();
    const group = dlg._canvas.getObjects()[0];
    checkTrue("QR group inserted", !!group);
    const matrix = qrLib.qrContentToMatrix("https://plastshop.se");
    check("QR group encodes content", group[qrLib.QR_PROP], "https://plastshop.se");
    check(
        "QR group sized modules * moduleSize",
        [group.width, group.height],
        [matrix.length * 4, matrix.length * 4]
    );
    check(
        "QR group holds one rect per dark module",
        group.getObjects().length,
        matrix.flat().filter(Boolean).length
    );
    check(
        "QR group centered",
        [group.left, group.top],
        [
            Math.floor((1200 - matrix.length * 4) / 2),
            Math.floor((630 - matrix.length * 4) / 2),
        ]
    );
    check("menu closed after insert", dlg.state.qrMenuOpen, false);
}
{
    // Empty content: inline error, nothing inserted.
    const dlg = makeDialog();
    dlg.state.qrContentDraft = "   ";
    await dlg.insertQr();
    check("empty content shows inline error", dlg.state.qrError !== "", true);
    checkTrue("empty content inserts nothing", dlg._canvas.getObjects().length === 0);
}
{
    // Over-long content: inline error, nothing inserted.
    const dlg = makeDialog();
    dlg.state.qrContentDraft = "x".repeat(4001);
    await dlg.insertQr();
    checkTrue(
        "over-long content shows inline error",
        dlg.state.qrError !== ""
    );
    checkTrue("over-long content inserts nothing", dlg._canvas.getObjects().length === 0);
}
{
    // EXTRA_PROPS carries _qrContent for the capture round trip.
    checkTrue(
        "EXTRA_PROPS lists _qrContent",
        utils.EXTRA_PROPS.includes("_qrContent")
    );
}

if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
}
console.log("all QR checks passed");
