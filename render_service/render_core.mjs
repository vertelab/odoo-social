// render_service/render_core.mjs
// Pure, fabric-free core of the render service — unit-testable without
// node-canvas. Mirrors the `*_core` TDD pattern used across the codebase.

const TOKEN_RE = /\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g

export function xmlEscape(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&apos;')
}

/**
 * Substitute every {{name}} token in `text` using `bindings`. Unknown
 * tokens are left untouched. Values are always injected as text.
 */
export function substituteText(text, bindings) {
    return String(text ?? '').replace(TOKEN_RE, (match, name) => {
        if (Object.prototype.hasOwnProperty.call(bindings, name)) {
            return String(bindings[name] ?? '')
        }
        return match
    })
}

function isEmptyValue(v) {
    return v === undefined || v === null || (typeof v === 'string' && v.trim() === '')
}

/**
 * Apply bindings to a Fabric scene (deep copy in, mutated copy out):
 *  - {{name}} tokens in every text layer are substituted
 *  - layers with `_hideIfEmpty: {placeholder}` are hidden when the bound
 *    value is empty
 *  - image layer srcs are absolutized for /web/image/... paths
 * When `escapeXml` is true the substituted text is XML-escaped.
 *
 * Do NOT pass `escapeXml: true` for the SVG path in server.mjs: Fabric's
 * `canvas.toSVG()` escapes the text itself when it serializes, so escaping
 * beforehand produces `&amp;amp;` and `&lt;` shown literally to whoever opens
 * the file. Escaping belongs to whoever writes the XML, and for SVG that is
 * Fabric. This option exists for callers that build XML without Fabric.
 */
export function applyBindingsToScene(sceneJson, bindings = {}, { escapeXml = false, apiBase = '' } = {}) {
    const json = JSON.parse(JSON.stringify(sceneJson))
    if (!Array.isArray(json.objects)) {
        return json
    }
    for (const obj of json.objects) {
        const hie = obj._hideIfEmpty
        if (hie && hie.placeholder && isEmptyValue(bindings[hie.placeholder])) {
            obj.visible = false
            obj.opacity = 0
        }
        if (obj.type === 'image' || obj.type === 'Image') {
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
