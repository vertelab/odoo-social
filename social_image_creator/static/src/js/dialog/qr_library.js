/** @odoo-module **/

// Editor QR helpers (design D5 in
// openspec/changes/editor-grid-dynamic-elements), mirroring
// render_service/qr_matrix.mjs. qrMatrixToRectSpecs and the validation in
// qrContentToMatrix are verbatim copies of the render-side module; the only
// difference is where the generator comes from: the service copy requires
// the qrcode-generator npm package (node), while this copy runs against the
// same library vendored for the browser (static/lib/qrcode-generator), wired
// in through initQrGenerator() by the dialog after lib/qr_loader.js
// resolves. A fixture test asserts both produce the identical matrix.
//
// Contract (identical to the render side):
//   qrContentToMatrix(content, { errorLevel }) -> boolean[][] (true = dark)
//   qrMatrixToRectSpecs(matrix, moduleSize, color) ->
//       [{ left, top, size, fill }]  (one entry per dark module)
//   QR_PROP = '_qrContent' names the fabric custom property holding the
//   (already token-substituted) content string on a group.

export const QR_PROP = '_qrContent'

const ERROR_LEVELS = new Set(['L', 'M', 'Q', 'H'])

// Upper bound sanity check so nonsense sizes fail with a clear message
// instead of deep inside the generator. Version 40-L holds 2953 bytes;
// 4000 chars of UTF-8 can exceed every level, which is the practical limit.
const MAX_CONTENT_LENGTH = 4000

// The vendored qrcode-generator entry point, injected by the dialog via
// initQrGenerator() once lib/qr_loader.js has resolved. Kept module-level
// so qrContentToMatrix keeps the render-side signature.
let _qrcode = null

/**
 * Wire in the generator (window.qrcode from the vendored UMD build).
 * Called once by the dialog on first QR use; test suites call it with the
 * library loaded from the vendored file directly.
 */
export function initQrGenerator(qrcode) {
    if (typeof qrcode !== 'function') {
        throw new Error('initQrGenerator: qrcode must be the qrcode-generator factory')
    }
    _qrcode = qrcode
}

/**
 * Encode `content` to a QR module matrix: a square, odd-sized 2D boolean
 * array where true marks a dark module. Throws a clear Error on empty or
 * unencodable content; the caller surfaces it, never aborts silently.
 * Validation and matrix extraction are identical to the render side.
 */
export function qrContentToMatrix(content, { errorLevel = 'M' } = {}) {
    if (!_qrcode) {
        throw new Error('qrContentToMatrix: QR generator not loaded')
    }
    const level = String(errorLevel || 'M').toUpperCase()
    if (!ERROR_LEVELS.has(level)) {
        throw new Error(
            `qrContentToMatrix: errorLevel must be one of L, M, Q, H, got ${JSON.stringify(errorLevel)}`
        )
    }
    const text = String(content ?? '')
    if (text.length === 0) {
        throw new Error('qrContentToMatrix: content is empty')
    }
    if (text.length > MAX_CONTENT_LENGTH) {
        throw new Error(
            `qrContentToMatrix: content is too long (${text.length} chars, max ${MAX_CONTENT_LENGTH})`
        )
    }
    const qr = _qrcode(0, level) // typeNumber 0 = auto version selection
    try {
        qr.addData(text)
        qr.make()
    } catch (err) {
        const reason = typeof err === 'string' ? err : (err && err.message) || String(err)
        throw new Error(`qrContentToMatrix: cannot encode content: ${reason}`)
    }
    const count = qr.getModuleCount()
    const matrix = []
    for (let row = 0; row < count; row += 1) {
        const line = []
        for (let col = 0; col < count; col += 1) {
            line.push(Boolean(qr.isDark(row, col)))
        }
        matrix.push(line)
    }
    return matrix
}

/**
 * Convert a module matrix to one rect spec per dark module:
 * { left, top, size, fill }. Pure geometry: left/top are col/row times
 * moduleSize, so every position is an exact multiple of moduleSize.
 * Verbatim copy of render_service/qr_matrix.mjs.
 */
export function qrMatrixToRectSpecs(matrix, moduleSize, color = '#000000') {
    if (!Array.isArray(matrix) || matrix.length === 0) {
        throw new Error('qrMatrixToRectSpecs: matrix must be a non-empty 2D array')
    }
    const size = Number(moduleSize)
    if (!Number.isFinite(size) || size <= 0) {
        throw new Error(`qrMatrixToRectSpecs: moduleSize must be a positive number, got ${JSON.stringify(moduleSize)}`)
    }
    const fill = String(color)
    const specs = []
    for (let row = 0; row < matrix.length; row += 1) {
        const line = matrix[row]
        if (!Array.isArray(line) || line.length !== matrix.length) {
            throw new Error('qrMatrixToRectSpecs: matrix must be square')
        }
        for (let col = 0; col < line.length; col += 1) {
            if (line[col]) {
                specs.push({
                    left: col * size,
                    top: row * size,
                    size,
                    fill,
                })
            }
        }
    }
    return specs
}
