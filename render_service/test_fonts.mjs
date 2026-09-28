// render_service/test_fonts.mjs: unit tests for fonts.mjs.
//
// Two layers:
//  1. Scan/registry logic with a fake registerFont injection (always runs,
//     no node-canvas needed). Uses fixture files in a temp dir.
//  2. A real registration test, only when a font file exists in fonts/:
//     registers it and asserts measureText differs from the unregistered
//     default. Skipped gracefully when fonts/ is empty (the common case in
//     CI and fresh checkouts).
import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { listRegisteredFonts, registerFontsInDir } from './fonts.mjs'

// --- 1. Scan/registry logic with a fake registerFont ---------------------
{
    const dir = await mkdtemp(join(tmpdir(), 'render-fonts-'))
    try {
        // Fake font bytes: the fake registerFont does not parse them.
        await writeFile(join(dir, 'BrandonGrotesque-Bold.ttf'), 'fake-ttf')
        await writeFile(join(dir, 'Inter-Regular.otf'), 'fake-otf')
        await writeFile(join(dir, 'notes.txt'), 'not a font')
        await writeFile(join(dir, 'broken.woff2'), 'fake-woff2')

        const calls = []
        const fakeRegister = async (path, opts) => {
            calls.push({ path, opts })
            if (path.endsWith('.woff2')) {
                throw new Error('unsupported format in fake register')
            }
        }

        const result = await registerFontsInDir(dir, fakeRegister)
        assert.equal(result.registered.length, 2)
        assert.equal(result.skipped.length, 1)
        assert.equal(result.skipped[0].error, 'unsupported format in fake register')

        // Family name convention: basename without extension.
        const families = result.registered.map((r) => r.family).sort()
        assert.deepEqual(families, ['BrandonGrotesque-Bold', 'Inter-Regular'])
        assert.equal(calls.length, 3, 'every font file is attempted once, incl. the failing one')
        for (const call of calls) {
            assert.ok(call.path.startsWith(dir), 'resolved to the scanned dir')
        }

        // Registry listing feeds /health and /fonts.
        const listed = listRegisteredFonts().map((f) => f.family).sort()
        assert.deepEqual(listed, ['BrandonGrotesque-Bold', 'Inter-Regular'])

        // A missing directory is not an error: nothing to register.
        const empty = await registerFontsInDir(join(dir, 'does-not-exist'), fakeRegister)
        assert.deepEqual(empty, { registered: [], skipped: [] })
        console.log('✓ scan/registry logic (fake registerFont injection)')
    } finally {
        await rm(dir, { recursive: true, force: true })
    }
}

// --- 2. Real registration, only when a font file exists in fonts/ --------
{
    let realRegisterFont = null
    let createCanvas = null
    try {
        // Optional import: node-canvas needs native libs that may be absent
        // on a dev machine (they are present in the service container).
        const canvasMod = await import('canvas')
        realRegisterFont = canvasMod.registerFont
        createCanvas = canvasMod.createCanvas
    } catch {
        realRegisterFont = null
    }

    const fontsDir = new URL('./fonts', import.meta.url).pathname
    const { readdir } = await import('node:fs/promises')
    const files = await readdir(fontsDir).catch(() => [])
    const fontFile = files.find((f) => /\.(ttf|otf)$/i.test(f))

    if (!realRegisterFont || !fontFile) {
        console.log('✓ real font registration SKIPPED (no node-canvas or fonts/ empty)')
    } else {
        const { registered, skipped } = await registerFontsInDir(fontsDir, realRegisterFont)
        assert.equal(skipped.length, 0, 'no font file should fail to register')
        assert.ok(registered.length > 0, 'at least the present font registers')

        const canvas = createCanvas(400, 100)
        const ctx = canvas.getContext('2d')
        ctx.font = '40px "NoSuchFontAnywhereXYZ"'
        const defaultWidth = ctx.measureText('Sommar').width
        ctx.font = `40px "${registered[0].family}"`
        const fontWidth = ctx.measureText('Sommar').width
        assert.notEqual(
            fontWidth,
            defaultWidth,
            `registered font ${registered[0].family} must measure differently than the fallback`
        )
        console.log(`✓ real font registration (${registered[0].family} changes textWidth)`)
    }
}

console.log('\nALL fonts TESTS PASSED')
