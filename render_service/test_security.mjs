// render_service/test_security.mjs: security behaviour of server.mjs.
//
//  1. SVG output must XML-escape binding values: a value containing
//     <script> renders as escaped text, never as markup.
//  2. /fonts and /fonts/reload require the bearer token (401 otherwise).
//  3. /health reports the registered font count and stays open.
//  4. Scene image srcs are allowlisted: anything outside data: URLs and
//     /web/image paths under API_BASE_URL is refused with 400 naming the
//     layer, before any outbound fetch (localhost, file://, foreign host,
//     nested group members).
//  5. /render dimensions are capped (integers 16..8192, pixel product at
//     most 67108864); oversized canvases get a 400 naming the limit.
//
// These start the real service on a free port, so they need the native
// node-canvas dependency (present in the service container, `npm install`
// with cairo dev libs). On a machine without it the file skips with exit
// 0 so `npm test` stays usable for the fabric-free unit tests.
import assert from 'node:assert'
import { spawn } from 'node:child_process'
import http from 'node:http'
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
// Stub Odoo for the allowlist-passing cases: the service must be allowed
// to fetch /web/image/... from API_BASE_URL, and only that. Serves a real
// 1x1 PNG so Fabric can actually load it.
const STUB_PORT = 8796
const API_BASE = `http://127.0.0.1:${STUB_PORT}`
const STUB_PNG = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
    'base64'
)
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

function startImageStub(port) {
    const server = http.createServer((req, res) => {
        if ((req.url || '').startsWith('/web/image/')) {
            res.writeHead(200, { 'Content-Type': 'image/png' })
            res.end(STUB_PNG)
            return
        }
        res.writeHead(404).end('not found')
    })
    return new Promise((resolve) => server.listen(port, '127.0.0.1', () => resolve(server)))
}

function start(port, env = {}) {
    const child = spawn(process.execPath, [SERVER], {
        env: { ...process.env, PORT: String(port), RENDER_TOKEN: TOKEN, ...env },
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

const stub = await startImageStub(STUB_PORT)
const { child } = start(8795, { API_BASE_URL: API_BASE })
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

    // 4. Scene image srcs are allowlisted: anything outside data: URLs and
    //    /web/image paths under the API base is refused with 400 naming the
    //    layer, before any outbound fetch.
    {
        const mkImageScene = (src, layerName, objects) => ({
            version: '6.9.1',
            objects: objects || [
                {
                    type: 'image',
                    _layerName: layerName,
                    src,
                    left: 0,
                    top: 0,
                    width: 4,
                    height: 4,
                },
            ],
            background: '#ffffff',
        })
        const post = (scene) =>
            fetch('http://127.0.0.1:8795/render', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${TOKEN}`,
                },
                body: JSON.stringify({
                    scene_json: scene,
                    width: 640,
                    height: 120,
                    format: 'svg',
                }),
            })

        for (const [src, label] of [
            ['http://127.0.0.1/x.png', 'localhost URL'],
            ['file:///etc/passwd', 'file URL'],
            ['https://evil.example/x.png', 'foreign host'],
        ]) {
            const res = await post(mkImageScene(src, 'Hero'))
            assert.equal(
                res.status,
                400,
                `${label} src must be refused, got ${res.status}: ${await res.text()}`
            )
            const body = await res.json()
            assert.match(body.error, /Hero/, `error must name the layer, got: ${body.error}`)
            assert.ok(body.error.includes(src), 'error must name the offending URL')
        }
        console.log('✓ non-allowlisted image srcs refused (400), naming layer and URL')

        // A bad src inside a nested group is caught by the pre-flight walk.
        const nested = mkImageScene(null, null, [
            {
                type: 'group',
                left: 0,
                top: 0,
                objects: [
                    {
                        type: 'image',
                        _layerName: 'Badge',
                        src: 'file:///etc/passwd',
                        left: 0,
                        top: 0,
                        width: 4,
                        height: 4,
                    },
                ],
            },
        ])
        const resNested = await post(nested)
        assert.equal(resNested.status, 400, 'nested bad src must be refused')
        assert.match((await resNested.json()).error, /Badge/, 'error names the inner layer')
        console.log('✓ nested group image src refused (400), naming the inner layer')

        // Allowlisted srcs render fine: /web/image under the API base
        // (served by the stub) and a self-contained data URL.
        for (const [src, label] of [
            [`${API_BASE}/web/image/123`, '/web/image under the API base'],
            [`data:image/png;base64,${STUB_PNG.toString('base64')}`, 'data URL'],
        ]) {
            const res = await post(mkImageScene(src, 'Hero'))
            assert.equal(
                res.status,
                200,
                `${label} must render, got ${res.status}: ${await res.text()}`
            )
        }
        console.log('✓ /web/image under API base and data URLs render (200)')
    }

    // 5. Dimension caps: integers 16..8192, pixel product at most 67108864.
    {
        const post = (width, height) =>
            fetch('http://127.0.0.1:8795/render', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${TOKEN}`,
                },
                body: JSON.stringify({
                    scene_json: SVG_SCENE,
                    width,
                    height,
                    format: 'svg',
                }),
            })
        for (const [w, h] of [
            [20000, 20000],
            [8192, 8193],
        ]) {
            const res = await post(w, h)
            assert.equal(res.status, 400, `${w}x${h} must be refused, got ${res.status}`)
            const body = await res.json()
            assert.match(body.error, /8192|67108864/, 'error names the violated limit')
        }
        const ok = await post(1200, 630)
        assert.equal(
            ok.status,
            200,
            `1200x630 must render, got ${ok.status}: ${await ok.text()}`
        )
        console.log('✓ dimension caps enforced (400 above limits, 1200x630 renders)')
    }
} finally {
    child.kill()
    stub.close()
}

console.log('\nALL security TESTS PASSED')
