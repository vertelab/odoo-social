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

export class SceneImageUrlError extends Error {
    constructor(message) {
        super(message)
        this.name = 'SceneImageUrlError'
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
 * Apply a layer-level case transform to a resolved string. Only
 * 'upper' / 'lower' / 'title' do anything; null, 'none' and unknown
 * values return the text unchanged. The semantics come from
 * applyPipeTransform so the _textTransform layer prop and the
 * {{token|pipe}} form can never drift apart. Non-string input passes
 * through untouched.
 */
export function applyTextTransform(text, transform) {
    if (typeof text !== 'string') return text
    if (transform === 'upper') return applyPipeTransform(text, 'upper')
    if (transform === 'lower') return applyPipeTransform(text, 'lower')
    if (transform === 'title') return applyPipeTransform(text, 'title')
    return text
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

// ------------------------------------------------------------------
// Render-time typography (design D2 in openspec/changes/creator-
// render-parity): case transform, inline markdown and overflow autofit
// all run inside applyBindingsToScene, after token substitution, so a
// bound value is styled exactly as the editor preview shows it.
// ------------------------------------------------------------------

/**
 * Autofit floor: a bound text is never shrunk below this size, whatever
 * the measurement says. The editor's edit-time autofit uses its own
 * (higher) floor; this one guards render-time fitting only.
 */
export const MIN_AUTOFIT_FONT_SIZE = 4

// Longest line of a (possibly multi-line) text, by character length.
// Width measuring is delegated to the caller, so this stays pure.
// Mirrors widestLine in social_image_editor_utils.js.
function widestLine(text) {
    if (typeof text !== 'string' || !text) {
        return ''
    }
    return text.split('\n').reduce((a, b) => (b.length > a.length ? b : a), '')
}

/**
 * Autofit font size: the largest font size at or below startSize whose
 * measured text width fits inside boxWidth. Never grows the text, never
 * shrinks below minSize. Binary search keeps it cheap and deterministic.
 * Mirrors computeAutofitFontSize in social_image_editor_utils.js
 * exactly; editor preview and server render must converge on the same
 * size for the same text.
 *
 * measure is (fontSize, widestLineText) => width in the same units as
 * boxWidth, injected so this stays pure and testable.
 */
export function computeAutofitFontSize({
    text,
    boxWidth,
    startSize,
    minSize = MIN_AUTOFIT_FONT_SIZE,
    measure,
}) {
    if (typeof measure !== 'function' || !boxWidth || boxWidth <= 0) {
        return startSize
    }
    const line = widestLine(text)
    if (!line) {
        return startSize
    }
    const start = Number(startSize) || 0
    const floor = Math.max(1, Number(minSize) || MIN_AUTOFIT_FONT_SIZE)
    if (start <= floor) {
        return start
    }
    if (measure(start, line) <= boxWidth) {
        return start
    }
    if (measure(floor, line) > boxWidth) {
        return floor
    }
    let lo = floor
    let hi = start
    for (let i = 0; i < 24; i++) {
        const mid = (lo + hi) / 2
        if (measure(mid, line) <= boxWidth) {
            lo = mid
        } else {
            hi = mid
        }
    }
    // The search converges from below, so an exact integer fit can floor
    // one short; probe upward while the next integer still fits.
    let best = Math.floor(lo)
    while (best < start && measure(best + 1, line) <= boxWidth) {
        best += 1
    }
    return Math.max(floor, best)
}

/**
 * Parse a small subset of markdown (**bold**, *italic*, _italic_) and
 * produce the stripped string plus flat segment ranges carrying
 * weight/style. Ported from parseMarkdownToFabricStyles in
 * render-engine-os render/server.mjs, with one addition: a backslash
 * escapes the next marker (\\* \\_ \\\\), so escaped markers stay
 * literal instead of opening or closing a segment. Unmatched markers
 * also stay literal: a text whose markers never pair up parses to no
 * segments at all, the function returns null and the caller leaves the
 * text untouched. Newlines pass through untouched (Fabric handles them
 * natively).
 *
 * Returns { text, segments: [{start, end, weight?, style?}] }, or null
 * when nothing was parsed so callers can skip the work.
 */
export function parseMarkdownSegments(text) {
    if (typeof text !== 'string') return null
    if (!/[*_]/.test(text)) return null // fast-out: no markers at all
    let stripped = ''
    const segments = [] // {start, end, weight?, style?}
    let i = 0
    let boldStart = -1
    let italicStart = -1
    while (i < text.length) {
        const c = text[i]
        const n = text[i + 1]
        // Escape: \* \_ \\ pass the next character through literally.
        if (c === '\\' && (n === '*' || n === '_' || n === '\\')) {
            stripped += n
            i += 2
            continue
        }
        // Bold: ** ... **
        if (c === '*' && n === '*') {
            if (boldStart === -1) {
                boldStart = stripped.length
            } else {
                segments.push({ start: boldStart, end: stripped.length, weight: 'bold' })
                boldStart = -1
            }
            i += 2
            continue
        }
        // Italic: single * or _
        if (c === '*' || c === '_') {
            if (italicStart === -1) {
                italicStart = stripped.length
            } else {
                segments.push({ start: italicStart, end: stripped.length, style: 'italic' })
                italicStart = -1
            }
            i += 1
            continue
        }
        stripped += c
        i++
    }
    if (segments.length === 0) return null
    return { text: stripped, segments }
}

// Translate flat string ranges into Fabric's styles structure:
//   { lineIdx: { charIdxWithinLine: { fontWeight, fontStyle } } }
function markdownSegmentsToFabricStyles(stripped, segments) {
    const lines = stripped.split('\n')
    const lineStarts = []
    let pos = 0
    for (const line of lines) {
        lineStarts.push(pos)
        pos += line.length + 1
    }
    const styles = {}
    for (const seg of segments) {
        for (let p = seg.start; p < seg.end; p++) {
            let lineIdx = 0
            for (let li = 0; li < lineStarts.length; li++) {
                if (p >= lineStarts[li]) lineIdx = li
                else break
            }
            const ci = p - lineStarts[lineIdx]
            if (!styles[lineIdx]) styles[lineIdx] = {}
            const merged = styles[lineIdx][ci] || {}
            if (seg.weight) merged.fontWeight = seg.weight
            if (seg.style) merged.fontStyle = seg.style
            styles[lineIdx][ci] = merged
        }
    }
    return styles
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
 *  - image layer srcs are restricted to the allowlist in
 *    absolutizeFileUrl: `data:` URLs and `/web/image/...` paths under
 *    `apiBase` only; anything else aborts with SceneImageUrlError
 *  - text layers then run the render-time typography pipeline, in this
 *    order so per-char style indices always describe the final text:
 *    substitution, optional XML escaping, `_textTransform` (upper /
 *    lower / title), inline markdown (**bold**, *italic*) converted to
 *    per-char styles merged into any existing styles, and finally
 *    `_overflow: autofit` recomputing fontSize against the resolved
 *    text (never growing, never below MIN_AUTOFIT_FONT_SIZE)
 * When `escapeXml` is true the substituted text is XML-escaped.
 * `measure` is the autofit width function (text, fontDescription) =>
 * width in canvas units; without it every candidate "fits" and fontSize
 * is left unchanged. server.mjs injects a node-canvas measurement.
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
    { escapeXml = false, apiBase = '', fitTargets = null, measure = null } = {}
) {
    const json = JSON.parse(JSON.stringify(sceneJson))
    if (!Array.isArray(json.objects)) {
        return json
    }
    // Without an injected measure every candidate "fits", so autofit
    // leaves fontSize untouched instead of guessing from nothing.
    const measureText = typeof measure === 'function' ? measure : () => 0
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
            try {
                obj.src = absolutizeFileUrl(obj.src, apiBase)
            } catch (err) {
                if (err instanceof SceneImageUrlError) {
                    const layerName = obj._layerName || obj.type || 'layer'
                    throw new SceneImageUrlError(`Layer "${layerName}": ${err.message}`)
                }
                throw err
            }
        }
        if (typeof obj.text !== 'string') {
            continue
        }
        // Order is fixed so per-char style indices always describe the
        // final obj.text: markdown markers contain no XML chars, so
        // escaping before parsing cannot hide them, and transform runs
        // before markers are stripped so segments index the final text.
        let text = substituteText(obj.text, bindings)
        if (escapeXml) {
            text = xmlEscape(text)
        }
        text = applyTextTransform(text, obj._textTransform)
        const md = parseMarkdownSegments(text)
        if (md) {
            text = md.text
            const mdStyles = markdownSegmentsToFabricStyles(text, md.segments)
            obj.styles = obj.styles || {}
            for (const [lineIdx, charMap] of Object.entries(mdStyles)) {
                const lineStyles = { ...(obj.styles[lineIdx] || {}) }
                for (const [ci, attrs] of Object.entries(charMap)) {
                    // Per-char merge: markdown only claims fontWeight /
                    // fontStyle, any other attribute already on the char
                    // (fill, underline, ...) survives.
                    lineStyles[ci] = { ...(lineStyles[ci] || {}), ...attrs }
                }
                obj.styles[lineIdx] = lineStyles
            }
        }
        if (obj._overflow === 'autofit' && obj.fontSize) {
            obj.fontSize = computeAutofitFontSize({
                text,
                boxWidth: obj.width,
                startSize: obj.fontSize,
                minSize: MIN_AUTOFIT_FONT_SIZE,
                measure: (size, line) =>
                    measureText(line, {
                        fontSize: size,
                        fontFamily: obj.fontFamily,
                        fontWeight: obj.fontWeight,
                        fontStyle: obj.fontStyle,
                    }),
            })
        }
        obj.text = text
    }
    return json
}

/**
 * Strict URL allowlist for scene image srcs (design D3 in
 * openspec/changes/creator-hardening). Fabric's node build loads image
 * srcs through JSDOM with `resources: 'usable'`, so every src in a scene
 * is a potential server-side fetch. Allowed:
 *  - `data:` URLs (self-contained, incl. binary-field bindings from Odoo)
 *  - `/web/image/...` paths, absolutized against `apiBase`
 *  - absolute http(s) URLs that start with `apiBase` (trailing slash
 *    trimmed, path boundary enforced), i.e. images already served by the
 *    configured Odoo
 * Everything else (other hosts, `file://`, other relative paths) throws
 * SceneImageUrlError naming the offending URL.
 */
export function absolutizeFileUrl(src, apiBase = '') {
    if (typeof src !== 'string' || !src) {
        return src
    }
    if (src.startsWith('data:')) {
        return src
    }
    if (src.startsWith('/web/image/')) {
        return `${apiBase}${src}`
    }
    if (src.startsWith('http://') || src.startsWith('https://')) {
        const base = String(apiBase).replace(/\/+$/, '')
        // Exact base or a path under it; the boundary check stops a host
        // that merely shares a prefix with the base (odoo:8069.evil...).
        if (src === base || src.startsWith(`${base}/`)) {
            return src
        }
        throw new SceneImageUrlError(
            `Image URL "${src}" is not under the configured API base "${base}"`
        )
    }
    throw new SceneImageUrlError(
        `Image URL "${src}" is not allowed: only data: URLs and /web/image paths under the configured API base may be rendered`
    )
}

/**
 * Pre-flight scan over a Fabric scene JSON (design D3): walk every object,
 * including nested group `.objects` arrays, and refuse scenes whose image
 * layers carry an src the allowlist rejects, naming the layer. server.mjs
 * runs this on the incoming scene and on the post-binding scene before
 * loadFromJSON, so a bad src is caught before JSDOM would fetch it.
 * Non-image objects and images without an src pass.
 */
export function assertSceneImageUrlsSafe(sceneJson, apiBase = '') {
    const walk = (objects) => {
        if (!Array.isArray(objects)) return
        for (const obj of objects) {
            if (!obj || typeof obj !== 'object') continue
            if (
                (obj.type === 'image' || obj.type === 'Image') &&
                typeof obj.src === 'string' &&
                obj.src
            ) {
                try {
                    absolutizeFileUrl(obj.src, apiBase)
                } catch (err) {
                    const layerName = obj._layerName || obj.type
                    throw new SceneImageUrlError(`Layer "${layerName}": ${err.message}`)
                }
            }
            walk(obj.objects)
        }
    }
    if (sceneJson && typeof sceneJson === 'object') {
        walk(sceneJson.objects)
    }
}
