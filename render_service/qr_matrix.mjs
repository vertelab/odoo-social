// render_service/qr_matrix.mjs
// Pure QR helpers around the vendored qrcode-generator package (design D5
// in openspec/changes/editor-grid-dynamic-elements). The editor vendors the
// same library for the browser and a fixture test asserts identical matrix
// output on both sides; keep this module free of fabric and node-canvas so
// it stays importable and testable without the Docker-only dependencies.
//
// Contract:
//   qrContentToMatrix(content, { errorLevel }) -> boolean[][] (true = dark)
//   qrMatrixToRectSpecs(matrix, moduleSize, color) ->
//       [{ left, top, size, fill }]  (one entry per dark module)
//   QR_PROP = '_qrContent' names the fabric custom property holding the
//   (already token-substituted) content string on a group.

import { createRequire } from 'node:module'

// qrcode-generator ships UMD CJS; require it from this ESM module. Loading
// via createRequire keeps the dependency out of the ESM graph so the pure
// test files do not need a bundler.
const require = createRequire(import.meta.url)
const qrcode = require('qrcode-generator')

// UTF-8 byte encoding, exactly what qrcode_UTF8.js from the same package
// does (qrcode.stringToBytes = qrcode.stringToBytesFuncs['UTF-8']). Applied
// here explicitly because requiring qrcode_UTF8.js itself would need a
// global `qrcode` binding; the base package already carries the UTF-8 table
// and this assignment is the entire content of that add-on file. Without
// it, non-ASCII content such as Swedish text would encode byte-wise wrong.
qrcode.stringToBytes = qrcode.stringToBytesFuncs['UTF-8']

// Custom property carrying the QR content on a fabric group (design D6).
export const QR_PROP = '_qrContent'

const ERROR_LEVELS = new Set(['L', 'M', 'Q', 'H'])

// Upper bound sanity check so nonsense sizes fail with a clear message
// instead of deep inside the generator. Version 40-L holds 2953 bytes;
// 4000 chars of UTF-8 can exceed every level, which is the practical limit.
const MAX_CONTENT_LENGTH = 4000

/**
 * Encode `content` to a QR module matrix: a square, odd-sized 2D boolean
 * array where true marks a dark module. Throws a clear Error on empty or
 * unencodable content; the render pipeline must surface it, never abort
 * silently.
 */
export function qrContentToMatrix(content, { errorLevel = 'M' } = {}) {
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
    const qr = qrcode(0, level) // typeNumber 0 = auto version selection
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
