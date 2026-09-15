/** @odoo-module **/

/**
 * Pure helpers for the social image editor dialog.
 *
 * Kept free of Odoo and Fabric imports so the logic can be unit-tested
 * under plain Node (see static/tests/social_image_editor_utils.test.mjs)
 * and reused by later editor tasks.
 */

/**
 * Custom object props that must survive the Fabric toJSON/loadFromJSON
 * round trip. `_`-prefixed, mirroring the namespacing proven in
 * render-engine-os (design decision D2).
 */
export const EXTRA_PROPS = [
    "_layerId",
    "_layerName",
    "_mediaName",
    "_dataBinding",
    "_hideIfEmpty",
    "_required",
    "_shapeKind",
    "_shapeParams",
    "_textTransform",
    "_overflow",
    "_fillImage",
    "_iconName",
];

export const HISTORY_LIMIT = 80;

const LAYER_TYPE_LABELS = {
    textbox: "Text",
    "i-text": "Text",
    text: "Text",
    rect: "Rectangle",
    circle: "Circle",
    triangle: "Triangle",
    line: "Line",
    image: "Image",
    group: "Group",
    path: "Shape",
    polygon: "Polygon",
    activeSelection: "Selection",
};

let _uidCounter = 0;

/**
 * Unique layer id, stable for the lifetime of an object on the canvas.
 */
export function newLayerId() {
    _uidCounter += 1;
    return `l_${Date.now().toString(36)}_${_uidCounter}_${Math.random()
        .toString(36)
        .slice(2, 7)}`;
}

/**
 * Human-readable label for a layer row: explicit custom name wins, then
 * text content preview, then media name, then the shape library label for
 * objects tagged with _shapeKind, then a per-type label.
 *
 * @param {Object} obj fabric object (or plain stand-in in tests)
 * @param {Object} [shapeMeta] optional SHAPE_META map (kind -> {label}),
 *   passed in by the dialog so this module stays free of data imports.
 */
export function buildLayerLabel(obj, shapeMeta) {
    if (obj._layerName) {
        return obj._layerName;
    }
    if (typeof obj.text === "string" && obj.text.trim()) {
        return obj.text.replace(/\s+/g, " ").trim().slice(0, 24);
    }
    if (obj._mediaName) {
        return String(obj._mediaName).slice(0, 24);
    }
    if (obj._shapeKind && shapeMeta && shapeMeta[obj._shapeKind]) {
        return shapeMeta[obj._shapeKind].label;
    }
    const type = (obj.type || "").toLowerCase();
    return LAYER_TYPE_LABELS[type] || obj.type || "Object";
}

/**
 * Layer descriptors for the panel, topmost first (Fabric's z-order
 * reversed, exactly like render-engine-os's syncLayers).
 */
export function buildLayerDescriptors(objects, shapeMeta) {
    return [...objects].reverse().map((obj) => ({
        id: obj._layerId || null,
        type: obj.type,
        label: buildLayerLabel(obj, shapeMeta),
        visible: obj.visible !== false,
        locked: obj.selectable === false,
    }));
}

/**
 * Move an item inside an array (pure); returns a new array.
 */
export function moveItem(list, fromIndex, toIndex) {
    if (
        fromIndex === toIndex ||
        fromIndex < 0 ||
        toIndex < 0 ||
        fromIndex >= list.length ||
        toIndex >= list.length
    ) {
        return [...list];
    }
    const result = [...list];
    const [item] = result.splice(fromIndex, 1);
    result.splice(toIndex, 0, item);
    return result;
}

/**
 * Scale factor to display a width x height canvas inside an
 * availWidth x availHeight area, never upscaling.
 */
export function computeDisplayScale(width, height, availWidth, availHeight) {
    if (!width || !height || !availWidth || !availHeight) {
        return 1;
    }
    return Math.min(1, availWidth / width, availHeight / height);
}

/**
 * Custom-prop safety around Fabric's loadFromJSON (the render-engine-os
 * quirk): Fabric enlivens any nested plain object that carries a string
 * `type` key into a Fabric class instance, which silently corrupts custom
 * props shaped like {type: ...} on save. Underscore-prefixed scalars
 * (strings, numbers, booleans, arrays of scalars) pass through untouched,
 * so they never need stashing. Only object-valued custom props are at
 * risk; this helper holds those aside before load and re-attaches them
 * after, sidestepping the whole family of bugs no matter what Fabric
 * chooses to do.
 *
 * @param {Object} scene parsed scene JSON (canvas.toObject() shape)
 * @returns {{sanitized: Object, stashed: Array<Array<{key, value}>>}}
 */
export function stashSceneProps(scene) {
    if (!scene || !Array.isArray(scene.objects)) {
        return { sanitized: scene, stashed: [] };
    }
    const stashed = [];
    const objects = scene.objects.map((obj) => {
        if (!obj || typeof obj !== "object") {
            stashed.push([]);
            return obj;
        }
        const held = [];
        const copy = { ...obj };
        for (const key of Object.keys(copy)) {
            const value = copy[key];
            const isCustomProp = key.startsWith("_") || EXTRA_PROPS.includes(key);
            const isEnlivenRisk =
                value !== null && typeof value === "object" &&
                typeof value.type === "string";
            if (isCustomProp && isEnlivenRisk) {
                held.push({ key, value });
                delete copy[key];
            }
        }
        stashed.push(held);
        return copy;
    });
    return { sanitized: { ...scene, objects }, stashed };
}

/**
 * Re-attach props held aside by stashSceneProps. `objects` must be the
 * canvas objects in the same order as the scene's objects list.
 */
export function restoreSceneProps(objects, stashed) {
    (objects || []).forEach((obj, index) => {
        const held = stashed[index];
        if (!held) {
            return;
        }
        for (const { key, value } of held) {
            obj[key] = value;
        }
    });
}

// ------------------------------------------------------------------
// Data binding helpers (pure; used by the dialog's Data panel and
// live preview, and unit-tested under plain Node)
// ------------------------------------------------------------------

/**
 * {{field}} and {{dotted.field.path}} with optional chained pipes,
 * e.g. {{name|upper}} or {{categ_id.name|title|trim}}. Mirrors the
 * TOKEN_RE in render_service/render_core.mjs and
 * social_image_creator/models/social_image_binding.py.
 */
export const BINDING_TOKEN_RE =
    /\{\{\s*([a-zA-Z0-9_.-]+)\s*((?:\|[^}|]+)*)\}\}/g;

/**
 * One pipe transform on a resolved string value. Unknown pipes leave the
 * value untouched. Mirrors render_service/render_core.mjs exactly so the
 * preview matches the rendered output.
 */
export function applyPipeTransform(value, pipe) {
    if (!pipe) {
        return value;
    }
    switch (pipe) {
        case "lower":
        case "lowercase":
            return value.toLowerCase();
        case "upper":
        case "uppercase":
            return value.toUpperCase();
        case "title":
            // Note: JS \b is ASCII-based, so non-ASCII letters (ä, ö, å)
            // count as word boundaries. Same quirk as the server side.
            return value
                .replace(/\b\p{L}/gu, (c) => c.toUpperCase())
                .replace(/\B\p{L}+/gu, (m) => m.toLowerCase());
        case "trim":
            return value.trim();
        case "capitalize":
            return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
        default:
            return value;
    }
}

/**
 * Resolve every {{path|pipe...}} token in `text` against `bindings`.
 * Unknown tokens are left untouched so the user sees what is unbound.
 */
export function resolveTokens(text, bindings) {
    return String(text ?? "").replace(
        BINDING_TOKEN_RE,
        (match, name, pipes) => {
            if (!Object.prototype.hasOwnProperty.call(bindings, name)) {
                return match;
            }
            let v = String(bindings[name] ?? "");
            if (pipes) {
                for (const p of pipes.split("|").filter(Boolean)) {
                    v = applyPipeTransform(v, p.trim());
                }
            }
            return v;
        }
    );
}

/**
 * Empty binding value: unset, false, or a whitespace-only string. Mirrors
 * is_empty_value in social_image_binding.py.
 */
export function isEmptyBindingValue(v) {
    return (
        v === undefined ||
        v === null ||
        v === false ||
        (typeof v === "string" && v.trim() === "")
    );
}

/**
 * Cover-fit math for a data-bound image. Must stay identical to
 * computeCoverFit in render_service/render_core.mjs; editor preview and
 * server render depend on the same numbers.
 *
 * Fabric model: width/height are in source pixels (post-crop), cropX/cropY
 * are the source-pixel offset of the visible window, scaleX/scaleY scale
 * source pixels to display pixels. Cover semantics: scale up so the
 * smaller dimension fills the frame, crop the overflow centered.
 */
export function computeCoverFit(
    naturalW,
    naturalH,
    frameW,
    frameH,
    oldHostScaleX = 1,
    oldHostScaleY = 1
) {
    const scale = Math.max(frameW / naturalW, frameH / naturalH);
    const visibleW = frameW / scale;
    const visibleH = frameH / scale;
    return {
        scale,
        cropX: Math.max(0, (naturalW - visibleW) / 2),
        cropY: Math.max(0, (naturalH - visibleH) / 2),
        width: visibleW,
        height: visibleH,
        clipScaleX: (oldHostScaleX || 1) / scale,
        clipScaleY: (oldHostScaleY || 1) / scale,
    };
}

/**
 * Re-fit a fabric.Image to a target frame using object-fit: cover
 * semantics: scale up so the smaller dimension fills the frame, crop the
 * overflow centered. Used when an image data-binding swaps a placeholder
 * for a record image of a different aspect ratio.
 *
 * Mutates `obj` in place (the caller captured the frame BEFORE the src
 * swap; setSrc resets width/height to the new image's natural dims).
 * Ported from render-engine-os TemplateEditor.jsx applyImageCoverFit.
 */
export function applyImageCoverFit(obj, frameW, frameH) {
    if (!obj || !frameW || !frameH) {
        return;
    }
    const naturalW = obj._originalElement?.naturalWidth ?? obj.width;
    const naturalH = obj._originalElement?.naturalHeight ?? obj.height;
    if (!naturalW || !naturalH) {
        return;
    }
    // Capture old host scale BEFORE mutating; needed to compensate any
    // clipPath that came from an image-fill shape (the clip lives in the
    // host's local coord space).
    const oldHostScaleX = obj.scaleX || 1;
    const oldHostScaleY = obj.scaleY || 1;
    const fit = computeCoverFit(
        naturalW,
        naturalH,
        frameW,
        frameH,
        oldHostScaleX,
        oldHostScaleY
    );
    obj.set({
        cropX: fit.cropX,
        cropY: fit.cropY,
        width: fit.width,
        height: fit.height,
        scaleX: fit.scale,
        scaleY: fit.scale,
    });
    // ClipPath compensation: the on-canvas mask footprint is
    // clip.scaleX x clip.width x host.scaleX; the host scale just changed,
    // so multiply the clip scale by the inverse ratio to keep the mask the
    // same on-canvas size.
    if (obj.clipPath) {
        obj.clipPath.scaleX = (obj.clipPath.scaleX || 1) * fit.clipScaleX;
        obj.clipPath.scaleY = (obj.clipPath.scaleY || 1) * fit.clipScaleY;
    }
    obj.setCoords?.();
}

// ------------------------------------------------------------------
// Typography helpers (pure; used by the dialog and by Node tests)
// ------------------------------------------------------------------

/**
 * Apply a case transform to a text. "upper"/"lower" transform, anything
 * else (including null/"none") returns the text unchanged. Non-string
 * input passes through untouched.
 */
export function applyCaseTransform(text, transform) {
    if (typeof text !== "string") {
        return text;
    }
    if (transform === "upper") {
        return text.toUpperCase();
    }
    if (transform === "lower") {
        return text.toLowerCase();
    }
    return text;
}

/**
 * Longest line of a (possibly multi-line) text, by character length.
 * Width measuring is delegated to the caller, so this stays pure.
 */
export function widestLine(text) {
    if (typeof text !== "string" || !text) {
        return "";
    }
    return text.split("\n").reduce((a, b) => (b.length > a.length ? b : a), "");
}

/**
 * Autofit font size: the largest font size at or below startSize whose
 * measured text width fits inside boxWidth. Never grows the text, never
 * shrinks below minSize. Binary search keeps it cheap and deterministic.
 *
 * @param {Object} args
 * @param {string} args.text text content (may contain newlines)
 * @param {number} args.boxWidth available width in canvas units
 * @param {number} args.startSize font size to start shrinking from
 * @param {number} [args.minSize] lower bound, default 6
 * @param {Function} args.measure (fontSize, widestLineText) -> width in
 *   the same units as boxWidth; injected so this stays pure and testable
 * @returns {number} the fitted font size (integer)
 */
export function computeAutofitFontSize({
    text,
    boxWidth,
    startSize,
    minSize = 6,
    measure,
}) {
    if (typeof measure !== "function" || !boxWidth || boxWidth <= 0) {
        return startSize;
    }
    const line = widestLine(text);
    if (!line) {
        return startSize;
    }
    const start = Number(startSize) || 0;
    const floor = Math.max(1, Number(minSize) || 6);
    if (start <= floor) {
        return start;
    }
    if (measure(start, line) <= boxWidth) {
        return start;
    }
    if (measure(floor, line) > boxWidth) {
        return floor;
    }
    let lo = floor;
    let hi = start;
    for (let i = 0; i < 24; i++) {
        const mid = (lo + hi) / 2;
        if (measure(mid, line) <= boxWidth) {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    // The search converges from below, so an exact integer fit can floor
    // one short; probe upward while the next integer still fits.
    let best = Math.floor(lo);
    while (best < start && measure(best + 1, line) <= boxWidth) {
        best += 1;
    }
    return Math.max(floor, best);
}

// ------------------------------------------------------------------
// Color helpers
// ------------------------------------------------------------------

/**
 * Browsers' <input type="color"> requires #rrggbb. Fabric returns colors
 * as rgb()/rgba() strings on default-loaded shapes, so coerce. Non-string
 * or unparseable input falls back to #000000; transparent yields #ffffff
 * (closest usable swatch for a color input).
 */
export function toHexColor(c) {
    if (!c || typeof c !== "string") {
        return "#000000";
    }
    if (c.startsWith("#")) {
        if (c.length === 4) {
            return "#" + [...c.slice(1)].map((x) => x + x).join("");
        }
        return c.slice(0, 7);
    }
    const m = c.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (m) {
        const h = (n) =>
            Math.max(0, Math.min(255, Number(n)))
                .toString(16)
                .padStart(2, "0");
        return `#${h(m[1])}${h(m[2])}${h(m[3])}`;
    }
    return "#000000";
}

// ------------------------------------------------------------------
// Effects helpers: gradients, shadows, stroke patterns (pure)
// ------------------------------------------------------------------

/**
 * Stroke dash presets keyed by style name. "solid" is null (no dash
 * array), matching how Fabric renders an unbroken stroke.
 */
export const DASH_PRESETS = {
    solid: null,
    dashed: [10, 6],
    dotted: [2, 5],
};

/**
 * Detect which DASH_PRESETS entry a strokeDashArray corresponds to.
 * Dotted = very short first dash with a longer gap; anything else
 * non-empty counts as dashed.
 */
export function detectStrokePattern(arr) {
    if (!arr || arr.length === 0) {
        return "solid";
    }
    if (arr.length >= 2 && arr[0] <= 3 && arr[1] >= arr[0] * 1.5) {
        return "dotted";
    }
    return "dashed";
}

/**
 * Linear gradient endpoints for an angle in degrees (0 = pointing
 * right, 90 = pointing down), spanning the object diagonal so no
 * corner is left uncovered at any angle. Ported from render-engine-os.
 */
export function gradientAngleToCoords(angle, w, h) {
    const rad = (angle * Math.PI) / 180;
    const cx = w / 2;
    const cy = h / 2;
    const len = Math.max(w, h);
    return {
        x1: cx - (Math.cos(rad) * len) / 2,
        y1: cy - (Math.sin(rad) * len) / 2,
        x2: cx + (Math.cos(rad) * len) / 2,
        y2: cy + (Math.sin(rad) * len) / 2,
    };
}

/**
 * Radial gradient coords centered on the object, outer radius half
 * the larger dimension.
 */
export function gradientRadialCoords(w, h) {
    return {
        x1: w / 2,
        y1: h / 2,
        r1: 0,
        x2: w / 2,
        y2: h / 2,
        r2: Math.max(w, h) / 2,
    };
}

/**
 * Recover the panel config from a fabric.Gradient instance OR its
 * serialized plain-object form (Fabric 6 serializes gradients as
 * {type: "gradient", gradientType: "linear"|"radial", ...}; live
 * instances expose type directly). Returns null for non-gradient
 * fills so the panel falls back to solid.
 */
export function gradientToConfig(fill) {
    if (!fill || typeof fill !== "object") {
        return null;
    }
    const type = fill.gradientType || fill.type;
    if (type !== "linear" && type !== "radial") {
        return null;
    }
    const stops = fill.colorStops || [];
    let angle = 0;
    if (type === "linear" && fill.coords) {
        const dx = fill.coords.x2 - fill.coords.x1;
        const dy = fill.coords.y2 - fill.coords.y1;
        angle = Math.round((Math.atan2(dy, dx) * 180) / Math.PI);
        if (angle < 0) {
            angle += 360;
        }
    }
    return {
        type,
        angle,
        startColor: (stops[0] && stops[0].color) || "#000000",
        endColor: (stops.length && stops[stops.length - 1].color) || "#ffffff",
        startPos: stops[0] ? stops[0].offset ?? 0 : 0,
        endPos: stops.length ? stops[stops.length - 1].offset ?? 1 : 1,
    };
}

/**
 * Split a shadow color (hex or rgb()/rgba()) into a #rrggbb hex and a
 * 0-100 alpha for the panel controls. Defaults mirror the reference
 * editor's default shadow (black at 30 percent).
 */
export function parseShadowColor(c) {
    if (!c || typeof c !== "string") {
        return { hex: "#000000", alpha: 30 };
    }
    if (c.startsWith("#")) {
        const hex =
            c.length === 4
                ? "#" + [...c.slice(1)].map((x) => x + x).join("")
                : c.slice(0, 7);
        return { hex, alpha: 100 };
    }
    const m = c.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)/);
    if (!m) {
        return { hex: "#000000", alpha: 30 };
    }
    const hex =
        "#" +
        [1, 2, 3].map((i) => Number(m[i]).toString(16).padStart(2, "0")).join("");
    const alpha = m[4] !== undefined ? Math.round(Number(m[4]) * 100) : 100;
    return { hex, alpha };
}

/**
 * Inverse of parseShadowColor: build the rgba() string Fabric.Shadow
 * stores, from a hex color and a 0-100 alpha.
 */
export function buildShadowColor(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${(alpha / 100).toFixed(2)})`;
}

// ------------------------------------------------------------------
// Alignment and distribution (pure)
// ------------------------------------------------------------------

/**
 * Alignment deltas for a multi-selection. rects are plain
 * {left, top, width, height} bounding boxes (canvas coords); kind is
 * left|cx|right|top|cy|bottom relative to the selection bounding box.
 * Returns one {dx, dy} per input rect, in the same order.
 */
export function computeAlignmentDeltas(rects, kind) {
    if (!rects || !rects.length) {
        return [];
    }
    const minLeft = Math.min(...rects.map((r) => r.left));
    const maxRight = Math.max(...rects.map((r) => r.left + r.width));
    const minTop = Math.min(...rects.map((r) => r.top));
    const maxBottom = Math.max(...rects.map((r) => r.top + r.height));
    const groupCx = (minLeft + maxRight) / 2;
    const groupCy = (minTop + maxBottom) / 2;
    return rects.map((r) => {
        let dx = 0;
        let dy = 0;
        if (kind === "left") {
            dx = minLeft - r.left;
        } else if (kind === "cx") {
            dx = groupCx - (r.left + r.width / 2);
        } else if (kind === "right") {
            dx = maxRight - (r.left + r.width);
        } else if (kind === "top") {
            dy = minTop - r.top;
        } else if (kind === "cy") {
            dy = groupCy - (r.top + r.height / 2);
        } else if (kind === "bottom") {
            dy = maxBottom - (r.top + r.height);
        }
        return { dx, dy };
    });
}

/**
 * Distribute positions along one axis. items are {start, size} in
 * canvas coords in any order; returns the new start per item in the
 * SAME input order, equalizing gaps while keeping the first and last
 * item fixed. Fewer than 3 items is a no-op (returns current starts).
 */
export function computeDistributePositions(items) {
    if (!items || items.length < 3) {
        return (items || []).map((it) => it.start);
    }
    const order = items
        .map((it, index) => ({ ...it, index }))
        .sort((a, b) => a.start - b.start);
    const first = order[0];
    const last = order[order.length - 1];
    const span = last.start + last.size - first.start;
    const totalSize = order.reduce((s, b) => s + b.size, 0);
    const gap = (span - totalSize) / (order.length - 1);
    const result = new Array(items.length);
    let cursor = first.start;
    for (const it of order) {
        result[it.index] = cursor;
        cursor += it.size + gap;
    }
    return result;
}

// ------------------------------------------------------------------
// Snapping and smart spacing (pure)
// ------------------------------------------------------------------

/**
 * Bounding box in the shape the snapping math uses: edges + centers.
 */
export function snapBoxFromRect(r) {
    return {
        left: r.left,
        right: r.left + r.width,
        top: r.top,
        bottom: r.top + r.height,
        centerX: r.left + r.width / 2,
        centerY: r.top + r.height / 2,
    };
}

/**
 * Pick the candidate with the SMALLEST absolute delta (not the first
 * one found). When three text layers stack vertically this is the
 * difference between smooth alignment and the cursor jumping between
 * half a dozen near-equal targets. Ported from render-engine-os.
 *
 * @returns {{delta: number, at: number|null, found: boolean}}
 */
export function closestSnap(candidates, edges, threshold) {
    let best = { delta: 0, at: null, found: false };
    for (const c of candidates) {
        for (const val of edges) {
            const delta = c.at - val;
            const abs = Math.abs(delta);
            if (abs < threshold && (!best.found || abs < Math.abs(best.delta))) {
                best = { delta, at: c.at, found: true };
            }
        }
    }
    return best;
}

/**
 * Snap a moving box to vertical/horizontal guide candidates (canvas
 * edges/centers + other objects' edges/centers). Returns the delta
 * to apply and the guide positions to draw (null when nothing snapped).
 */
export function snapBoxToGuides(box, vCandidates, hCandidates, threshold) {
    const v = closestSnap(
        vCandidates,
        [box.left, box.centerX, box.right],
        threshold
    );
    const h = closestSnap(
        hCandidates,
        [box.top, box.centerY, box.bottom],
        threshold
    );
    return {
        dx: v.found ? v.delta : 0,
        dy: h.found ? h.delta : 0,
        vAt: v.found ? v.at : null,
        hAt: h.found ? h.at : null,
    };
}

/**
 * Smart spacing: equal-gap snapping between the immediate horizontal
 * and vertical neighbors, plus pink distance labels for the gaps.
 * Only the nearest neighbor on each side is considered (same
 * simplification as render-engine-os: the sandwich pair).
 *
 * @param {Object} box moving object's snap box (already guide-snapped)
 * @param {Array<Object>} others snap boxes of the other visible objects
 * @param {number} threshold canvas-unit snap threshold
 * @returns {{dx: number, dy: number, distances: Array}}
 *   distances entries: {kind: 'h'|'v', from, to, x|y, label}
 */
export function computeSmartSpacing(box, others, threshold) {
    const distances = [];
    let dx = 0;
    let dy = 0;
    const vOverlap = (a, b) =>
        Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
    const hOverlap = (a, b) =>
        Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));

    // Horizontal sandwich: nearest object fully to the left and to the
    // right that shares vertical overlap with the moving object.
    const left = others
        .filter((b) => vOverlap(b, box) > 0 && b.right <= box.left)
        .sort((a, b) => b.right - a.right)[0];
    const right = others
        .filter((b) => vOverlap(b, box) > 0 && b.left >= box.right)
        .sort((a, b) => a.left - b.left)[0];
    if (left && right) {
        const gapL = box.left - left.right;
        const gapR = right.left - box.right;
        if (Math.abs(gapL - gapR) < threshold) {
            const targetGap = (gapL + gapR) / 2;
            dx = left.right + targetGap - box.left;
            const b3 = { ...box, left: box.left + dx, right: box.right + dx };
            distances.push({
                kind: "h",
                from: left.right,
                to: b3.left,
                y: (b3.top + b3.bottom) / 2,
                label: Math.round(b3.left - left.right) + "px",
            });
            distances.push({
                kind: "h",
                from: b3.right,
                to: right.left,
                y: (b3.top + b3.bottom) / 2,
                label: Math.round(right.left - b3.right) + "px",
            });
        } else {
            distances.push({
                kind: "h",
                from: left.right,
                to: box.left,
                y: (box.top + box.bottom) / 2,
                label: Math.round(gapL) + "px",
            });
            distances.push({
                kind: "h",
                from: box.right,
                to: right.left,
                y: (box.top + box.bottom) / 2,
                label: Math.round(gapR) + "px",
            });
        }
    } else if (left) {
        distances.push({
            kind: "h",
            from: left.right,
            to: box.left,
            y: (box.top + box.bottom) / 2,
            label: Math.round(box.left - left.right) + "px",
        });
    } else if (right) {
        distances.push({
            kind: "h",
            from: box.right,
            to: right.left,
            y: (box.top + box.bottom) / 2,
            label: Math.round(right.left - box.right) + "px",
        });
    }

    // Vertical sandwich: nearest object fully above and below sharing
    // horizontal overlap.
    const above = others
        .filter((b) => hOverlap(b, box) > 0 && b.bottom <= box.top)
        .sort((a, b) => b.bottom - a.bottom)[0];
    const below = others
        .filter((b) => hOverlap(b, box) > 0 && b.top >= box.bottom)
        .sort((a, b) => a.top - b.top)[0];
    if (above && below) {
        const gapA = box.top - above.bottom;
        const gapB = below.top - box.bottom;
        if (Math.abs(gapA - gapB) < threshold) {
            const targetGap = (gapA + gapB) / 2;
            dy = above.bottom + targetGap - box.top;
            const b3 = { ...box, top: box.top + dy, bottom: box.bottom + dy };
            distances.push({
                kind: "v",
                from: above.bottom,
                to: b3.top,
                x: (b3.left + b3.right) / 2,
                label: Math.round(b3.top - above.bottom) + "px",
            });
            distances.push({
                kind: "v",
                from: b3.bottom,
                to: below.top,
                x: (b3.left + b3.right) / 2,
                label: Math.round(below.top - b3.bottom) + "px",
            });
        } else {
            distances.push({
                kind: "v",
                from: above.bottom,
                to: box.top,
                x: (box.left + box.right) / 2,
                label: Math.round(gapA) + "px",
            });
            distances.push({
                kind: "v",
                from: box.bottom,
                to: below.top,
                x: (box.left + box.right) / 2,
                label: Math.round(gapB) + "px",
            });
        }
    } else if (above) {
        distances.push({
            kind: "v",
            from: above.bottom,
            to: box.top,
            x: (box.left + box.right) / 2,
            label: Math.round(box.top - above.bottom) + "px",
        });
    } else if (below) {
        distances.push({
            kind: "v",
            from: box.bottom,
            to: below.top,
            x: (box.left + box.right) / 2,
            label: Math.round(below.top - box.bottom) + "px",
        });
    }

    return { dx, dy, distances };
}
