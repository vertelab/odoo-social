// render_service/render_core.mjs
// Pure, fabric-free core of the render service, unit-testable without
// node-canvas. Mirrors the `*_core` TDD pattern used across the codebase.

// Match {{field}} and {{dotted.field.path}} with optional chained pipe
// transforms: {{name|upper}}, {{categ_id.name|title|trim}}. Mirrors the
// TOKEN_RE in social_image_creator/models/social_image_binding.py.
const TOKEN_RE = /\{\{\s*([a-zA-Z0-9_.-]+)\s*((?:\|[^}|]+)*)\}\}/g

export class RequiredBindingError extends Error {
    constructor(message) {
        super(message)
        this.name = 'RequiredBindingError'
    }
}

export function xmlEscape(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&apos;')
}

/**
 * Apply one pipe transform to a string. Unknown pipes leave the value
 * untouched (mirrors the editor preview exactly; ported from
 * render-engine-os).
 */
export function applyPipeTransform(value, pipe) {
    if (!pipe) return value
    switch (pipe) {
        case 'lower':
        case 'lowercase':
            return value.toLowerCase()
        case 'upper':
        case 'uppercase':
            return value.toUpperCase()
        case 'title':
            return value
                .replace(/\b\p{L}/gu, (c) => c.toUpperCase())
                .replace(/\B\p{L}+/gu, (m) => m.toLowerCase())
        case 'trim':
            return value.trim()
        case 'capitalize':
            return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase()
        default:
            return value
    }
}

/**
 * Substitute every {{name}} / {{path|pipe...}} token in `text` using
 * `bindings`. Unknown tokens are left untouched. Values are always
 * injected as text.
 */
export function substituteText(text, bindings) {
    return String(text ?? '').replace(TOKEN_RE, (match, name, pipes) => {
        if (!Object.prototype.hasOwnProperty.call(bindings, name)) {
            return match
        }
        let v = String(bindings[name] ?? '')
        if (pipes) {
            for (const p of pipes.split('|').filter(Boolean)) {
                v = applyPipeTransform(v, p.trim())
            }
        }
        return v
    })
}

function isEmptyValue(v) {
    return (
        v === undefined ||
        v === null ||
        v === false ||
        (typeof v === 'string' && v.trim() === '')
    )
}

// Unique id markers for cover-fit targets (see prepareCoverFit).
let __fitMarkerCounter = 0

/**
 * Cover-fit math for a data-bound image, shared with the editor's
 * applyImageCoverFit (social_image_editor_utils.js). The two must stay
 * identical; the rendered output depends on it.
 *
 * Fabric model: width/height are in source pixels (post-crop), cropX/cropY
 * are the source-pixel offset of the visible window, scaleX/scaleY scale
 * source pixels to display pixels. Cover semantics: scale up so the
 * smaller dimension fills the frame, crop the overflow centered.
 *
 * oldHostScaleX/Y are the host's scale BEFORE the fit; their ratio to the
 * new scale compensates a clipPath that lives in the host's local coord
 * space (image-fill shapes), keeping the on-canvas mask size unchanged.
 */
export function computeCoverFit(
    naturalW,
    naturalH,
    frameW,
    frameH,
    oldHostScaleX = 1,
    oldHostScaleY = 1
) {
    const scale = Math.max(frameW / naturalW, frameH / naturalH)
    const visibleW = frameW / scale
    const visibleH = frameH / scale
    return {
        scale,
        cropX: Math.max(0, (naturalW - visibleW) / 2),
        cropY: Math.max(0, (naturalH - visibleH) / 2),
        width: visibleW,
        height: visibleH,
        clipScaleX: (oldHostScaleX || 1) / scale,
        clipScaleY: (oldHostScaleY || 1) / scale,
    }
}

/**
 * Capture the pre-swap frame of a data-bound image layer and reset its
 * dims/scale/crop so Fabric loads the NEW image at its natural size.
 * The frame and marker go into `fitTargets` (keyed by a unique id stashed
 * on obj.id, a stateProperty Fabric preserves through loadFromJSON); the
 * caller re-applies the cover fit post-load. Ported from
 * render-engine-os render/server.mjs.
 */
export function prepareCoverFit(obj, fitTargets) {
    // Frame = layer's intended display size = width*scaleX x height*scaleY.
    const frameW = (obj.width || 0) * (obj.scaleX ?? 1)
    const frameH = (obj.height || 0) * (obj.scaleY ?? 1)
    // Capture the OLD host scale; needed to compensate any clipPath after
    // cover-fit changes the host's scale (clipPath lives in the host's
    // local coord space and would shrink with it).
    const oldHostScaleX = obj.scaleX ?? 1
    const oldHostScaleY = obj.scaleY ?? 1
    if (frameW <= 0 || frameH <= 0) return
    // Re-anchor to center origin at the frame center, so the post-load
    // clipPath (centered on the object's bbox) lands where the user
    // actually placed the layer, whatever its original origin was.
    const ox = obj.originX || 'left'
    const oy = obj.originY || 'top'
    const left = obj.left || 0
    const top = obj.top || 0
    const dx = ox === 'left' ? frameW / 2 : ox === 'right' ? -frameW / 2 : 0
    const dy = oy === 'top' ? frameH / 2 : oy === 'bottom' ? -frameH / 2 : 0
    const marker = `arc_fit_${++__fitMarkerCounter}`
    obj.id = marker
    fitTargets.set(marker, {
        frameW,
        frameH,
        oldHostScaleX,
        oldHostScaleY,
        hadClipPath: !!obj.clipPath,
    })
    delete obj.width
    delete obj.height
    obj.cropX = 0
    obj.cropY = 0
    obj.scaleX = 1
    obj.scaleY = 1
    obj.originX = 'center'
    obj.originY = 'center'
    obj.left = left + dx
    obj.top = top + dy
}

/**
 * Apply bindings to a Fabric scene (deep copy in, mutated copy out):
 *  - {{field|pipe...}} tokens in every text layer are substituted
 *  - layers with `_hideIfEmpty: {field}` are hidden when the bound value
 *    is empty
 *  - layers with `_required: {field}` abort with RequiredBindingError
 *    naming the layer when the bound value is empty
 *  - image layers with `_dataBinding: {field}` swap their src for the
 *    bound value (empty hides the layer); with `fitTargets` provided the
 *    pre-swap frame is captured for post-load cover-fit re-application
 *  - image layer srcs are absolutized for /web/image/... paths
 * When `escapeXml` is true the substituted text is XML-escaped.
 *
 * Do NOT pass `escapeXml: true` for the SVG path in server.mjs: Fabric's
 * `canvas.toSVG()` escapes the text itself when it serializes, so escaping
 * beforehand produces `&amp;amp;` and `&lt;` shown literally to whoever opens
 * the file. Escaping belongs to whoever writes the XML, and for SVG that is
 * Fabric. This option exists for callers that build XML without Fabric.
 */
export function applyBindingsToScene(
    sceneJson,
    bindings = {},
    { escapeXml = false, apiBase = '', fitTargets = null } = {}
) {
    const json = JSON.parse(JSON.stringify(sceneJson))
    if (!Array.isArray(json.objects)) {
        return json
    }
    for (const obj of json.objects) {
        if (!obj || typeof obj !== 'object') continue
        const hie = obj._hideIfEmpty
        if (hie && hie.field && isEmptyValue(bindings[hie.field])) {
            obj.visible = false
            obj.opacity = 0
        }
        const req = obj._required
        if (req && req.field && isEmptyValue(bindings[req.field])) {
            const layerName = obj._layerName || obj.type || 'layer'
            throw new RequiredBindingError(
                `Required binding "${req.field}" on layer "${layerName}" resolved to an empty value`
            )
        }
        if (obj.type === 'image' || obj.type === 'Image') {
            const db = obj._dataBinding
            if (db && db.field) {
                const newSrc = bindings[db.field]
                if (typeof newSrc === 'string' && newSrc) {
                    if (fitTargets) {
                        prepareCoverFit(obj, fitTargets)
                    }
                    obj.src = newSrc
                } else {
                    // Bound to a field whose value is empty: hide the layer
                    // rather than leaking the static placeholder image into
                    // the rendered output.
                    obj.visible = false
                    obj.opacity = 0
                }
            }
            obj.src = absolutizeFileUrl(obj.src, apiBase)
        }
        if (typeof obj.text !== 'string') {
            continue
        }
        let text = substituteText(obj.text, bindings)
        if (escapeXml) {
            text = xmlEscape(text)
        }
        obj.text = text
    }
    return json
}

export function absolutizeFileUrl(src, apiBase = '') {
    if (typeof src !== 'string' || !src) {
        return src
    }
    if (src.startsWith('data:')) {
        return src
    }
    if (src.startsWith('http://') || src.startsWith('https://')) {
        return src
    }
    if (src.startsWith('/web/image/')) {
        return `${apiBase}${src}`
    }
    return src
}
