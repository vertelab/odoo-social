// Node lint test for the editor dialog's OWL template.
// Run: node social_image_creator/static/tests/social_image_editor_template.test.mjs
//
// OWL compiles every identifier in a template expression to a lookup on the
// component (`ctx.<name>`) unless it is one of OWL's reserved words. A bare
// JS global such as Number() therefore becomes ctx.Number, which does not
// exist, and the render dies with "ctx.Number is not a function". Nothing in
// the asset build catches this, so this test does.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const xml = readFileSync(
    join(here, "../src/xml/social_image_editor_dialog.xml"),
    "utf8"
);

let failures = 0;
function checkTrue(name, cond, detail) {
    if (!cond) {
        failures += 1;
        console.error(`FAIL ${name}${detail ? `: ${detail}` : ""}`);
    } else {
        console.log(`ok ${name}`);
    }
}

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

// ------------------------------------------------------------------
// No disallowed global inside any t-* expression
// ------------------------------------------------------------------

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
