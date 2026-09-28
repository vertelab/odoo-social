// Node smoke test for the pure table helpers and the fabric group builder
// (design D4 in openspec/changes/editor-grid-dynamic-elements).
// Run: node social_image_creator/static/tests/social_image_editor_table.test.mjs
//
// The source module is an Odoo-flavored ES module; Node treats .js as CJS
// here, so copy it to a .mjs temp file before importing (same trick as
// social_image_editor_utils.test.mjs). buildTableGroup is exercised with a
// fabric stub; the real fabric bundle only exists in the browser and the
// Docker render service.

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

const table = await importAsMjs(
    "../src/js/dialog/table_library.js",
    "social_image_editor_table.smoke.mjs"
);
const utils = await importAsMjs(
    "../src/js/dialog/social_image_editor_utils.js",
    "social_image_editor_utils.table.mjs"
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
// normalizeTableData
// ------------------------------------------------------------------

check(
    "normalize defaults",
    table.normalizeTableData(null),
    { rows: 3, cols: 3, header: true, cells: {} }
);
check(
    "normalize keeps in-range cells only",
    table.normalizeTableData({
        rows: 2,
        cols: 2,
        header: false,
        cellWidth: 120,
        cells: { "0,0": "A", "1,1": "B", "5,5": "drop", "0,2": "drop" },
    }),
    {
        rows: 2,
        cols: 2,
        header: false,
        cells: { "0,0": "A", "1,1": "B" },
        cellWidth: 120,
    }
);
check(
    "normalize clamps sides",
    table.normalizeTableData({ rows: 0, cols: 500 }).rows >= 1 &&
        table.normalizeTableData({ rows: 0, cols: 500 }).cols <= 50,
    true
);
checkTrue(
    "normalize stringifies cell values",
    table.normalizeTableData({ rows: 1, cols: 1, cells: { "0,0": 42 } })
        .cells["0,0"] === "42"
);

// ------------------------------------------------------------------
// Structural ops preserve cell contents
// ------------------------------------------------------------------

const base = table.normalizeTableData({
    rows: 2,
    cols: 2,
    header: true,
    cells: { "0,0": "H1", "0,1": "H2", "1,0": "A", "1,1": "B" },
});

{
    const t = table.addTableRow(base);
    check("add row appends", [t.rows, t.cols], [3, 2]);
    check(
        "add row keeps texts, shifts none",
        t.cells,
        { "0,0": "H1", "0,1": "H2", "1,0": "A", "1,1": "B" }
    );
}
{
    const t = table.addTableRow(base, 1);
    check(
        "insert row in the middle shifts below",
        t.cells,
        { "0,0": "H1", "0,1": "H2", "2,0": "A", "2,1": "B" }
    );
}
{
    const t = table.removeTableRow(base, 0);
    check("remove header row shifts body up", t.cells, { "0,0": "A", "0,1": "B" });
}
{
    const t = table.removeTableRow(table.normalizeTableData({ rows: 1, cols: 2 }));
    check("remove row never drops below one", t.rows, 1);
}
{
    const t = table.addTableColumn(base, 0);
    check(
        "insert column shifts right",
        t.cells,
        { "0,1": "H1", "0,2": "H2", "1,1": "A", "1,2": "B" }
    );
}
{
    const t = table.removeTableColumn(base, 1);
    check("remove column shifts left", t.cells, { "0,0": "H1", "1,0": "A" });
}
{
    const t = table.removeTableColumn(table.normalizeTableData({ rows: 2, cols: 1 }));
    check("remove column never drops below one", t.cols, 1);
}
check(
    "setTableCellText writes one cell",
    table.setTableCellText(base, 1, 0, "Edited").cells["1,0"],
    "Edited"
);
check(
    "setTableCellText ignores out of range",
    "2,0" in table.setTableCellText(base, 5, 0, "Nope").cells,
    false
);
check(
    "syncTableTexts merges edited entries",
    table.syncTableTexts(base, [
        { row: 0, col: 0, text: "Ny" },
        { row: 1, col: 1, text: "C" },
    ]).cells,
    { "0,0": "Ny", "0,1": "H2", "1,0": "A", "1,1": "C" }
);
checkTrue(
    "structural ops do not mutate the input",
    base.cells["1,1"] === "B" && base.rows === 2 && base.cols === 2
);

// ------------------------------------------------------------------
// buildTableGroup with a fabric stub
// ------------------------------------------------------------------

function makeFakeFabric() {
    class FakeRect {
        constructor(opts) {
            this.type = "rect";
            Object.assign(this, opts);
        }
        set(opts) {
            Object.assign(this, opts);
        }
        setCoords() {}
    }
    class FakeTextbox {
        constructor(text, opts) {
            this.type = "textbox";
            this.text = text;
            Object.assign(this, opts);
        }
        set(opts) {
            Object.assign(this, opts);
        }
        setCoords() {}
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
    }
    return { Rect: FakeRect, Textbox: FakeTextbox, Group: FakeGroup };
}

{
    const fabric = makeFakeFabric();
    const data = table.normalizeTableData({
        rows: 3,
        cols: 2,
        cellWidth: 100,
        cells: { "0,0": "Namn", "2,1": "Sista" },
    });
    const group = table.buildTableGroup(fabric, data);
    check(
        "group has rect + textbox per cell",
        group.getObjects().length,
        3 * 2 * 2
    );
    check(
        "group natural size",
        [group.width, group.height],
        [200, 3 * table.TABLE_CELL_HEIGHT]
    );
    checkTrue(
        "group carries _tableData",
        group[table.TABLE_PROP] && group[table.TABLE_PROP].rows === 3
    );
    const objects = group.getObjects();
    const firstRect = objects[0];
    const firstText = objects[1];
    check("first rect at origin", [firstRect.left, firstRect.top], [0, 0]);
    check(
        "first rect header fill",
        firstRect.fill,
        table.TABLE_HEADER_FILL
    );
    check("first text carries cell text", firstText.text, "Namn");
    check("first text carries cell markers", [firstText._tableCellRow, firstText._tableCellCol], [0, 0]);
    const lastText = objects[objects.length - 1];
    check(
        "last text is the bottom-right cell",
        [lastText._tableCellRow, lastText._tableCellCol, lastText.text],
        [2, 1, "Sista"]
    );
    // Row-major layout: cell (r, c) rect sits at (c * cellWidth, r * H).
    const cell21Rect = objects[(2 * 2 + 1) * 2];
    check(
        "cell rect positioned on the grid",
        [cell21Rect.left, cell21Rect.top],
        [100, 2 * table.TABLE_CELL_HEIGHT]
    );
    // Zebra: body row 1 (index 0 body) is white, body row 2 is the
    // alternating fill.
    const row1Rect = objects[(1 * 2 + 0) * 2];
    const row2Rect = objects[(2 * 2 + 0) * 2];
    check("body zebra alternates", [row1Rect.fill, row2Rect.fill], [
        table.TABLE_BODY_FILLS[0],
        table.TABLE_BODY_FILLS[1],
    ]);
}
{
    // Round trip: serialize through the EXTRA_PROPS contract like
    // _captureScene does, rebuild from the parsed JSON, structure and
    // texts intact.
    const fabric = makeFakeFabric();
    const data = table.normalizeTableData({
        rows: 2,
        cols: 3,
        cellWidth: 80,
        header: false,
        cells: { "0,0": "Ett", "1,2": "Två" },
    });
    const group = table.buildTableGroup(fabric, data);
    const serialized = {};
    for (const key of utils.EXTRA_PROPS) {
        if (group[key] !== undefined) {
            serialized[key] = group[key];
        }
    }
    const restored = table.normalizeTableData(
        JSON.parse(JSON.stringify(serialized[table.TABLE_PROP]))
    );
    const rebuilt = table.buildTableGroup(fabric, restored);
    check(
        "table data round-trips through EXTRA_PROPS",
        rebuilt[table.TABLE_PROP],
        group[table.TABLE_PROP]
    );
    checkTrue(
        "EXTRA_PROPS lists _tableData",
        utils.EXTRA_PROPS.includes("_tableData")
    );
}

if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
}

// ------------------------------------------------------------------
// Dialog edit isolation (task 3.2): double-click ungroups a table for
// cell editing; reassembly syncs the edited texts back into _tableData
// and restores the captured placement.
// ------------------------------------------------------------------

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
    `import * as __utils from ${JSON.stringify(join("/tmp", "social_image_editor_utils.table.mjs"))};`,
    `const { ${DIALOG_NAMES.join(", ")} } = __utils;`,
    `import * as __table from ${JSON.stringify(join("/tmp", "social_image_editor_table.smoke.mjs"))};`,
    "const { TABLE_PROP, addTableColumn, addTableRow, buildTableGroup, normalizeTableData, removeTableColumn, removeTableRow, starterTableData, syncTableTexts } = __table;",
    "const chartSpecToSvg = () => '';",
    "const substituteChartSpec = (spec) => spec;",
    "const CHART_SPEC_PROP = '_chartSpec';",
    "const qrContentToMatrix = () => [];",
    "const qrMatrixToRectSpecs = () => [];",
    "const initQrGenerator = () => {};",
    "const QR_PROP = '_qrContent';",
    "const loadQr = async () => ({});",
    "const Component = class {};",
    "const FileUploader = class {};",
    "const _t = (term) => term;",
    'const isTextType = (type) => ["textbox", "i-text", "text"].includes((type || "").toLowerCase());',
    'const isImageType = (type) => (type || "").toLowerCase() === "image";',
].join("\n");
const harnessTmp = join("/tmp", "social_image_editor_dialog.table.mjs");
writeFileSync(harnessTmp, `${preamble}\n${stripped}`);
const dialogMod = await import(harnessTmp);
const DialogClass = dialogMod.SocialImageEditorDialog;

function makeFakeFabricWithUtil() {
    const fabric = makeFakeFabric();
    // Identity placement math: a child's own calcTransformMatrix already
    // carries the absolute position for these fakes.
    fabric.util = {
        multiplyTransformMatrices: (_groupMatrix, childMatrix) => childMatrix,
        qrDecompose: (m) => ({
            translateX: m.tx,
            translateY: m.ty,
            scaleX: 1,
            scaleY: 1,
            angle: 0,
            skewX: 0,
            skewY: 0,
        }),
    };
    fabric.Group = class extends fabric.Group {
        calcTransformMatrix() {
            return { tx: this.left, ty: this.top };
        }
        set(opts) {
            Object.assign(this, opts);
        }
    };
    const baseRect = fabric.Rect;
    fabric.Rect = class extends baseRect {
        calcTransformMatrix() {
            return { tx: this._absX ?? this.left, ty: this._absY ?? this.top };
        }
    };
    const baseText = fabric.Textbox;
    fabric.Textbox = class extends baseText {
        calcTransformMatrix() {
            return { tx: this._absX ?? this.left, ty: this._absY ?? this.top };
        }
    };
    return fabric;
}

{
    const fabric = makeFakeFabricWithUtil();
    const data = table.normalizeTableData({
        rows: 2,
        cols: 2,
        cellWidth: 100,
        cells: { "0,0": "A", "1,1": "B" },
    });
    const group = table.buildTableGroup(fabric, data);
    group.left = 300;
    group.top = 120;
    group._layerId = "l_table";
    group._layerName = "Table";

    const other = { type: "rect", _layerId: "l_other" };
    const dlg = Object.create(DialogClass.prototype);
    dlg.props = { resModel: "social.image.template", resId: 1, close: () => {} };
    const objects = [other, group];
    let current = group;
    dlg._canvas = {
        getActiveObject: () => current,
        getObjects: () => objects,
        add: (obj) => {
            objects.push(obj);
            current = obj;
        },
        insertAt: (index, obj) => {
            objects.splice(index, 0, obj);
            current = obj;
        },
        remove: (obj) => {
            const i = objects.indexOf(obj);
            if (i >= 0) objects.splice(i, 1);
        },
        discardActiveObject: () => {
            current = null;
        },
        setActiveObject: (obj) => {
            current = obj;
        },
        requestRenderAll: () => {},
        renderAll: () => {},
    };
    dlg.state = {
        previewMode: false,
        tableEditing: null,
        message: "",
    };
    dlg._fabric = fabric;
    dlg._tableEdit = null;
    dlg._snapGuides = { lines: [], distances: [] };
    dlg._syncLayers = () => {};
    dlg._syncSelection = () => {};
    dlg._onCanvasChanged = () => {};
    dlg._showMessage = (text) => {
        dlg.state.message = text;
    };

    // Double-click enters edit isolation: group gone, cells loose.
    dlg._onCanvasDblClick({ target: group });
    checkTrue(
        "edit isolation removes the group from the canvas",
        !objects.includes(group) && objects.length === 9
    );
    check(
        "edit isolation exposes the session",
        [
            !!dlg._tableEdit,
            dlg.state.tableEditing && dlg.state.tableEditing.rows,
        ],
        [true, 2]
    );
    const looseTexts = objects.filter((o) => typeof o.text === "string");
    checkTrue(
        "loose cell texts are editable (selectable + evented)",
        looseTexts.every((o) => o.selectable && o.evented)
    );
    const looseRects = objects.filter((o) => o.type === "rect");
    checkTrue(
        "cell backgrounds stay inert while loose",
        looseRects.every((o) => !o.selectable && !o.evented)
    );

    // Simulate a cell edit, then reassemble.
    const cell00 = looseTexts.find(
        (o) => o._tableCellRow === 0 && o._tableCellCol === 0
    );
    cell00.text = "A edited";
    dlg._exitTableEdit(true);
    const rebuilt = objects[1];
    checkTrue(
        "reassembly leaves one grouped layer on the canvas",
        objects.length === 2 && rebuilt.type === "group"
    );
    checkTrue(
        "z-order slot preserved",
        objects[0] === other && objects[1] === rebuilt
    );
    check(
        "edited text synced back into _tableData",
        rebuilt[table.TABLE_PROP].cells["0,0"],
        "A edited"
    );
    check(
        "untouched cell text preserved",
        rebuilt[table.TABLE_PROP].cells["1,1"],
        "B"
    );
    check(
        "placement restored",
        [rebuilt.left, rebuilt.top],
        [300, 120]
    );
    check(
        "layer identity restored",
        [rebuilt._layerId, rebuilt._layerName],
        ["l_table", "Table"]
    );
    check("session cleared", dlg.state.tableEditing, null);
}
{
    // Clicking outside the loose cells reassembles too (commit path),
    // and markers survive the round trip through group children.
    const fabric = makeFakeFabricWithUtil();
    const group = table.buildTableGroup(
        fabric,
        table.normalizeTableData({
            rows: 1,
            cols: 1,
            cellWidth: 100,
            cells: { "0,0": "Solo" },
        })
    );
    group.left = 10;
    group.top = 20;
    // Strip the transient markers BEFORE entering edit isolation, like
    // a save/load round trip would (markers are never serialized).
    for (const child of group.getObjects()) {
        delete child._tableCellRow;
        delete child._tableCellCol;
    }
    const dlg = Object.create(DialogClass.prototype);
    dlg.props = { resModel: "social.image.template", resId: 1, close: () => {} };
    const objects = [group];
    dlg._canvas = {
        getActiveObject: () => null,
        getObjects: () => objects,
        add: (obj) => objects.push(obj),
        remove: (obj) => {
            const i = objects.indexOf(obj);
            if (i >= 0) objects.splice(i, 1);
        },
        discardActiveObject: () => {},
        setActiveObject: (obj) => {
            dlg._active = obj;
        },
        requestRenderAll: () => {},
        renderAll: () => {},
    };
    dlg.state = { previewMode: false, tableEditing: null, message: "" };
    dlg._fabric = fabric;
    dlg._tableEdit = null;
    dlg._syncLayers = () => {};
    dlg._syncSelection = () => {};
    dlg._onCanvasChanged = () => {};
    dlg._showMessage = () => {};
    dlg._onCanvasDblClick({ target: group });
    checkTrue("session opened via dblclick", !!dlg._tableEdit);
    const looseText = dlg._tableEdit.children.find(
        (o) => typeof o.text === "string"
    );
    looseText.text = "Reloaded edit";
    // Outside click: target is another object (not a loose child).
    dlg._onCanvasPointerDown({ target: { type: "rect" } });
    checkTrue(
        "outside click reassembles",
        !dlg._tableEdit && objects.length === 1
    );
    check(
        "markers re-derived from child order after reload",
        objects[0][table.TABLE_PROP].cells["0,0"],
        "Reloaded edit"
    );
    // dblclick on a non-table object is a no-op.
    dlg._onCanvasDblClick({ target: { type: "rect" } });
    checkTrue("dblclick outside a table does nothing", !dlg._tableEdit);
}

if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
}
console.log("all table checks passed");
