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
const preamble = [
    "const Component = class {};",
    "const FileUploader = class {};",
    "const _t = (term) => term;",
    `const EXTRA_PROPS = ${JSON.stringify(utils.EXTRA_PROPS)};`,
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
        penMode: false,
    };
    const removed = [];
    let current = activeObject;
    dlg._removed = removed;
    dlg._canvas = {
        getActiveObject: () => current,
        getObjects: () => objects,
        remove: (obj) => removed.push(obj),
        discardActiveObject: () => {
            current = null;
        },
        requestRenderAll: () => {},
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
    checkTrue("fourth Escape closes the shapes menu", !dlg.state.shapesOpen);
    escape();
    await sleep(10);
    checkTrue("fifth Escape closes the dialog", dlg.closedCount() === 1);
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
            kdBody.indexOf("this.close()") > pickerIdx[3]
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
