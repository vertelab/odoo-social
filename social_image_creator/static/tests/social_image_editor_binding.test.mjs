// Node smoke test for the editor data binding helpers (resolveTokens,
// pipe transforms, cover-fit math).
// Run: node social_image_creator/static/tests/social_image_editor_binding.test.mjs

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// The render-side mirror; the autofit parity fixtures below pin both
// binary-search implementations to identical outputs (design D2 in
// openspec/changes/creator-render-parity).
import * as renderCore from "../../../render_service/render_core.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
    join(here, "../src/js/dialog/social_image_editor_utils.js"),
    "utf8"
);
const tmp = join("/tmp", "social_image_editor_binding.smoke.mjs");
writeFileSync(tmp, source);
const utils = await import(tmp);

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

// resolveTokens: plain, dotted, pipes, chained, unknown kept
check(
    "resolve plain",
    utils.resolveTokens("Hej {{name}}!", { name: "Världen" }),
    "Hej Världen!"
);
check(
    "resolve dotted",
    utils.resolveTokens("{{categ_id.name}}", { "categ_id.name": "Chairs" }),
    "Chairs"
);
check(
    "resolve pipe upper",
    utils.resolveTokens("{{name|upper}}", { name: "Stol" }),
    "STOL"
);
check(
    "resolve chained pipes",
    utils.resolveTokens("{{name|trim|lower}}", { name: "  STOL  " }),
    "stol"
);
check(
    "resolve title",
    utils.resolveTokens("{{name|title}}", { name: "hej varlden" }),
    "Hej Varlden"
);
check(
    "resolve capitalize",
    utils.resolveTokens("{{name|capitalize}}", { name: "sTOL" }),
    "Stol"
);
check(
    "unknown token kept",
    utils.resolveTokens("{{missing}}", { name: "x" }),
    "{{missing}}"
);
check(
    "unknown pipe leaves value",
    utils.resolveTokens("{{name|bogus}}", { name: "Stol" }),
    "Stol"
);
check("resolve non-string", utils.resolveTokens(null, {}), "");

// applyPipeTransform direct
check("pipe uppercase alias", utils.applyPipeTransform("stol", "uppercase"), "STOL");
check("pipe lowercase alias", utils.applyPipeTransform("STOL", "lowercase"), "stol");

// isEmptyBindingValue
check("empty undefined", utils.isEmptyBindingValue(undefined), true);
check("empty false", utils.isEmptyBindingValue(false), true);
check("empty whitespace", utils.isEmptyBindingValue("  "), true);
check("empty zero string ok", utils.isEmptyBindingValue("0"), false);
check("empty value", utils.isEmptyBindingValue("x"), false);

// computeCoverFit: identical math to render_service/render_core.mjs
{
  const f = utils.computeCoverFit(400, 200, 100, 100);
  check("cover landscape scale", f.scale, 0.5);
  check("cover landscape cropX", f.cropX, 100);
  check("cover landscape cropY", f.cropY, 0);

  const g = utils.computeCoverFit(200, 400, 200, 100);
  check("cover portrait scale", g.scale, 1);
  check("cover portrait cropY", g.cropY, 150);

  const c = utils.computeCoverFit(400, 200, 100, 100, 2, 2);
  check("cover clip compensation", [c.clipScaleX, c.clipScaleY], [4, 4]);
}

// applyImageCoverFit on a fake fabric image object
{
  const fake = {
    width: 400,
    height: 200,
    scaleX: 1,
    scaleY: 1,
    clipPath: { scaleX: 1, scaleY: 1 },
    set(patch) {
      Object.assign(this, patch);
    },
    setCoords() {},
  };
  utils.applyImageCoverFit(fake, 100, 100);
  check("applyCoverFit width", fake.width, 200);
  check("applyCoverFit height", fake.height, 200);
  check("applyCoverFit cropX", fake.cropX, 100);
  check("applyCoverFit cropY", fake.cropY, 0);
  check("applyCoverFit scale", [fake.scaleX, fake.scaleY], [0.5, 0.5]);
  check("applyCoverFit clipPath compensated", [fake.clipPath.scaleX, fake.clipPath.scaleY], [2, 2]);

  // No frame: untouched.
  const noop = { width: 10, height: 10, set() { Object.assign(this, arguments[0]); } };
  utils.applyImageCoverFit(noop, 0, 100);
  check("applyCoverFit noop without frame", noop.width, 10);
}

// Autofit parity (task 2.2 / design D2): the editor's
// computeAutofitFontSize and the render-side mirror must converge on
// the same size for the same text, box, start size and floor. minSize
// is passed explicitly on both sides; the render-time floor (4) and the
// edit-time default (6) are separate concerns.
{
  const measure = (size, line) => line.length * size * 0.55;
  const cases = [
    { text: "abcdefghijklmnopqrst", boxWidth: 100, startSize: 40, minSize: 4 },
    { text: "ab", boxWidth: 100, startSize: 40, minSize: 4 },
    { text: "x".repeat(500), boxWidth: 80, startSize: 32, minSize: 4 },
    { text: "tre\nlånga\nrader", boxWidth: 60, startSize: 24, minSize: 6 },
    { text: "kort", boxWidth: 0, startSize: 20, minSize: 4 },
    { text: "", boxWidth: 100, startSize: 40, minSize: 4 },
    { text: "edge", boxWidth: 10, startSize: 4, minSize: 4 },
  ];
  for (const c of cases) {
    check(
      `autofit parity: ${JSON.stringify(c)}`,
      utils.computeAutofitFontSize({ ...c, measure }),
      renderCore.computeAutofitFontSize({ ...c, measure })
    );
  }
  // The render-side default floor is 4 (MIN_AUTOFIT_FONT_SIZE).
  check(
    "render autofit default floor 4",
    renderCore.computeAutofitFontSize({
      text: "x".repeat(500),
      boxWidth: 80,
      startSize: 32,
      measure,
    }),
    4
  );
  check(
    "render MIN_AUTOFIT_FONT_SIZE mirrored",
    utils.MIN_AUTOFIT_FONT_SIZE,
    renderCore.MIN_AUTOFIT_FONT_SIZE
  );
}

// resolveTextForPreview is the drop-in the dialog preview path uses
// instead of a bare resolveTokens call: markdown, transform and autofit
// included. Same fixtures through render and preview stay identical.
{
  const measure = (line, desc) => line.length * desc.fontSize * 0.6;
  const obj = {
    type: "textbox",
    text: "{{name}}",
    _textTransform: "upper",
    _overflow: "autofit",
    width: 120,
    fontSize: 40,
    fontFamily: "Arial",
  };
  const renderOut = renderCore.applyBindingsToScene(
    { version: "6.9.1", objects: [JSON.parse(JSON.stringify(obj))] },
    { name: "**acme ab**" },
    { measure }
  ).objects[0];
  const previewObj = utils.resolveTextForPreview(
    JSON.parse(JSON.stringify(obj)),
    { name: "**acme ab**" },
    { measure }
  );
  check(
    "preview pipeline matches render",
    { text: previewObj.text, styles: previewObj.styles, fontSize: previewObj.fontSize },
    { text: renderOut.text, styles: renderOut.styles, fontSize: renderOut.fontSize }
  );
  check("preview uppercases", previewObj.text, "ACME AB");
  check("preview fits", previewObj.fontSize, 28);
}

if (failures) {
  console.error(`\n${failures} check(s) FAILED`);
  process.exit(1);
}
console.log("\nALL editor binding CHECKS PASSED");
