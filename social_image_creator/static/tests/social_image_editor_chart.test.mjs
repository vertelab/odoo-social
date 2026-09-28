// Node smoke test for the editor chart library and the dialog's chart
// editing flow (tasks 4.3/4.5, design D3 in
// openspec/changes/editor-grid-dynamic-elements).
// Run: node social_image_creator/static/tests/social_image_editor_chart.test.mjs
//
// Byte parity with render_service/chart_spec.mjs is enforced separately by
// scripts/check_chart_sync.py; this suite asserts the editor copy's own
// behavior (all six types, token substitution) and that the dialog's
// chart edit handlers produce specs that chartSpecToSvg accepts.

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

const chartLib = await importAsMjs(
    "../src/js/dialog/chart_library.js",
    "social_image_editor_chart.smoke.mjs"
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
function checkTrue(name, cond, detail) {
    if (!cond) {
        failures += 1;
        console.error(`FAIL ${name}${detail ? `: ${detail}` : ""}`);
    } else {
        console.log(`ok ${name}`);
    }
}

// ------------------------------------------------------------------
// chart_library: all six types generate, deterministic, escaped
// ------------------------------------------------------------------

function spec(type, extra = {}) {
    return {
        version: 1,
        type,
        title: "Test",
        categories: ["Jan", "Feb"],
        series: [
            { name: "A", values: [10, 20] },
            { name: "B", values: [5, "15"] },
        ],
        options: { width: 320, height: 240 },
        ...extra,
    };
}

const TYPES = ["bar-v", "bar-h", "line", "area", "pie", "donut"];
for (const type of TYPES) {
    const svg = chartLib.chartSpecToSvg(spec(type));
    checkTrue(
        `${type} generates an svg document`,
        svg.startsWith("<svg") && svg.endsWith("</svg>") && svg.length > 200
    );
    const again = chartLib.chartSpecToSvg(spec(type));
    checkTrue(`${type} is deterministic`, svg === again);
}
{
    const svg = chartLib.chartSpecToSvg(spec("bar-v"));
    const bars = (svg.match(/class="bar"/g) || []).length;
    check("bar-v draws categories x series bars", bars, 4);
}
{
    const svg = chartLib.chartSpecToSvg(spec("donut"));
    checkTrue(
        "donut draws slices",
        (svg.match(/class="slice"/g) || []).length === 2
    );
}
{
    // Markup injection in a title is escaped.
    const svg = chartLib.chartSpecToSvg(
        spec("bar-v", { title: '<script>alert("x")</script>' })
    );
    checkTrue("title is xml-escaped", !svg.includes("<script>"));
    // A bad cell maps to 0 and never throws.
    const bad = chartLib.chartSpecToSvg(
        spec("bar-v", { series: [{ name: "A", values: ["abc", null] }] })
    );
    checkTrue("non-numeric cells plot as zero", bad.includes('class="bar"'));
}
{
    // Substitution resolves known tokens, leaves unknown ones.
    const bound = chartLib.substituteChartSpec(
        spec("bar-v", {
            categories: ["{{categ.name}}", "Static"],
            series: [{ name: "Vikt", values: ["{{product.weight}}", "{{missing}}"] }],
        }),
        { "product.weight": "12.5", "categ.name": "Kok" }
    );
    check("substituted categories", bound.categories, ["Kok", "Static"]);
    check("substituted values", bound.series[0].values, ["12.5", "{{missing}}"]);
    checkTrue(
        "input spec not mutated by substitution",
        spec("bar-v").categories[0] === "Jan"
    );
    const svg = chartLib.chartSpecToSvg(bound);
    checkTrue("bound chart renders", svg.includes('class="bar"'));
}

// ------------------------------------------------------------------
// Dialog chart editing produces valid specs
// ------------------------------------------------------------------

const utils = await importAsMjs(
    "../src/js/dialog/social_image_editor_utils.js",
    "social_image_editor_utils.chart.mjs"
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
    `import * as __utils from ${JSON.stringify(join("/tmp", "social_image_editor_utils.chart.mjs"))};`,
    `const { ${DIALOG_NAMES.join(", ")} } = __utils;`,
    `import * as __chart from ${JSON.stringify(join("/tmp", "social_image_editor_chart.smoke.mjs"))};`,
    "const { chartSpecToSvg, substituteChartSpec, CHART_SPEC_PROP } = __chart;",
    "const qrContentToMatrix = () => [];",
    "const qrMatrixToRectSpecs = () => [];",
    "const initQrGenerator = () => {};",
    "const QR_PROP = '_qrContent';",
    "const TABLE_PROP = '_tableData';",
    "const addTableColumn = (d) => d;",
    "const addTableRow = (d) => d;",
    "const buildTableGroup = () => null;",
    "const normalizeTableData = (d) => d;",
    "const removeTableColumn = (d) => d;",
    "const removeTableRow = (d) => d;",
    "const starterTableData = () => ({});",
    "const syncTableTexts = (d) => d;",
    "const loadQr = async () => ({});",
    "const Component = class {};",
    "const FileUploader = class {};",
    "const _t = (term) => term;",
    'const isTextType = (type) => ["textbox", "i-text", "text"].includes((type || "").toLowerCase());',
    'const isImageType = (type) => (type || "").toLowerCase() === "image";',
].join("\n");
const harnessTmp = join("/tmp", "social_image_editor_dialog.chart.mjs");
writeFileSync(harnessTmp, `${preamble}\n${stripped}`);
const dialogMod = await import(harnessTmp);
const DialogClass = dialogMod.SocialImageEditorDialog;

function makeDialogWithChart() {
    const dlg = Object.create(DialogClass.prototype);
    dlg.props = { resModel: "social.image.template", resId: 1, close: () => {} };
    const group = {
        type: "group",
        [chartLib.CHART_SPEC_PROP]: dlg.starterChartSpec("bar-v"),
    };
    dlg.state = {
        busy: false,
        previewMode: false,
        saveState: "clean",
        message: "",
        hasSelection: true,
        qrMenuOpen: false,
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
    dlg._canvas = {
        getActiveObject: () => group,
        getObjects: () => [group],
        requestRenderAll: () => {},
        renderAll: () => {},
    };
    dlg._dimensions = { width: 1200, height: 630 };
    dlg._history = { stack: [], cursor: -1, suspended: false };
    dlg._dirty = false;
    dlg._saving = false;
    dlg._messageTimer = null;
    dlg._previewSnapshot = null;
    dlg._suppressDirty = false;
    dlg._tableEdit = null;
    dlg._snapGuides = { lines: [], distances: [] };
    let committed = null;
    dlg._commitChartSpec = async (g, spec) => {
        committed = { group: g, spec };
    };
    dlg._showMessage = (text) => {
        dlg.state.message = text;
    };
    dlg.committed = () => committed;
    // The panel edits the inspector draft, like the template does.
    dlg._syncSelection = () => {};
    dlg._onCanvasChanged = () => {};
    return dlg;
}

{
    const dlg = makeDialogWithChart();
    const starter = dlg.starterChartSpec("bar-v");
    check(
        "starter spec matches the contract",
        [
            starter.version,
            starter.type,
            starter.categories.length,
            starter.series.length,
            starter.series[0].values,
            starter.options.width,
            starter.options.height,
        ],
        [1, "bar-v", 3, 1, [10, 20, 15], 480, 320]
    );
    check(
        "six chart types offered",
        dlg.chartTypeOptions().map((o) => o.type),
        ["bar-v", "bar-h", "line", "area", "pie", "donut"]
    );
    checkTrue(
        "starter spec renders",
        chartLib.chartSpecToSvg(starter).startsWith("<svg")
    );
}
{
    const dlg = makeDialogWithChart();
    dlg.state.inspector = { chart: JSON.parse(JSON.stringify(dlg.starterChartSpec("bar-v"))) };
    dlg.onChartTypeChange("pie");
    let committed = dlg.committed();
    checkTrue("type change committed", !!committed);
    check("committed type", committed.spec.type, "pie");
    checkTrue(
        "committed pie spec renders slices",
        (chartLib.chartSpecToSvg(committed.spec).match(/class="slice"/g) || [])
            .length === 3
    );
    // Data preserved across a type switch.
    check(
        "data preserved across type switch",
        committed.spec.series[0].values,
        [10, 20, 15]
    );
}
{
    const dlg = makeDialogWithChart();
    dlg.state.inspector = { chart: JSON.parse(JSON.stringify(dlg.starterChartSpec("bar-v"))) };
    dlg.onChartTitleChange({ target: { value: "Forsaljning" } });
    check("title edit committed", dlg.committed().spec.title, "Forsaljning");
    dlg.onChartCategoryChange(1, { target: { value: "Feb" } });
    check("category edit committed", dlg.committed().spec.categories[1], "Feb");
    dlg.onChartSeriesNameChange(0, { target: { value: "Stolar" } });
    check("series rename committed", dlg.committed().spec.series[0].name, "Stolar");
    dlg.onChartCellChange(0, 2, { target: { value: "{{product.weight}}" } });
    check(
        "token cell committed",
        dlg.committed().spec.series[0].values[2],
        "{{product.weight}}"
    );
    checkTrue(
        "token cell resolves and still renders",
        chartLib
            .chartSpecToSvg(
                chartLib.substituteChartSpec(dlg.committed().spec, {
                    "product.weight": "12.5",
                })
            )
            .includes('class="bar"')
    );
}
{
    const dlg = makeDialogWithChart();
    dlg.state.inspector = { chart: JSON.parse(JSON.stringify(dlg.starterChartSpec("bar-v"))) };
    dlg.onChartAddCategory();
    check(
        "add category grows every series",
        [
            dlg.committed().spec.categories.length,
            dlg.committed().spec.series[0].values.length,
        ],
        [4, 4]
    );
    dlg.onChartAddSeries();
    check("add series", dlg.committed().spec.series.length, 2);
    dlg.onChartRemoveCategory(0);
    check(
        "remove category shrinks every series",
        [
            dlg.committed().spec.categories.length,
            dlg.committed().spec.series[0].values.length,
        ],
        [3, 3]
    );
    dlg.onChartRemoveSeries(1);
    check("remove series", dlg.committed().spec.series.length, 1);
    // Last category/series is guarded.
    dlg.onChartRemoveCategory(0);
    dlg.onChartRemoveCategory(0);
    check(
        "one category always remains",
        dlg.committed().spec.categories.length,
        1
    );
    checkTrue(
        "every committed spec renders",
        chartLib.chartSpecToSvg(dlg.committed().spec).startsWith("<svg")
    );
}
{
    // Insert path with a stubbed fabric: SVG string -> group with prop.
    const dlg = Object.create(DialogClass.prototype);
    dlg.props = { resModel: "social.image.template", resId: 1, close: () => {} };
    dlg.state = {
        busy: false,
        previewMode: false,
        saveState: "clean",
        message: "",
        hasSelection: false,
        qrMenuOpen: false,
        qrContentDraft: "",
        qrError: "",
        chartMenuOpen: true,
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
    dlg._messageTimer = null;
    dlg._previewSnapshot = null;
    dlg._suppressDirty = false;
    dlg._tableEdit = null;
    dlg._snapGuides = { lines: [], distances: [] };
    let loadedSvg = null;
    dlg._fabric = {
        loadSVGFromString: async (svg) => {
            loadedSvg = svg;
            return { objects: [{ type: "path" }], options: {} };
        },
        util: {
            groupSVGElements: (objs, options) => ({
                type: "group",
                _objects: objs,
                width: options.width || 480,
                height: options.height || 320,
                set(opts) {
                    Object.assign(this, opts);
                },
            }),
        },
        Group: class {
            constructor(children) {
                this.type = "group";
                this._objects = children;
            }
        },
    };
    dlg._syncSelection = () => {};
    dlg._onCanvasChanged = () => {};
    dlg._syncGlobalPointerListener = () => {};
    await dlg.insertChart("line");
    const group = objects[0];
    checkTrue("chart group inserted", !!group);
    checkTrue("svg was generated through the parity module", !!loadedSvg && loadedSvg.startsWith("<svg"));
    checkTrue(
        "group carries _chartSpec",
        group[chartLib.CHART_SPEC_PROP] && group[chartLib.CHART_SPEC_PROP].type === "line"
    );
    check(
        "chart centered",
        [group.left, group.top],
        [Math.floor((1200 - 480) / 2), Math.floor((630 - 320) / 2)]
    );
    check("chart menu closed", dlg.state.chartMenuOpen, false);
}
checkTrue(
    "EXTRA_PROPS lists _chartSpec",
    utils.EXTRA_PROPS.includes("_chartSpec")
);

if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
}
console.log("all chart checks passed");
