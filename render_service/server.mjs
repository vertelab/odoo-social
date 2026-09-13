// render_service/server.mjs
// Server-side renderer for social.image.template (Odoo social_marketing).
//
// Port of the proven render-node pattern (Fabric + node-canvas) used by
// render-engine, adapted for Odoo image templates. The fabric-free scene
// transformation lives in render_core.mjs (unit-testable); this file owns
// the HTTP surface and the actual Fabric rendering.
//
// Security: binding values are injected as *text only*. For SVG output the
// substituted text is XML-escaped so values can never inject markup into
// the produced SVG (PNG output is raster and inherently inert).

import express from 'express'

import * as fabric from 'fabric/node'
import { applyBindingsToScene } from './render_core.mjs'

const app = express()
// MAX_BODY_MB is a plain number (e.g. "8") from env; express expects a
// byte-string like "8mb" — a bare "8" would be parsed as 8 BYTES and
// reject every real payload with 413.
const maxBodyMb = Number(process.env.MAX_BODY_MB || 8) || 8
app.use(express.json({ limit: `${maxBodyMb}mb` }))

const TOKEN = process.env.RENDER_TOKEN || ''
// Where to resolve relative /web/image/... paths from. The render container
// must be able to reach the Odoo instance (docker network name or host).
const API_BASE = process.env.API_BASE_URL || 'http://odoo:8069'

// An empty token used to mean "no auth configured, allow everything". That is
// the wrong failure mode for a service that renders whatever it is given:
// if the token is ever missing -- a stale process, a bad EnvironmentFile, a
// unit that was never restarted -- the service silently becomes an open
// renderer instead of refusing. It also makes a misconfigured deployment
// indistinguishable from a correct one, because every request succeeds.
//
// Set RENDER_ALLOW_NO_AUTH=1 to opt back in for local development.
const ALLOW_NO_AUTH = process.env.RENDER_ALLOW_NO_AUTH === '1'

if (!TOKEN && !ALLOW_NO_AUTH) {
    console.error(
        'render-odoo: RENDER_TOKEN is empty or unset. Refusing to start. ' +
            'Set RENDER_TOKEN, or set RENDER_ALLOW_NO_AUTH=1 for local development.'
    )
    process.exit(1)
}

function requireAuth(req, res, next) {
    if (!TOKEN) {
        return next() // explicitly opted in via RENDER_ALLOW_NO_AUTH=1
    }
    const header = req.headers.authorization || ''
    if (header === `Bearer ${TOKEN}`) {
        return next()
    }
    return res.status(401).json({ error: 'unauthorized' })
}

app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'render-odoo' }))

app.post('/render', requireAuth, async (req, res) => {
    try {
        const { scene_json, width, height, bindings = {}, format = 'png' } = req.body || {}
        if (!scene_json || !width || !height) {
            return res.status(400).json({ error: 'scene_json, width, height required' })
        }
        if (!['png', 'svg'].includes(format)) {
            return res.status(400).json({ error: 'format must be png or svg' })
        }

        const wantSvg = format === 'svg'
        const json = applyBindingsToScene(scene_json, bindings, {
            escapeXml: wantSvg,
            apiBase: API_BASE,
        })

        const canvas = new fabric.StaticCanvas(null, {
            width,
            height,
            backgroundColor: json.background || '#ffffff',
        })
        await canvas.loadFromJSON(json)
        canvas.renderAll()

        if (wantSvg) {
            // Fabric's toSVG builds an XML string; in node this does not
            // require a real canvas backing (pure serialization).
            const svg = canvas.toSVG()
            return res.type('image/svg+xml').send(svg)
        }

        const nodeCanvas =
            (typeof canvas.getNodeCanvas === 'function' && canvas.getNodeCanvas()) ||
            canvas.lowerCanvasEl ||
            canvas._canvas ||
            canvas.elements?.lower?.el
        if (!nodeCanvas || typeof nodeCanvas.toBuffer !== 'function') {
            const dataUrl = canvas.toDataURL({ format: 'png' })
            const base64 = dataUrl.split(',')[1] || ''
            return res.type('image/png').send(Buffer.from(base64, 'base64'))
        }
        const buf = nodeCanvas.toBuffer('image/png')
        return res.type('image/png').send(buf)
    } catch (err) {
        console.error('render error', err)
        return res.status(500).json({ error: err.message })
    }
})

const PORT = process.env.PORT || 8600
app.listen(PORT, '0.0.0.0', () => {
    console.log(`render-odoo listening on :${PORT}`)
})
