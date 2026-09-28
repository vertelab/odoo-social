// render_service/test_security.mjs: security behaviour of server.mjs.
//
//  1. SVG output must XML-escape binding values: a value containing
//     <script> renders as escaped text, never as markup.
//  2. /fonts and /fonts/reload require the bearer token (401 otherwise).
//  3. /health reports the registered font count and stays open.
//
// These start the real service on a free port, so they need the native
// node-canvas dependency (present in the service container, `npm install`
// with cairo dev libs). On a machine without it the file skips with exit
// 0 so `npm test` stays usable for the fabric-free unit tests.
import assert from 'node:assert'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

try {
    await import('canvas')
    await import('fabric/node')
} catch {
    console.log('SKIP: test_security needs node-canvas (run in the container or after npm install with cairo dev libs)')
    process.exit(0)
}

const here = dirname(fileURLToPath(import.meta.url))
const SERVER = join(here, 'server.mjs')
const TOKEN = 'cafebabe'.repeat(8)
const SVG_SCENE = {
    version: '6.9.1',
    objects: [
        {
            type: 'textbox',
            left: 10,
            top: 10,
            width: 600,
            fontSize: 24,
            fontFamily: 'Arial',
            fill: '#1a1a1a',
            text: '{{headline}}',
        },
    ],
    background: '#ffffff',
}

function start(port) {
    const child = spawn(process.execPath, [SERVER], {
        env: { ...process.env, PORT: String(port), RENDER_TOKEN: TOKEN },
        stdio: ['ignore', 'pipe', 'pipe'],
    })
    let out = ''
    child.stdout.on('data', (d) => (out += d))
    child.stderr.on('data', (d) => (out += d))
    return { child, output: () => out }
}

async function waitForPort(port, tries = 40) {
    for (let i = 0; i < tries; i++) {
        try {
            const res = await fetch(`http://127.0.0.1:${port}/health`)
            if (res.ok) return true
        } catch {
            // not up yet
        }
        await sleep(100)
    }
    return false
}

const { child } = start(8795)
try {
    assert.ok(await waitForPort(8795), 'service should start')

    // 1. SVG output escapes binding values (markup injection test).
    {
        const res = await fetch('http://127.0.0.1:8795/render', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${TOKEN}`,
            },
            body: JSON.stringify({
                scene_json: SVG_SCENE,
                width: 640,
                height: 120,
                bindings: { headline: '<script>alert(1)</script>' },
                format: 'svg',
            }),
        })
        assert.equal(res.status, 200, `render failed: ${await res.text()}`)
        assert.match(res.headers.get('content-type'), /image\/svg/)
        const svg = await res.text()
        assert.ok(svg.startsWith('<svg') || svg.includes('<svg'), 'SVG document returned')
        assert.ok(
            svg.includes('&lt;script&gt;alert(1)&lt;/script&gt;'),
            'binding value must appear XML-escaped'
        )
        assert.ok(!svg.includes('<script>'), 'no raw script element may appear')
        // No double escaping either: '&amp;lt;' would show literally.
        assert.ok(!svg.includes('&amp;lt;'), 'value must be escaped exactly once')
        console.log('✓ SVG output XML-escapes binding values (<script> inert)')
    }

    // 2. /fonts and /fonts/reload are token-protected.
    {
        for (const [path, method] of [['/fonts', 'GET'], ['/fonts/reload', 'POST']]) {
            for (const header of [`Bearer wrong`, undefined]) {
                const res = await fetch(`http://127.0.0.1:8795${path}`, {
                    method,
                    headers: header ? { Authorization: header } : {},
                })
                assert.equal(
                    res.status,
                    401,
                    `${method} ${path} with ${header || 'no header'} must be 401, got ${res.status}`
                )
            }
        }
        const ok = await fetch('http://127.0.0.1:8795/fonts', {
            headers: { Authorization: `Bearer ${TOKEN}` },
        })
        assert.equal(ok.status, 200)
        const body = await ok.json()
        assert.ok(Array.isArray(body.fonts), '/fonts returns a fonts list')
        const reload = await fetch('http://127.0.0.1:8795/fonts/reload', {
            method: 'POST',
            headers: { Authorization: `Bearer ${TOKEN}` },
        })
        assert.equal(reload.status, 200)
        console.log('✓ /fonts and /fonts/reload reject bad tokens (401), accept the real one')
    }

    // 3. /health stays open and reports the font registry.
    {
        const res = await fetch('http://127.0.0.1:8795/health')
        assert.equal(res.status, 200)
        const body = await res.json()
        assert.equal(body.status, 'ok')
        assert.equal(typeof body.fonts_registered, 'number')
        console.log('✓ /health open and reports fonts_registered')
    }
} finally {
    child.kill()
}

console.log('\nALL security TESTS PASSED')
