// Node smoke test for the editor data binding helpers (resolveTokens,
// pipe transforms, cover-fit math).
// Run: node social_image_creator/static/tests/social_image_editor_binding.test.mjs

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

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

if (failures) {
  console.error(`\n${failures} check(s) FAILED`);
  process.exit(1);
}
console.log("\nALL editor binding CHECKS PASSED");
