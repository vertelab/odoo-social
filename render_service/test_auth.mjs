// Test for the auth behaviour of server.mjs.
//
// This exists because the previous behaviour was the wrong way round: an empty
// RENDER_TOKEN, which is what a stale process or a bad EnvironmentFile
// produces, meant "allow everything". The service became an open renderer and
// every check still passed, because every request succeeded.
//
// The service is started as a real child process on a free port. That is
// slower than stubbing, but the failure we are guarding against is precisely
// a startup/environment one, and it cannot be observed without starting it.
import assert from 'node:assert'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const here = dirname(fileURLToPath(import.meta.url))
const SERVER = join(here, 'server.mjs')
const TOKEN = 'deadbeef'.repeat(8)
const BODY = {
    scene_json: { version: '5.3.0', objects: [] },
    width: 64,
    height: 64,
    format: 'png',
}

function start(env, port) {
    const child = spawn(process.execPath, [SERVER], {
        env: { ...process.env, PORT: String(port), ...env },
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

// 1. An empty token must stop the process, not open the service.
{
    const { child, output } = start({ RENDER_TOKEN: '' }, 8791)
    const code = await new Promise((resolve) => child.on('exit', resolve))
    assert.equal(code, 1, `expected exit 1 with an empty token, got ${code}`)
    assert.match(output(), /RENDER_TOKEN is empty or unset/)
    assert.match(output(), /RENDER_ALLOW_NO_AUTH=1/, 'must name the escape hatch')
    console.log('✓ empty RENDER_TOKEN refuses to start (exit 1)')
}

// 2. RENDER_ALLOW_NO_AUTH=1 is the explicit opt-in and lets it run.
{
    const { child } = start({ RENDER_TOKEN: '', RENDER_ALLOW_NO_AUTH: '1' }, 8792)
    try {
        assert.ok(await waitForPort(8792), 'should start when explicitly allowed')
        const res = await fetch('http://127.0.0.1:8792/render', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(BODY),
        })
        assert.equal(res.status, 200, 'opt-in mode allows unauthenticated renders')
        console.log('✓ RENDER_ALLOW_NO_AUTH=1 opts back in (documented dev path)')
    } finally {
        child.kill()
    }
}

// 3. With a token: correct accepted, wrong and missing rejected.
{
    const { child } = start({ RENDER_TOKEN: TOKEN }, 8793)
    try {
        assert.ok(await waitForPort(8793), 'should start with a token')

        const ok = await fetch('http://127.0.0.1:8793/render', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${TOKEN}`,
            },
            body: JSON.stringify(BODY),
        })
        assert.equal(ok.status, 200, 'correct token must be accepted')
        assert.equal(ok.headers.get('content-type'), 'image/png')
        const png = Buffer.from(await ok.arrayBuffer())
        assert.ok(png.length > 0, 'render must return bytes')
        console.log('✓ correct token accepted (200, image/png, %d bytes)', png.length)

        for (const header of [`Bearer wrong`, undefined]) {
            const res = await fetch('http://127.0.0.1:8793/render', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(header ? { Authorization: header } : {}),
                },
                body: JSON.stringify(BODY),
            })
            assert.equal(
                res.status,
                401,
                `${header || 'no header'} must be rejected with 401, got ${res.status}`
            )
        }
        console.log('✓ wrong token and missing header both rejected (401)')
    } finally {
        child.kill()
    }
}

// 4. /health stays open: it is what the state and the deploy script poll.
{
    const { child } = start({ RENDER_TOKEN: TOKEN }, 8794)
    try {
        assert.ok(await waitForPort(8794))
        const res = await fetch('http://127.0.0.1:8794/health')
        assert.equal(res.status, 200)
        assert.equal((await res.json()).status, 'ok')
        console.log('✓ /health requires no auth')
    } finally {
        child.kill()
    }
}

console.log('\nALL server auth TESTS PASSED')
