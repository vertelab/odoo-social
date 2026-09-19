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
import { registerFont } from 'canvas'

import * as fabric from 'fabric/node'
import {
    applyBindingsToScene,
    computeCoverFit,
    RequiredBindingError,
} from './render_core.mjs'
import { listRegisteredFonts, registerFontsInDir } from './fonts.mjs'

const app = express()
// MAX_BODY_MB is a plain number (e.g. "8") from env; express expects a
// byte-string like "8mb"; a bare "8" would be parsed as 8 BYTES and
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

// Brand fonts for parity with the editor (design D6). The file basename
// (without extension) is the family name; see fonts/README.md.
const FONTS_DIR = process.env.FONTS_DIR || new URL('./fonts', import.meta.url).pathname

async function loadFonts() {
    const result = await registerFontsInDir(FONTS_DIR, registerFont)
    for (const skip of result.skipped) {
        console.error(`render-odoo: could not register font ${skip.file}: ${skip.error}`)
    }
    if (result.registered.length > 0) {
        console.log(
            `render-odoo: registered ${result.registered.length} font(s): ` +
                result.registered.map((f) => f.family).join(', ')
        )
    }
    return result
}

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

app.get('/health', (_req, res) =>
    res.json({
        status: 'ok',
        service: 'render-odoo',
        fonts_registered: listRegisteredFonts().length,
    })
)

app.get('/fonts', requireAuth, (_req, res) => res.json({ fonts: listRegisteredFonts() }))

app.post('/fonts/reload', requireAuth, async (_req, res) => {
    const result = await loadFonts()
    res.json({
        registered: result.registered.map((f) => f.family),
        skipped: result.skipped,
    })
})

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
        // Låt INTE applyBindingsToScene XML-escapra åt oss.
        //
        // canvas.toSVG() escaprar redan texten när den serialiserar till XML.
        // Att escapra dessförinnan gav dubbel escaping: '&' blev '&amp;amp;'
        // och '<' blev '&amp;lt;', alltså bokstavliga '&amp;' och '&lt;' för
        // den som öppnar SVG:n. Raster-vägen påverkas inte: den läser samma
        // text utan serialisering.
        //
        // Escaping sker därför på exakt ett ställe: i Fabric.
        const fitTargets = new Map()
        const json = applyBindingsToScene(scene_json, bindings, {
            escapeXml: false,
            apiBase: API_BASE,
            fitTargets,
        })

        const canvas = new fabric.StaticCanvas(null, {
            width,
            height,
            backgroundColor: json.background || '#ffffff',
        })
        await canvas.loadFromJSON(json)

        // Apply object-fit:cover to data-bound images now that Fabric has
        // loaded them. Width/height after load are the NEW image's natural
        // dimensions in source pixels. We scale to cover and crop to the
        // pre-swap frame captured in applyBindingsToScene: with a pre-
        // existing clipPath (image-fill shape) its scale is compensated by
        // the inverse host-scale ratio; without one a fresh frame-sized
        // rect clip exposes only the frame window. Ported from
        // render-engine-os render/server.mjs.
        if (fitTargets.size > 0) {
            for (const obj of canvas.getObjects()) {
                if (!obj || !obj.id) continue
                const fit = fitTargets.get(obj.id)
                if (!fit) continue
                const naturalW = obj.width
                const naturalH = obj.height
                if (!naturalW || !naturalH) continue
                const { frameW, frameH, oldHostScaleX, oldHostScaleY, hadClipPath } = fit
                const f = computeCoverFit(
                    naturalW,
                    naturalH,
                    frameW,
                    frameH,
                    oldHostScaleX,
                    oldHostScaleY
                )
                obj.set({ scaleX: f.scale, scaleY: f.scale })
                if (hadClipPath && obj.clipPath) {
                    obj.clipPath.scaleX = (obj.clipPath.scaleX || 1) * f.clipScaleX
                    obj.clipPath.scaleY = (obj.clipPath.scaleY || 1) * f.clipScaleY
                } else {
                    // Plain data-bound image (no shape mask): replace any
                    // clipPath with a fresh frame-sized rect. A pre-existing
                    // clipPath was tuned for the original media's aspect and
                    // would shrink/expand the visible window incorrectly for
                    // the new image.
                    obj.clipPath = new fabric.Rect({
                        width: frameW / f.scale,
                        height: frameH / f.scale,
                        originX: 'center',
                        originY: 'center',
                    })
                }
                obj.setCoords?.()
            }
        }

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
        if (err instanceof RequiredBindingError) {
            // A layer marked _required resolved to empty: the caller (Odoo)
            // surfaces this to the user, naming the layer.
            return res.status(400).json({ error: err.message })
        }
        console.error('render error', err)
        return res.status(500).json({ error: err.message })
    }
})

const PORT = process.env.PORT || 8600
loadFonts()
    .catch((err) => console.error('render-odoo: initial font registration failed', err))
    .finally(() => {
        app.listen(PORT, '0.0.0.0', () => {
            console.log(`render-odoo listening on :${PORT}`)
        })
    })
