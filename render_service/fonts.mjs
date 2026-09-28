// render_service/fonts.mjs
// Font registration for the render service (design D6).
//
// Brand fonts must render identically in the editor and in server-side
// PNGs. The editor applies fonts by family name; node-canvas only knows
// system fonts unless each file is registered explicitly. This module
// scans a fonts directory and registers every font file with node-canvas
// `registerFont`, using the file basename (without extension) as the
// family name. The editor must use that exact name in Fabric.
//
// The registry functions take `registerFont` as an injectable dependency
// so the scan/registry logic is unit-testable without node-canvas.

import { readdir } from 'node:fs/promises'
import { basename, extname, join } from 'node:path'

// Extensions node-canvas can register. TTF and OTF are supported
// everywhere node-canvas runs. WOFF/WOFF2 depend on the platform font
// stack (fontconfig); registration is attempted and failures are logged
// per file, never fatal.
const FONT_EXTENSIONS = new Set(['.ttf', '.otf', '.woff', '.woff2'])

// Cache of what has been registered, for /health and /fonts reporting.
const registered = new Map() // family -> file path

export function listRegisteredFonts() {
    return [...registered.entries()].map(([family, file]) => ({ family, file }))
}

/**
 * Scan `dir` for font files and register each one through `registerFont`.
 * Returns { registered: [{family, file}], skipped: [{file, error}] }.
 * A file that fails to register is reported in `skipped`, never thrown:
 * a single corrupt font must not take the service down.
 */
export async function registerFontsInDir(dir, registerFont) {
    const result = { registered: [], skipped: [] }
    let files
    try {
        files = await readdir(dir)
    } catch (err) {
        if (err.code === 'ENOENT') {
            return result // no fonts dir: nothing to do
        }
        throw err
    }
    for (const file of files.sort()) {
        const ext = extname(file).toLowerCase()
        if (!FONT_EXTENSIONS.has(ext)) continue
        const family = basename(file, ext)
        const fullPath = join(dir, file)
        try {
            await registerFont(fullPath, { family })
            registered.set(family, fullPath)
            result.registered.push({ family, file: fullPath })
        } catch (err) {
            result.skipped.push({ file: fullPath, error: err.message })
        }
    }
    return result
}
