// Node lint and behavior test for the editor dialog: the OWL template,
// the dialog SCSS, and the close/message/capture paths of the dialog JS.
// Run: node social_image_creator/static/tests/social_image_editor_template.test.mjs
//
// OWL compiles every identifier in a template expression to a lookup on the
// component (`ctx.<name>`) unless it is one of OWL's reserved words. A bare
// JS global such as Number() therefore becomes ctx.Number, which does not
// exist, and the render dies with "ctx.Number is not a function". Nothing in
// the asset build catches this, so this test does.
//
// The behavior half drives the real dialog class under plain Node. The
// dialog is an Odoo OWL component, so its imports cannot resolve here; the
// same copy-to-/tmp trick as the other suites gets the utils module in, and
// for the dialog the import block is stripped and the few module-scope
// symbols the class definition touches (Component, FileUploader, _t,
// EXTRA_PROPS) are stubbed. The methods under test (close, _flushSave,
// _captureScene, _showMessage, _onKeyDown, deleteSelected) only touch
// instance fields, which the tests set on a bare instance.

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const xml = readFileSync(
    join(here, "../src/xml/social_image_editor_dialog.xml"),
    "utf8"
);
const scss = readFileSync(
    join(here, "../src/scss/social_image_editor_dialog.scss"),
    "utf8"
);
const dialogSource = readFileSync(
    join(here, "../src/js/dialog/social_image_editor_dialog.js"),
    "utf8"
);

function importAsMjs(relSource, tmpName) {
    const source = readFileSync(join(here, relSource), "utf8");
    const tmp = join("/tmp", tmpName);
    writeFileSync(tmp, source);
    return import(tmp);
}

let failures = 0;
function checkTrue(name, cond, detail) {
    if (!cond) {
        failures += 1;
        console.error(`FAIL ${name}${detail ? `: ${detail}` : ""}`);
    } else {
        console.log(`ok ${name}`);
    }
}
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
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ------------------------------------------------------------------
// Behavior harness: the real dialog class with stripped imports
// ------------------------------------------------------------------

const utils = await importAsMjs(
    "../src/js/dialog/social_image_editor_utils.js",
    "social_image_editor_utils.template.mjs"
);

const stripped = dialogSource
    .replace(/^import\b[^;]*;/gm, "")
    .replace("export class SocialImageEditorDialog", "class SocialImageEditorDialog")
    .concat("\nexport { SocialImageEditorDialog };\n");
// The dialog under test references the pure utils and the shape-library
// type guards by bare identifier; the harness import block is stripped,
// so re-declare them from the real utils module and small stubs.
const UTIL_NAMES = [
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
    "restoreSceneProps",
    "roundToGrid",
    "snapBoxFromRect",
    "snapBoxToGuides",
    "stashSceneProps",
    "toHexColor",
    "widestLine",
];
const preamble = [
    `import * as __utils from ${JSON.stringify(join("/tmp", "social_image_editor_utils.template.mjs"))};`,
    `const { ${UTIL_NAMES.join(", ")} } = __utils;`,
    "const Component = class {};",
    "const FileUploader = class {};",
    "const _t = (term) => term;",
    "const isTextType = (type) => [\"textbox\", \"i-text\", \"text\"].includes((type || \"\").toLowerCase());",
    "const isImageType = (type) => (type || \"\").toLowerCase() === \"image\";",
].join("\n");
const harnessTmp = join("/tmp", "social_image_editor_dialog.template.mjs");
writeFileSync(harnessTmp, `${preamble}\n${stripped}`);
const dialogMod = await import(harnessTmp);
const DialogClass = dialogMod.SocialImageEditorDialog;

// A bare instance with the fields the tested methods read. The canvas is a
// stub: object events are not synthesized, so nothing outside the called
// method runs.
function makeDialog({ orm, activeObject = null, objects = [] } = {}) {
    const dlg = Object.create(DialogClass.prototype);
    let closed = 0;
    dlg.props = {
        resModel: "social.image.template",
        resId: 1,
        close: () => {
            closed += 1;
        },
    };
    dlg.closedCount = () => closed;
    dlg.orm = orm;
    dlg.state = {
        busy: false,
        previewMode: false,
        saveState: "dirty",
        message: "",
        hasSelection: !!activeObject,
        iconPickerOpen: false,
        iconFilter: "",
        mediaPickerOpen: false,
        mediaFilter: "",
        fontPickerOpen: false,
        fontFilter: "",
        shapesOpen: false,
        gridMenuOpen: false,
        gridVisible: false,
        gridSnap: false,
        gridSpacing: 16,
        insertDataOpen: false,
        insertDataStep: "model",
        insertDataSearch: "",
        insertDataResults: [],
        insertDataFieldFilter: "",
        insertDataField: null,
        bindingModel: null,
        bindingModelName: "",
        bindingFields: [],
        inspector: { isText: false, isImage: false },
        penMode: false,
    };
    const removed = [];
    let current = activeObject;
    dlg._removed = removed;
    dlg._snapGuides = { lines: [], distances: [] };
    dlg._snapAlt = false;
    dlg._snapShift = false;
    dlg._moveStart = null;
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
        remove: (obj) => removed.push(obj),
        discardActiveObject: () => {
            current = null;
        },
        setActiveObject: (obj) => {
            current = obj;
        },
        requestRenderAll: () => {},
        renderAll: () => {},
        getWidth: () => 1200,
        getHeight: () => 630,
        getZoom: () => 1,
        viewportTransform: [1, 0, 0, 1, 0, 0],
        toObject: () => ({ version: "6.9.1", objects: [] }),
        toSVG: () => '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        contextContainer: undefined,
    };
    dlg._variants = [
        { name: "Primary", width: 1200, height: 630, scene_json: "{}", is_primary: true },
    ];
    dlg._primaryIndex = 0;
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
    return dlg;
}

// window stubs: DOMPurify stays undefined (sanitize skipped), confirm is
// set per test, the pointer listeners are no-ops.
globalThis.window = {
    addEventListener: () => {},
    removeEventListener: () => {},
    confirm: () => false,
};

// ------------------------------------------------------------------
// A. Close safety: flush failure keeps the dialog open with the edits
// ------------------------------------------------------------------

const failingOrm = {
    write: async () => {
        throw new Error("network down");
    },
};
{
    const dlg = makeDialog({ orm: failingOrm });
    dlg._dirty = true;
    await dlg.close();
    checkTrue("failed flush keeps the dialog open", dlg.closedCount() === 0);
    check("save state is error", dlg.state.saveState, "error");
    checkTrue(
        "message line carries the error",
        typeof dlg.state.message === "string" &&
            dlg.state.message.includes("Autosave failed")
    );
    checkTrue("edits kept (dirty flag)", dlg._dirty === true);
    checkTrue("second attempt will ask for discard", dlg._closeFailed === true);
    dlg.dismissMessage();

    // Second attempt after the failure, discard cancelled: stays open.
    window.confirm = () => false;
    await dlg.close();
    checkTrue("cancelled discard keeps the dialog open", dlg.closedCount() === 0);
    checkTrue("edits survive until discard is confirmed", dlg._dirty === true);
    dlg.dismissMessage();

    // Third attempt, discard confirmed: closes unsaved.
    window.confirm = () => true;
    await dlg.close();
    checkTrue("confirmed discard closes unsaved", dlg.closedCount() === 1);
}
{
    const okOrm = { write: async () => {} };
    const dlg = makeDialog({ orm: okOrm });
    dlg._dirty = true;
    await dlg.close();
    checkTrue("successful flush closes cleanly", dlg.closedCount() === 1);
    check("save state saved", dlg.state.saveState, "saved");

    const dlgBusy = makeDialog({ orm: okOrm });
    dlgBusy._dirty = true;
    dlgBusy._saving = true;
    await dlgBusy.close();
    checkTrue(
        "close blocked while a save is in flight",
        dlgBusy.closedCount() === 0
    );
}
{
    // Retry button: same save, recovered ORM.
    let fail = true;
    const flakyOrm = {
        write: async () => {
            if (fail) {
                throw new Error("down");
            }
        },
    };
    const dlg = makeDialog({ orm: flakyOrm });
    dlg._dirty = true;
    await dlg.close();
    checkTrue("failure keeps the dialog open", dlg.closedCount() === 0);
    fail = false;
    await dlg.retrySave();
    check("retry success clears the error state", dlg.state.saveState, "saved");
    checkTrue("retry success clears the message", dlg.state.message === "");
}

// ------------------------------------------------------------------
// B. Keyboard: Delete/Backspace, Escape unwind, editing suppression
// ------------------------------------------------------------------

const keyEvent = (key) => ({
    key,
    target: { tagName: "DIV" },
    preventDefault: () => {},
});
{
    const target = { type: "textbox", text: "Hello" };
    const dlg = makeDialog({ activeObject: target, objects: [target] });
    dlg._onKeyDown(keyEvent("Delete"));
    checkTrue(
        "Delete removes the active selection",
        dlg._removed.length === 1 && dlg._removed[0] === target
    );
}
{
    const editing = { type: "textbox", text: "Hello", isEditing: true };
    const dlg = makeDialog({ activeObject: editing, objects: [editing] });
    dlg._onKeyDown(keyEvent("Backspace"));
    checkTrue(
        "Backspace suppressed while a text object is editing",
        dlg._removed.length === 0
    );
}
{
    const dlg = makeDialog({ orm: { write: async () => {} } });
    const escape = () => dlg._onKeyDown(keyEvent("Escape"));
    dlg.state.iconPickerOpen = true;
    dlg.state.mediaPickerOpen = true;
    dlg.state.fontPickerOpen = true;
    dlg.state.shapesOpen = true;
    dlg.state.gridMenuOpen = true;
    dlg.state.insertDataOpen = true;
    escape();
    checkTrue(
        "first Escape closes the icon picker",
        !dlg.state.iconPickerOpen && dlg.state.mediaPickerOpen
    );
    escape();
    checkTrue(
        "second Escape closes the media picker",
        !dlg.state.mediaPickerOpen && dlg.state.fontPickerOpen
    );
    escape();
    checkTrue(
        "third Escape closes the font picker",
        !dlg.state.fontPickerOpen && dlg.state.shapesOpen
    );
    escape();
    checkTrue(
        "fourth Escape closes the shapes menu",
        !dlg.state.shapesOpen && dlg.state.gridMenuOpen
    );
    escape();
    checkTrue(
        "fifth Escape closes the grid menu",
        !dlg.state.gridMenuOpen && dlg.state.insertDataOpen
    );
    escape();
    checkTrue("sixth Escape closes the insert data panel", !dlg.state.insertDataOpen);
    escape();
    await sleep(10);
    checkTrue("seventh Escape closes the dialog", dlg.closedCount() === 1);
}

// Source-order lint: the handler body wires Delete and the Escape unwind.
{
    const kdStart = dialogSource.indexOf("_onKeyDown(ev) {");
    const kdEnd = dialogSource.indexOf("// Autosave", kdStart);
    const kdBody = dialogSource.slice(kdStart, kdEnd);
    const delAt = kdBody.indexOf('key === "delete"');
    const delCall = kdBody.indexOf("this.deleteSelected()");
    const escAt = kdBody.indexOf('key === "escape"');
    const pickerIdx = [
        "iconPickerOpen",
        "mediaPickerOpen",
        "fontPickerOpen",
        "shapesOpen",
        "gridMenuOpen",
        "insertDataOpen",
    ].map((name) => kdBody.indexOf(`this.state.${name}`));
    checkTrue(
        "keydown handler removes the selection on Delete/Backspace",
        delAt >= 0 && delCall > delAt
    );
    checkTrue(
        "editing guard runs before the Delete branch",
        kdBody.indexOf("active.isEditing") >= 0 &&
            kdBody.indexOf("active.isEditing") < delAt
    );
    checkTrue(
        "Escape unwinds pickers in order, then closes the dialog",
        escAt >= 0 &&
            pickerIdx.every((i) => i > escAt) &&
            pickerIdx.every((v, i) => i === 0 || v > pickerIdx[i - 1]) &&
            kdBody.indexOf("this.close()") > pickerIdx[pickerIdx.length - 1]
    );
}

// ------------------------------------------------------------------
// C. i18n lint: user-facing literals in the dialog JS go through _t()
// ------------------------------------------------------------------
//
// Pragmatic heuristic, not a parser: it flags the unambiguous sinks
// (message assignments, alert/confirm/prompt, throw new Error) when they
// carry a raw string literal. Markup builders (icon SVG, canvas defaults)
// are covered by the manual sweep, not by this lint.

checkTrue(
    "dialog JS imports _t",
    dialogSource.includes('import { _t } from "@web/core/l10n/translation";')
);
{
    const offenders = [];
    dialogSource.split("\n").forEach((line, idx) => {
        const trimmed = line.trim();
        const msgAssign = trimmed.match(/\.message\s*=(?!=)\s*(["'`])/);
        if (msgAssign && !trimmed.includes("_t(")) {
            const quote = msgAssign[1];
            const start = trimmed.indexOf(quote, trimmed.indexOf("=") + 1);
            const rest = trimmed.slice(start + 1);
            const isEmptyReset = rest.startsWith(quote);
            if (!isEmptyReset) {
                offenders.push(`line ${idx + 1}: message assignment without _t()`);
            }
        }
        if (
            /\b(?:window\.)?(?:alert|confirm|prompt)\(\s*["'`]/.test(trimmed) &&
            !trimmed.includes("_t(")
        ) {
            offenders.push(
                `line ${idx + 1}: dialog-style call with a raw string literal`
            );
        }
        if (/throw new Error\(\s*["'`]/.test(trimmed) && !trimmed.includes("_t(")) {
            offenders.push(`line ${idx + 1}: throw new Error with a raw string literal`);
        }
    });
    checkTrue(
        "dialog JS: no raw user-facing literals (i18n lint)",
        offenders.length === 0,
        `\n  ${offenders.join("\n  ")}`
    );
}

// ------------------------------------------------------------------
// D. Message lifecycle: dismiss + auto-clear
// ------------------------------------------------------------------

{
    const realSetTimeout = globalThis.setTimeout;
    const realClearTimeout = globalThis.clearTimeout;
    const timers = [];
    globalThis.setTimeout = (fn, ms) => {
        const t = { fn, ms, cleared: false };
        timers.push(t);
        return t;
    };
    globalThis.clearTimeout = (t) => {
        if (t) {
            t.cleared = true;
        }
    };
    try {
        const dlg = makeDialog();
        dlg._showMessage("boom");
        check("message is shown", dlg.state.message, "boom");
        checkTrue("auto-clear timer scheduled", timers.length === 1);
        dlg.dismissMessage();
        check("manual dismiss clears the message", dlg.state.message, "");
        checkTrue("manual dismiss cancels the timer", timers[0].cleared === true);

        dlg._showMessage("one");
        dlg._showMessage("two");
        checkTrue("a new message reschedules the timer", timers.length === 3);
        timers[1].fn(); // stale timer fires; must not clear the newer message
        check("stale timer keeps the newer message", dlg.state.message, "two");
        timers[2].fn(); // current timer fires
        check("current timer auto-clears the message", dlg.state.message, "");
    } finally {
        globalThis.setTimeout = realSetTimeout;
        globalThis.clearTimeout = realClearTimeout;
    }
}
checkTrue(
    "message bar wiring: dismiss + retry + auto-clear",
    /t-on-click="dismissMessage"/.test(xml) &&
        /aria-label="Dismiss"/.test(xml) &&
        /t-on-click="retrySave"/.test(xml) &&
        /MESSAGE_TIMEOUT_MS/.test(dialogSource)
);

// ------------------------------------------------------------------
// E. Capture keeps raw token text; transform/autofit persist as props
// ------------------------------------------------------------------

{
    const tokenObj = {
        type: "textbox",
        text: "{{name}}",
        fontSize: 40,
        width: 200,
        _textTransform: "upper",
        _overflow: "autofit",
        set(key, value) {
            this[key] = value;
        },
        toObject() {
            return {
                type: this.type,
                text: this.text,
                fontSize: this.fontSize,
                _textTransform: this._textTransform,
                _overflow: this._overflow,
            };
        },
    };
    const dlg = makeDialog({ objects: [tokenObj] });
    const scene = dlg._captureScene();
    check(
        "captured scene text is the raw token",
        scene.objects[0].text,
        "{{name}}"
    );
    check("transform prop persists", scene.objects[0]._textTransform, "upper");
    check("overflow prop persists", scene.objects[0]._overflow, "autofit");
    checkTrue("live object text untouched", tokenObj.text === "{{name}}");
}
{
    const capStart = dialogSource.indexOf("_captureScene() {");
    const capEnd = dialogSource.indexOf("_pushHistory()", capStart);
    const capBody = dialogSource.slice(capStart, capEnd);
    checkTrue(
        "_captureScene no longer derives text props",
        capStart >= 0 && capEnd > capStart && !capBody.includes("_applyTextPropsToAll")
    );
}
checkTrue(
    "inspector copy: case transform applies at render",
    xml.includes("Case transform (applies at render)")
);
checkTrue(
    "inspector copy: autofit applies at render",
    xml.includes("Autofit (shrink to fit at render)")
);

// ------------------------------------------------------------------
// F. Grid: toolbar markup, prefs round trip, snapping, painter
// (tasks 1.1-1.3)
// ------------------------------------------------------------------

checkTrue(
    "toolbar: grid toggle + spacing dropdown + snap switch",
    /t-on-click="toggleGrid"/.test(xml) &&
        /t-on-click="toggleGridMenu"/.test(xml) &&
        /gridSpacingPresets\(\)/.test(xml) &&
        /t-on-change="onGridSnapChange"/.test(xml) &&
        /t-ref="gridMenuRef"/.test(xml)
);
checkTrue(
    "grid JS: prefs key + presets wired",
    dialogSource.includes('"social_image_editor_grid"') &&
        dialogSource.includes("_readGridPrefs") &&
        dialogSource.includes("_writeGridPrefs") &&
        dialogSource.includes('this._canvas.on("object:scaling"')
);
{
    // Source wiring: the grid paints from the after:render chain on
    // contextTop (never the scene), guarded by state.gridVisible and
    // zoom-aware like the guides.
    const ovStart = dialogSource.indexOf("_drawOverlays() {");
    const ovEnd = dialogSource.indexOf("_drawGrid(ctx) {", ovStart);
    const ovBody = dialogSource.slice(ovStart, ovEnd);
    checkTrue(
        "overlays hook: clear, grid, guides on contextTop",
        ovStart >= 0 &&
            ovEnd > ovStart &&
            ovBody.includes("contextTop") &&
            ovBody.includes("clearContext(ctx)") &&
            ovBody.includes("_drawGrid(ctx)") &&
            ovBody.includes("_drawSnapGuides(ctx)")
    );
    const gridStart = ovEnd;
    const gridEnd = dialogSource.indexOf("_drawSnapGuides(ctx) {", gridStart);
    const gridBody = dialogSource.slice(gridStart, gridEnd);
    checkTrue(
        "grid painter: visible guard, computeGridLines, zoom-multiplied",
        gridStart >= 0 &&
            gridEnd > gridStart &&
            gridBody.includes("state.gridVisible") &&
            gridBody.includes("computeGridLines(") &&
            gridBody.includes("g.at * z") &&
            !gridBody.includes("fc.add(")
    );
    // Snapping order: grid rounding runs after the guide selection and
    // yields per axis (guide keeps priority), in both move and scaling.
    const mvStart = dialogSource.indexOf("_onObjectMoving(ev) {");
    const mvEnd = dialogSource.indexOf("_onObjectScaling(ev) {", mvStart);
    const mvBody = dialogSource.slice(mvStart, mvEnd);
    checkTrue(
        "grid snap after guide selection, per axis",
        mvStart >= 0 &&
            mvEnd > mvStart &&
            mvBody.indexOf("roundToGrid(") > mvBody.indexOf("snapBoxToGuides(") &&
            mvBody.includes("snap.vAt == null") &&
            mvBody.includes("snap.hAt == null") &&
            mvBody.includes("!spacing.dx") &&
            mvBody.includes("!spacing.dy")
    );
    const scEnd = dialogSource.indexOf("_drawOverlays() {", mvEnd);
    const scBody = dialogSource.slice(mvEnd, scEnd);
    checkTrue(
        "scaling snap: alt-aware footprint rounding",
        scBody.includes("roundToGrid(") &&
            scBody.includes("obj.scaleX") &&
            scBody.includes("_snapAlt")
    );
}

function makeMoving(left, top, width = 40, height = 20) {
    return {
        left,
        top,
        width,
        height,
        getBoundingRect() {
            return {
                left: this.left,
                top: this.top,
                width: this.width,
                height: this.height,
            };
        },
        setCoords() {},
    };
}

{
    // Plain grid snap with no other objects: position rounds to the
    // nearest intersection.
    const dlg = makeDialog();
    dlg.state.gridSnap = true;
    dlg.state.gridSpacing = 16;
    const moving = makeMoving(13, 27);
    dlg._onObjectMoving({ target: moving });
    check("grid snap rounds left/top", [moving.left, moving.top], [16, 32]);
}
{
    // Snap toggle off: the raw drag position survives.
    const dlg = makeDialog();
    const moving = makeMoving(13, 27);
    dlg._onObjectMoving({ target: moving });
    check("grid snap off leaves position", [moving.left, moving.top], [13, 27]);
}
{
    // Guide priority: the other object's right edge at x=100 is within
    // the guide threshold of the moving box's right edge (99), so the
    // x axis follows the guide (left becomes 60); the free y axis
    // still snaps to the grid.
    const dlg = makeDialog();
    dlg.state.gridSnap = true;
    dlg.state.gridSpacing = 16;
    const other = makeMoving(100, 400);
    dlg._canvas.getObjects = () => [other];
    const moving = makeMoving(59, 27);
    dlg._onObjectMoving({ target: moving });
    check("guide wins over grid on its axis", moving.left, 60);
    check("grid still snaps the free axis", moving.top, 32);
}
{
    // Alt bypasses grid snap together with the guides.
    const dlg = makeDialog();
    dlg.state.gridSnap = true;
    dlg._snapAlt = true;
    const moving = makeMoving(13, 27);
    dlg._onObjectMoving({ target: moving });
    check("alt bypasses grid snap", [moving.left, moving.top], [13, 27]);
}
{
    // Scaling snaps the scaled footprint (width*scaleX, height*scaleY).
    const dlg = makeDialog();
    dlg.state.gridSnap = true;
    dlg.state.gridSpacing = 16;
    const obj = { width: 100, height: 50, scaleX: 0.37, scaleY: 1, setCoords() {} };
    dlg._onObjectScaling({ target: obj });
    check("scaling snaps footprint", [obj.scaleX, obj.scaleY], [0.32, 0.96]);
}
{
    const dlg = makeDialog();
    const obj = { width: 100, height: 50, scaleX: 0.37, scaleY: 1, setCoords() {} };
    dlg._onObjectScaling({ target: obj });
    check("scaling snap off untouched", [obj.scaleX, obj.scaleY], [0.37, 1]);
    const dlgAlt = makeDialog();
    dlgAlt.state.gridSnap = true;
    dlgAlt._snapAlt = true;
    const objAlt = { width: 100, height: 50, scaleX: 0.37, scaleY: 1, setCoords() {} };
    dlgAlt._onObjectScaling({ target: objAlt });
    check("alt bypasses scaling snap", objAlt.scaleX, 0.37);
}
{
    // The painter draws clipped segments on the contextTop 2d context
    // only while the grid is visible, and never touches the scene.
    const runPainter = (visible) => {
        const strokes = [];
        const dlg = makeDialog();
        dlg.state.gridVisible = visible;
        dlg.state.gridSpacing = 16;
        dlg._canvas.contextTop = {
            save: () => strokes.push(["save"]),
            restore: () => strokes.push(["restore"]),
            beginPath: () => strokes.push(["begin"]),
            moveTo: (x, y) => strokes.push(["m", x, y]),
            lineTo: (x, y) => strokes.push(["l", x, y]),
            stroke: () => strokes.push(["stroke"]),
        };
        dlg._canvas.clearContext = () => strokes.push(["clear"]);
        dlg._drawOverlays();
        return { strokes, scene: dlg._canvas.getObjects() };
    };
    const on = runPainter(true);
    checkTrue(
        "grid painter draws segments on contextTop",
        on.strokes.filter((s) => s[0] === "l").length > 0,
        JSON.stringify(on.strokes)
    );
    checkTrue("overlays clear the top context first", on.strokes[0][0] === "clear");
    check("grid painter adds no scene objects", on.scene.length, 0);
    const off = runPainter(false);
    check(
        "grid hidden paints nothing",
        off.strokes.filter((s) => s[0] === "l").length,
        0
    );
}
{
    // Prefs round trip through localStorage; unknown values fall back.
    const store = new Map();
    window.localStorage = {
        getItem: (k) => (store.has(k) ? store.get(k) : null),
        setItem: (k, v) => store.set(k, v),
    };
    try {
        const dlg = makeDialog();
        dlg.state.gridVisible = true;
        dlg.state.gridSnap = true;
        dlg.state.gridSpacing = 32;
        dlg._writeGridPrefs();
        check(
            "grid prefs persisted",
            JSON.parse(store.get("social_image_editor_grid")),
            { visible: true, snap: true, spacing: 32 }
        );
        check("grid prefs read back", dlg._readGridPrefs(), {
            visible: true,
            snap: true,
            spacing: 32,
        });
        store.set("social_image_editor_grid", '{"spacing": 13}');
        check("unknown spacing falls back", dlg._readGridPrefs().spacing, 16);
    } finally {
        delete window.localStorage;
    }
}
{
    // Toolbar actions.
    const dlg = makeDialog();
    let renders = 0;
    dlg._canvas.requestRenderAll = () => renders++;
    dlg.toggleGrid();
    check("grid toggle flips visible", dlg.state.gridVisible, true);
    checkTrue("grid toggle re-renders the canvas", renders === 1);
    dlg.setGridSpacing(8);
    check("spacing preset applied", dlg.state.gridSpacing, 8);
    dlg.setGridSpacing(13);
    check("unknown spacing falls back to default", dlg.state.gridSpacing, 16);
    dlg.onGridSnapChange({ target: { checked: true } });
    check("snap checkbox applied", dlg.state.gridSnap, true);
}

// ------------------------------------------------------------------
// G. Insert Dynamic Data flow (tasks 2.1-2.3)
// ------------------------------------------------------------------

checkTrue(
    "toolbar: insert dynamic data button + stepped panel",
    /t-on-click="toggleInsertDataPanel"/.test(xml) &&
        xml.includes("Insert Dynamic Data") &&
        xml.includes("state.insertDataStep === 'model'") &&
        xml.includes("state.insertDataStep === 'field'") &&
        xml.includes("state.insertDataStep === 'target'") &&
        /t-on-click="onInsertDataTokenClick"/.test(xml) &&
        /t-on-click="onInsertDataBindImageClick"/.test(xml) &&
        /t-ref="insertDataRef"/.test(xml)
);
checkTrue(
    "insert data JS: model search domain excludes transient/abstract",
    dialogSource.includes('["transient", "=", false]') &&
        dialogSource.includes('["abstract", "=", false]') &&
        dialogSource.includes('_t("Insert Dynamic Data")')
);

function makeInsertOrm() {
    return {
        written: [],
        async call(model, method, args) {
            if (model === "ir.model" && method === "name_search") {
                return [
                    [1, "Contact"],
                    [2, "Product"],
                ];
            }
            if (method === "get_binding_fields") {
                return [
                    { name: "name", type: "char", field_description: "Name" },
                    { name: "image_1920", type: "binary", field_description: "Image" },
                ];
            }
            return [];
        },
        async read() {
            return [{ id: 1, model: "res.partner" }];
        },
        async write(model, ids, vals) {
            this.written.push(vals);
        },
    };
}

{
    // No binding model: the panel opens at the model step, preloads
    // the search, and picking one persists model_id via the normal
    // ORM write before the field step.
    const orm = makeInsertOrm();
    const dlg = makeDialog({ orm });
    dlg.toggleInsertDataPanel();
    check("panel opens", dlg.state.insertDataOpen, true);
    check("model step without binding model", dlg.state.insertDataStep, "model");
    await sleep(0);
    check("model search preloaded", dlg.state.insertDataResults.length, 2);
    await dlg.onInsertModelPicked({ id: 1, name: "Contact" });
    check("model persisted via orm.write", orm.written, [{ model_id: 1 }]);
    check(
        "binding model set",
        [dlg.state.bindingModel, dlg.state.bindingModelName],
        [1, "res.partner"]
    );
    check("fields loaded from get_binding_fields", dlg.state.bindingFields.length, 2);
    check("flow continues at field step", dlg.state.insertDataStep, "field");
}
{
    // With a binding model the flow starts at the field step.
    const orm = makeInsertOrm();
    const dlg = makeDialog({ orm });
    dlg.state.bindingModel = 1;
    dlg.state.bindingModelName = "res.partner";
    dlg.state.bindingFields = [
        { name: "name", type: "char", field_description: "Name" },
    ];
    dlg.toggleInsertDataPanel();
    check("field step with binding model", dlg.state.insertDataStep, "field");
    dlg.state.insertDataFieldFilter = "nomatch";
    check("field filter narrows", dlg.filteredInsertDataFields().length, 0);
    dlg.state.insertDataFieldFilter = "na";
    check("field filter matches name", dlg.filteredInsertDataFields().length, 1);
    await dlg.onInsertDataFieldPicked(dlg.state.bindingFields[0]);
    check("target step after field pick", dlg.state.insertDataStep, "target");
    check("token preview", dlg.insertDataToken(), "{{name}}");
    dlg.onInsertDataStepBack();
    check("back returns to field step", dlg.state.insertDataStep, "field");
}
{
    // Target step, text action with an active text layer: the token
    // lands at the caret and parses with the binding token regex.
    const text = {
        type: "textbox",
        text: "Hej ",
        isEditing: false,
        selectionStart: 4,
        selectionEnd: 4,
        set(key, value) {
            this[key] = value;
        },
    };
    const dlg = makeDialog({ activeObject: text, objects: [text] });
    dlg._syncSelection = () => {};
    dlg._onCanvasChanged = () => {};
    dlg.state.insertDataField = { name: "name", type: "char" };
    dlg.onInsertDataTokenClick();
    check("token inserted into active text", text.text, "Hej {{name}}");
    check(
        "inserted token parses with BINDING_TOKEN_RE",
        (text.text.match(utils.BINDING_TOKEN_RE) || []).length,
        1
    );
    check("panel closed after insert", dlg.state.insertDataOpen, false);
}
{
    // Target step, text action with no text layer: a new textbox
    // holding the token appears at the canvas center.
    const dlg = makeDialog();
    dlg._syncSelection = () => {};
    dlg._onCanvasChanged = () => {};
    dlg._fabric = {
        Textbox: class {
            constructor(text, opts) {
                this.type = "textbox";
                this.text = text;
                Object.assign(this, opts);
            }
        },
    };
    dlg.state.insertDataField = { name: "name", type: "char" };
    dlg.onInsertDataTokenClick();
    const created = dlg._canvas.getObjects()[0];
    checkTrue("token textbox created", !!created);
    check("new textbox holds the token", created.text, "{{name}}");
    check("new textbox centered", [created.left, created.top], [450, 291]);
    checkTrue("new textbox selected", dlg._canvas.getActiveObject() === created);
}
{
    // Target step, image action: a binary field binds the active image
    // layer through the same _dataBinding path as the Data panel.
    const img = { type: "image" };
    const dlg = makeDialog({ activeObject: img, objects: [img] });
    dlg._syncSelection = () => {};
    dlg._onCanvasChanged = () => {};
    dlg.state.inspector = { isImage: true };
    dlg.state.insertDataField = { name: "image_1920", type: "binary" };
    checkTrue("bind offered for binary field + image layer", dlg.insertDataCanBindImage());
    dlg.onInsertDataBindImageClick();
    check("image layer bound", img._dataBinding, { field: "image_1920" });
    check("panel closed after bind", dlg.state.insertDataOpen, false);
}
{
    // Binary field but no image layer active: binding is refused.
    const dlg = makeDialog();
    dlg._syncSelection = () => {};
    dlg._onCanvasChanged = () => {};
    dlg.state.insertDataField = { name: "image_1920", type: "binary" };
    checkTrue("bind needs an active image layer", !dlg.insertDataCanBindImage());
    dlg.onInsertDataBindImageClick();
    checkTrue("bind without image is a no-op", dlg._canvas.getObjects().length === 0);
}

// ------------------------------------------------------------------
// H. Chart, table and QR elements (tasks 3.x-5.x): toolbar lint,
// panels, capture round-trip, Escape unwind
// ------------------------------------------------------------------

checkTrue(
    "toolbar: table/chart/QR entries with popovers",
    /t-on-click="toggleTableMenu"/.test(xml) &&
        /t-on-click="insertTable"/.test(xml) &&
        /t-ref="tableMenuRef"/.test(xml) &&
        /t-on-click="toggleChartMenu"/.test(xml) &&
        /chartTypeOptions\(\)/.test(xml) &&
        /t-on-click="\(\) => this\.insertChart\(opt\.type\)"/.test(xml) &&
        /t-ref="chartMenuRef"/.test(xml) &&
        /t-on-click="toggleQrMenu"/.test(xml) &&
        /t-on-click="insertQr"/.test(xml) &&
        /t-ref="qrMenuRef"/.test(xml)
);
checkTrue(
    "QR insert: inline error slot wired",
    /o_social_image_editor_qr_error/.test(xml) &&
        dialogSource.includes("this.state.qrError") &&
        dialogSource.includes("insertQr()") &&
        dialogSource.includes("_ensureQrLib")
);
checkTrue(
    "properties panel: chart/table/QR editors + editing banner",
    /o_social_image_editor_chart_props/.test(xml) &&
        /onChartTypeChange/.test(xml) &&
        /onChartCellChange/.test(xml) &&
        /onChartAddCategory/.test(xml) &&
        /onChartAddSeries/.test(xml) &&
        /o_social_image_editor_table_props/.test(xml) &&
        /onTableAddRow/.test(xml) &&
        /onTableRemoveRow/.test(xml) &&
        /onTableAddColumn/.test(xml) &&
        /onTableRemoveColumn/.test(xml) &&
        /o_social_image_editor_qr_props/.test(xml) &&
        /onQrContentChange/.test(xml) &&
        /o_social_image_editor_table_editing/.test(xml) &&
        /_exitTableEdit\(true\)/.test(xml)
);
checkTrue(
    "inspector carries chart/qr/table copies",
    dialogSource.includes("inspector.chart = obj[CHART_SPEC_PROP]") &&
        dialogSource.includes('inspector.qrContent =') &&
        dialogSource.includes("inspector.table = obj[TABLE_PROP]")
);
checkTrue(
    "EXTRA_PROPS carries the three new props",
    utils.EXTRA_PROPS.includes("_tableData") &&
        utils.EXTRA_PROPS.includes("_chartSpec") &&
        utils.EXTRA_PROPS.includes("_qrContent")
);
{
    // Capture round trip: the three new props survive EXTRA_PROPS
    // serialization exactly like the binding props do.
    const dynamicGroup = {
        type: "group",
        _layerId: "l_dyn",
        _tableData: {
            rows: 2,
            cols: 2,
            header: true,
            cellWidth: 120,
            cells: { "0,0": "Reg", "1,1": "100%" },
        },
        _chartSpec: {
            version: 1,
            type: "bar-v",
            title: "{{categ.name}}",
            categories: ["A"],
            series: [{ name: "S", values: ["{{product.weight}}"] }],
            options: { width: 480, height: 320 },
        },
        _qrContent: "{{product.default_code}}",
        toObject(extraProps) {
            const out = { type: this.type };
            for (const key of extraProps) {
                if (this[key] !== undefined) {
                    out[key] = this[key];
                }
            }
            return out;
        },
    };
    const dlg = makeDialog({ objects: [dynamicGroup] });
    const scene = dlg._captureScene();
    const json = JSON.parse(JSON.stringify(scene));
    check(
        "_tableData survives the capture round trip",
        json.objects[0]._tableData.cells,
        { "0,0": "Reg", "1,1": "100%" }
    );
    check(
        "_chartSpec survives the capture round trip",
        json.objects[0]._chartSpec.series[0].values,
        ["{{product.weight}}"]
    );
    check(
        "_qrContent survives the capture round trip",
        json.objects[0]._qrContent,
        "{{product.default_code}}"
    );
}
{
    // Escape unwinds the three new menus (in order) before closing.
    const dlg = makeDialog({ orm: { write: async () => {} } });
    dlg.state.chartMenuOpen = true;
    dlg.state.tableMenuOpen = true;
    dlg.state.qrMenuOpen = true;
    const escape = () => dlg._onKeyDown(keyEvent("Escape"));
    escape();
    checkTrue("Escape closes the chart menu", !dlg.state.chartMenuOpen);
    escape();
    checkTrue("Escape closes the table menu", !dlg.state.tableMenuOpen);
    escape();
    checkTrue(
        "Escape closes the QR menu and clears its error",
        !dlg.state.qrMenuOpen && dlg.state.qrError === ""
    );
    escape();
    await sleep(10);
    checkTrue("Escape then closes the dialog", dlg.closedCount() === 1);
}
{
    // A live table edit session is reassembled before a save flush so
    // the persisted scene is always the grouped table.
    const kdStart = dialogSource.indexOf("_flushSave() {");
    const kdEnd = dialogSource.indexOf("async close()", kdStart);
    const flushBody = dialogSource.slice(kdStart, kdEnd);
    checkTrue(
        "flush reassembles an open table edit session",
        kdStart >= 0 &&
            kdEnd > kdStart &&
            flushBody.indexOf("_exitTableEdit(true)") <
                flushBody.indexOf("_captureScene")
    );
}

// ------------------------------------------------------------------
// Accessibility lint: real buttons, accessible names, focus visibility
// ------------------------------------------------------------------

{
    // The two upload togglers (image, SVG) are real buttons inside the
    // FileUploader toggler slot; the shape-fill and media-upload slots
    // already were.
    const togglers = [...xml.matchAll(/<t t-set-slot="toggler">([\s\S]*?)<\/t>/g)].map(
        (m) => m[1].trim()
    );
    checkTrue("four FileUploader toggler slots", togglers.length === 4);
    checkTrue(
        "upload togglers are real buttons",
        togglers.every((t) => /^<button\b[^>]*\btype="button"/.test(t))
    );
    checkTrue(
        "icon-only upload togglers have aria-labels",
        togglers.every((t) => {
            const hasText = t
                .replace(/<[^>]+>/g, "")
                .replace(/&[a-z]+;/gi, "x")
                .trim();
            return hasText || /\baria-label=/.test(t);
        })
    );
}
{
    // Icon-only buttons (no text content, no runtime t-esc text) need an
    // aria-label; a t-att-aria-label counts too.
    const unnamed = [];
    for (const m of xml.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)) {
        const [full, attrs, inner] = m;
        if (/\baria-label=/.test(attrs)) {
            continue;
        }
        if (/\bt-esc\s*=/.test(attrs) || /\bt-esc\s*=/.test(inner)) {
            continue; // runtime text content
        }
        const text = inner.replace(/<[^>]+>/g, "").replace(/&[a-z]+;/gi, "x").trim();
        if (!text) {
            unnamed.push(full.split("\n")[0].slice(0, 100));
        }
    }
    checkTrue(
        "every icon-only button has an aria-label",
        unnamed.length === 0,
        `\n  ${unnamed.join("\n  ")}`
    );
}
checkTrue(
    "layer action buttons become visible on :focus-within",
    /&:focus-within\s+\.o_social_image_editor_layer_btn/.test(scss)
);

// ------------------------------------------------------------------
// No disallowed global inside any t-* expression
// ------------------------------------------------------------------

// RESERVED_WORDS in odoo/addons/web/static/lib/owl/owl.js (OWL 2.8.2). These
// are the only globals a template expression may name directly.
const OWL_ALLOWED = new Set(
    "true,false,NaN,null,undefined,debugger,console,window,in,instanceof,new,function,return,eval,void,Math,RegExp,Array,Object,Date,__globals__".split(
        ","
    )
);
// JS globals that look harmless in an expression and are not allowed.
const TEMPTING_GLOBALS = [
    "Number",
    "String",
    "Boolean",
    "parseInt",
    "parseFloat",
    "isNaN",
    "isFinite",
    "JSON",
    "Symbol",
    "BigInt",
    "Intl",
    "encodeURIComponent",
    "decodeURIComponent",
    "document",
    "navigator",
    "localStorage",
    "setTimeout",
];

const offenders = [];
const lines = xml.split("\n");
lines.forEach((line, idx) => {
    for (const match of line.matchAll(/\bt-[a-zA-Z0-9_.:-]+="([^"]*)"/g)) {
        const expr = match[1];
        for (const name of TEMPTING_GLOBALS) {
            if (OWL_ALLOWED.has(name)) {
                continue;
            }
            // A bare use, not a property access such as `foo.Number`.
            if (new RegExp(`(^|[^.\\w$])${name}\\b`).test(expr)) {
                offenders.push(`line ${idx + 1}: ${name} in ${match[0].slice(0, 90)}`);
            }
        }
    }
});
checkTrue(
    "no disallowed JS global in a template expression",
    offenders.length === 0,
    `\n  ${offenders.join("\n  ")}`
);

// ------------------------------------------------------------------
// The Fabric canvas element carries no background utility class
// ------------------------------------------------------------------
//
// Fabric copies the lower canvas's className onto the upper (interaction)
// canvas it stacks on top. A `bg-*` class is `!important` in Bootstrap, so
// it paints the upper canvas opaque and hides every object drawn below it.
// The white page comes from Fabric's own backgroundColor instead.

const canvasTag = (xml.match(/<canvas\b[^>]*>/) || [""])[0];
checkTrue("template has a canvas element", canvasTag.length > 0);
checkTrue(
    "canvas element has no bg-* class",
    !/class="[^"]*\bbg-[a-z]/.test(canvasTag),
    canvasTag
);

if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
}
console.log("all checks passed");
