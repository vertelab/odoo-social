/** @odoo-module **/

/**
 * Shape library for the social image editor, ported from render-engine-os
 * (ui/src/pages/TemplateEditor.jsx). Pure data and path math: no Odoo and
 * no Fabric imports, so it can be unit-tested under plain Node.
 *
 * All path-based shapes are drawn into a 100x100 viewBox; the editor scales
 * fabric.Path on add via scaleX/scaleY = targetSize / 100.
 */

/**
 * Burst/star burst path helper: alternating outer/inner radius points.
 */
export function buildBurstPath(points, ro = 45, ri = 30) {
    let d = "";
    for (let i = 0; i < points * 2; i++) {
        const r = i % 2 === 0 ? ro : ri;
        const ang = -Math.PI / 2 + (i * Math.PI) / points;
        const x = (50 + r * Math.cos(ang)).toFixed(1);
        const y = (50 + r * Math.sin(ang)).toFixed(1);
        d += (i === 0 ? "M " : "L ") + x + " " + y + " ";
    }
    return d + "Z";
}

const _f = (n) => Number(n).toFixed(2);

/**
 * Parametric polygon: regular n-gon with optional rounded corners
 * (cornerRadius is a fraction of the half side length).
 */
export function pathParametricPolygon({ sides, cornerRadius }) {
    const cx = 50;
    const cy = 50;
    const R = 45;
    const n = Math.max(3, Math.min(12, Math.round(sides)));
    const pts = [];
    for (let i = 0; i < n; i++) {
        const ang = -Math.PI / 2 + (i * 2 * Math.PI) / n;
        pts.push([cx + R * Math.cos(ang), cy + R * Math.sin(ang)]);
    }
    if (cornerRadius <= 0.001) {
        return "M " + pts.map((p) => _f(p[0]) + " " + _f(p[1])).join(" L ") + " Z";
    }
    const sideLen = 2 * R * Math.sin(Math.PI / n);
    const r = Math.min(sideLen / 2 - 0.5, (cornerRadius * sideLen) / 2);
    let d = "";
    for (let i = 0; i < n; i++) {
        const cur = pts[i];
        const prev = pts[(i - 1 + n) % n];
        const next = pts[(i + 1) % n];
        const v1x = prev[0] - cur[0];
        const v1y = prev[1] - cur[1];
        const len1 = Math.hypot(v1x, v1y);
        const a = [cur[0] + (v1x / len1) * r, cur[1] + (v1y / len1) * r];
        const v2x = next[0] - cur[0];
        const v2y = next[1] - cur[1];
        const len2 = Math.hypot(v2x, v2y);
        const b = [cur[0] + (v2x / len2) * r, cur[1] + (v2y / len2) * r];
        d += (i === 0 ? "M " : "L ") + _f(a[0]) + " " + _f(a[1]) + " ";
        d += "Q " + _f(cur[0]) + " " + _f(cur[1]) + " " + _f(b[0]) + " " + _f(b[1]) + " ";
    }
    return d + "Z";
}

/**
 * Parametric star: n points with inner radius ratio and optional soft
 * (rounded) corners.
 */
export function pathParametricStar({ points, innerRatio, cornerRadius }) {
    const n = Math.max(3, Math.min(16, Math.round(points)));
    const cx = 50;
    const cy = 50;
    const ro = 45;
    const ri = ro * Math.max(0.15, Math.min(0.85, innerRatio));
    const pts = [];
    for (let i = 0; i < n * 2; i++) {
        const r = i % 2 === 0 ? ro : ri;
        const ang = -Math.PI / 2 + (i * Math.PI) / n;
        pts.push([cx + r * Math.cos(ang), cy + r * Math.sin(ang)]);
    }
    if (cornerRadius <= 0.001) {
        return "M " + pts.map((p) => _f(p[0]) + " " + _f(p[1])).join(" L ") + " Z";
    }
    let d = "";
    const total = pts.length;
    for (let i = 0; i < total; i++) {
        const cur = pts[i];
        const prev = pts[(i - 1 + total) % total];
        const next = pts[(i + 1) % total];
        const v1x = prev[0] - cur[0];
        const v1y = prev[1] - cur[1];
        const len1 = Math.hypot(v1x, v1y);
        const v2x = next[0] - cur[0];
        const v2y = next[1] - cur[1];
        const len2 = Math.hypot(v2x, v2y);
        const r = Math.min(len1, len2) * 0.5 * Math.max(0, Math.min(1, cornerRadius));
        const a = [cur[0] + (v1x / len1) * r, cur[1] + (v1y / len1) * r];
        const b = [cur[0] + (v2x / len2) * r, cur[1] + (v2y / len2) * r];
        d += (i === 0 ? "M " : "L ") + _f(a[0]) + " " + _f(a[1]) + " ";
        d += "Q " + _f(cur[0]) + " " + _f(cur[1]) + " " + _f(b[0]) + " " + _f(b[1]) + " ";
    }
    return d + "Z";
}

/**
 * Parametric burst: n straight rays with a configurable valley depth.
 */
export function pathParametricBurst({ rays, depth }) {
    const n = Math.max(4, Math.min(32, Math.round(rays)));
    const ro = 47;
    const ri = ro * (1 - Math.max(0.1, Math.min(0.7, depth)));
    let d = "";
    for (let i = 0; i < n * 2; i++) {
        const r = i % 2 === 0 ? ro : ri;
        const ang = -Math.PI / 2 + (i * Math.PI) / n;
        d += (i === 0 ? "M " : "L ") + _f(50 + r * Math.cos(ang)) + " " + _f(50 + r * Math.sin(ang)) + " ";
    }
    return d + "Z";
}

/**
 * Parametric flower: sinusoidal radius modulation around the centre.
 */
export function pathParametricFlower({ petals, depth }) {
    const n = Math.max(3, Math.min(16, Math.round(petals)));
    const cx = 50;
    const cy = 50;
    const baseR = 25;
    const amp = (45 - baseR) * Math.max(0.2, Math.min(1, depth));
    const samples = Math.max(120, n * 24);
    let d = "";
    for (let i = 0; i <= samples; i++) {
        const ang = (i * 2 * Math.PI) / samples;
        const r = baseR + amp * (0.5 + 0.5 * Math.cos(n * ang));
        d += (i === 0 ? "M " : "L ") + _f(cx + r * Math.cos(ang)) + " " + _f(cy + r * Math.sin(ang)) + " ";
    }
    return d + "Z";
}

/**
 * Parametric sunny: like burst but the valleys are implied by a fixed
 * valley radius, giving a gentler sun look.
 */
export function pathParametricSunny({ rays, length }) {
    const n = Math.max(6, Math.min(32, Math.round(rays)));
    const valleyR = 30;
    const peakR = valleyR + (45 - valleyR) * Math.max(0.1, Math.min(1, length));
    let d = "";
    for (let i = 0; i < n * 2; i++) {
        const r = i % 2 === 0 ? peakR : valleyR;
        const ang = -Math.PI / 2 + (i * Math.PI) / n;
        d += (i === 0 ? "M " : "L ") + _f(50 + r * Math.cos(ang)) + " " + _f(50 + r * Math.sin(ang)) + " ";
    }
    return d + "Z";
}

/**
 * Parametric shape definitions: kind + params to SVG path-d, plus the
 * slider definitions the properties panel renders. Persisted on objects as
 * { _shapeKind, _shapeParams } so a re-load regenerates the same path.
 */
export const PARAM_SHAPES = {
    polygon: {
        label: "Polygon",
        build: pathParametricPolygon,
        defaults: { sides: 6, cornerRadius: 0.2 },
        params: [
            { key: "sides", label: "Sides", min: 3, max: 12, step: 1 },
            { key: "cornerRadius", label: "Corner radius", min: 0, max: 1, step: 0.05 },
        ],
    },
    pstar: {
        label: "Star",
        build: pathParametricStar,
        defaults: { points: 5, innerRatio: 0.45, cornerRadius: 0 },
        params: [
            { key: "points", label: "Points", min: 3, max: 12, step: 1 },
            { key: "innerRatio", label: "Inner radius", min: 0.15, max: 0.85, step: 0.05 },
            { key: "cornerRadius", label: "Soft corners", min: 0, max: 1, step: 0.05 },
        ],
    },
    pburst: {
        label: "Burst",
        build: pathParametricBurst,
        defaults: { rays: 12, depth: 0.35 },
        params: [
            { key: "rays", label: "Rays", min: 4, max: 32, step: 1 },
            { key: "depth", label: "Depth", min: 0.1, max: 0.7, step: 0.05 },
        ],
    },
    pflower: {
        label: "Flower",
        build: pathParametricFlower,
        defaults: { petals: 6, depth: 0.7 },
        params: [
            { key: "petals", label: "Petals", min: 3, max: 16, step: 1 },
            { key: "depth", label: "Depth", min: 0.2, max: 1, step: 0.05 },
        ],
    },
    psunny: {
        label: "Sunny",
        build: pathParametricSunny,
        defaults: { rays: 16, length: 0.4 },
        params: [
            { key: "rays", label: "Rays", min: 6, max: 32, step: 1 },
            { key: "length", label: "Length", min: 0.1, max: 1, step: 0.05 },
        ],
    },
};

/**
 * Primitives offered at the top of the shapes menu. These are native Fabric
 * objects (Rect, Circle, Triangle, Line, Group), not paths, so each maps to
 * an add* method on the editor dialog rather than to a path in SHAPES.
 */
export const BASIC_SHAPES = [
    { kind: "rect", label: "Rectangle", icon: "fa-square-o" },
    { kind: "circle", label: "Circle", icon: "fa-circle" },
    { kind: "ring", label: "Ring", icon: "fa-circle-o" },
    { kind: "triangle", label: "Triangle", icon: "fa-caret-up" },
    { kind: "line", label: "Line", icon: "fa-minus" },
    { kind: "arrow", label: "Arrow", icon: "fa-long-arrow-right" },
];

/**
 * Path shape catalog. Path-based and parametric shapes are inserted from the
 * shapes menu via fabric.Path, scaled by targetSize / 100. The primitives
 * live in BASIC_SHAPES above and share the same menu.
 */
export const SHAPES = [
    { kind: "pill", label: "Pill", path: "M 25 0 H 75 A 25 25 0 0 1 75 100 H 25 A 25 25 0 0 1 25 0 Z" },
    { kind: "diamond", label: "Diamond", path: "M 50 0 L 100 50 L 50 100 L 0 50 Z" },
    { kind: "pentagon", label: "Pentagon", path: "M 50 5 L 95 38 L 78 90 L 22 90 L 5 38 Z" },
    { kind: "hexagon", label: "Hexagon", path: "M 50 5 L 95 28 L 95 72 L 50 95 L 5 72 L 5 28 Z" },
    { kind: "octagon", label: "Octagon", path: "M 30 5 H 70 L 95 30 V 70 L 70 95 H 30 L 5 70 V 30 Z" },
    { kind: "star5", label: "Star 5", path: "M 50 5 L 61 38 L 95 38 L 67 59 L 78 92 L 50 71 L 22 92 L 33 59 L 5 38 L 39 38 Z" },
    { kind: "star6", label: "Star 6", path: "M 50 5 L 61 30 L 88 30 L 67 50 L 88 70 L 61 70 L 50 95 L 39 70 L 12 70 L 33 50 L 12 30 L 39 30 Z" },
    { kind: "burst8", label: "Burst 8", path: buildBurstPath(8, 47, 24) },
    { kind: "burst12", label: "Burst 12", path: buildBurstPath(12, 47, 30) },
    { kind: "plus", label: "Plus", path: "M 35 5 H 65 V 35 H 95 V 65 H 65 V 95 H 35 V 65 H 5 V 35 H 35 Z" },
    { kind: "cross", label: "Cross", path: "M 30 18 L 50 38 L 70 18 L 82 30 L 62 50 L 82 70 L 70 82 L 50 62 L 30 82 L 18 70 L 38 50 L 18 30 Z" },
    { kind: "heart", label: "Heart", path: "M 50 88 C 12 60 5 30 28 14 C 39 7 47 12 50 22 C 53 12 61 7 72 14 C 95 30 88 60 50 88 Z" },
    { kind: "cloud", label: "Cloud", path: "M 25 75 A 18 18 0 1 1 25 39 A 22 22 0 0 1 70 28 A 18 18 0 0 1 88 50 A 16 16 0 0 1 78 78 H 30 A 14 14 0 0 1 25 75 Z" },
    { kind: "speech", label: "Speech bubble", path: "M 10 12 H 90 V 65 H 60 L 38 88 L 45 65 H 10 Z" },
    { kind: "chevron", label: "Chevron arrow", path: "M 5 30 L 50 30 L 50 10 L 95 50 L 50 90 L 50 70 L 5 70 Z" },
    { kind: "pixel-tri", label: "Pixel triangle", path: "M 50 8 L 92 84 H 8 Z" },
    { kind: "gem", label: "Gem", path: "M 25 8 H 75 L 95 38 L 50 95 L 5 38 Z M 25 8 L 50 38 L 75 8 M 5 38 L 50 38 L 95 38" },

    // Parametric: initial path uses the defaults; the user morphs live in
    // the properties panel.
    ...Object.entries(PARAM_SHAPES).map(([kind, def]) => ({
        kind,
        label: def.label,
        parametric: true,
        path: def.build(def.defaults),
        defaults: def.defaults,
    })),
];

export const SHAPE_META = Object.fromEntries(SHAPES.map((s) => [s.kind, s]));

export const TEXT_TYPES = ["textbox", "i-text", "text"];

export function isTextType(type) {
    return TEXT_TYPES.includes((type || "").toLowerCase());
}

export function isImageType(type) {
    return (type || "").toLowerCase() === "image";
}
