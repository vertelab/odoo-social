// render_service/dynamic_groups.mjs
// Fabric-side regeneration of chart and QR layers (design D3/D5). Imported
// ONLY by server.mjs: it needs a live `fabric` namespace and a canvas, so it
// stays out of every pure test. All data logic lives in the pure modules
// chart_spec.mjs / qr_matrix.mjs; this file only converts their output into
// fabric objects and swaps them into the scene.
//
// Regeneration runs after applyBindingsToScene (render_core.mjs) has
// substituted {{tokens}} in _chartSpec cells and _qrContent, so the rebuilt
// geometry always reflects the record being rendered. Everything here is
// deterministic: the same scene JSON produces the same canvas.

import { chartSpecToSvg, CHART_SPEC_PROP } from './chart_spec.mjs'
import { qrContentToMatrix, qrMatrixToRectSpecs, QR_PROP } from './qr_matrix.mjs'

const DEFAULT_QR_COLOR = '#000000'

// Recursively collect objects carrying a chart spec or QR content. Chart
// and QR elements are fabric groups, but the props can sit at any depth
// once the user groups elements together.
function collectTargets(container, acc = []) {
    const objects =
        container && typeof container.getObjects === 'function'
            ? container.getObjects()
            : []
    for (const obj of objects) {
        if (!obj) continue
        if (obj[CHART_SPEC_PROP] || typeof obj[QR_PROP] === 'string') {
            acc.push(obj)
        }
        if (typeof obj.getObjects === 'function') {
            collectTargets(obj, acc)
        }
    }
    return acc
}

// True while `obj` is still reachable from the canvas (a previously
// replaced ancestor would leave it detached).
function isAttached(obj, canvas) {
    let cur = obj
    while (cur) {
        if (cur === canvas) return true
        cur = cur.group || null
    }
    return false
}

// Copy the placement transform from the old layer so the regenerated one
// sits exactly where the editor put it. Natural size is preserved because
// the spec options (width/height or module count) do not change with data:
// token substitution only rewrites cell values, never structure.
function copyPlacement(src, dst) {
    dst.set({
        left: src.left,
        top: src.top,
        scaleX: src.scaleX ?? 1,
        scaleY: src.scaleY ?? 1,
        angle: src.angle ?? 0,
        flipX: !!src.flipX,
        flipY: !!src.flipY,
        originX: src.originX || 'left',
        originY: src.originY || 'top',
        opacity: src.opacity ?? 1,
        visible: src.visible !== false,
    })
    if (src.selectable === false) dst.selectable = false
    if (src.evented === false) dst.evented = false
    if (src._layerName) dst._layerName = src._layerName
    dst.setCoords?.()
}

// Insert `replacement` where `oldObj` sat in its container, preserving
// z-order. Fabric 6 containers take insertAt(index, objects[]); the add()
// fallback keeps this alive if that signature ever shifts.
function replaceInContainer(container, oldObj, replacement) {
    const siblings = container.getObjects()
    const index = Math.max(0, siblings.indexOf(oldObj))
    container.remove(oldObj)
    if (typeof container.insertAt === 'function') {
        container.insertAt(index, [replacement])
    } else {
        container.add(replacement)
    }
}

async function buildChartGroup(fabric, spec) {
    const svg = chartSpecToSvg(spec)
    const loaded = await fabric.loadSVGFromString(svg)
    const objects = (loaded.objects || []).filter(Boolean)
    let group = fabric.groupSVGElements(objects, loaded.options || {})
    // groupSVGElements may return a bare object when the SVG holds a single
    // element; the chart SVG never does, but wrap defensively.
    if (!group || group.type !== 'group') {
        group = new fabric.Group(group ? [group] : [])
    }
    return group
}

function buildQrGroup(fabric, content, oldGroup) {
    const matrix = qrContentToMatrix(content)
    // Derive module size and color from the layer being replaced: the old
    // natural width is modules * moduleSize, and the previous generation's
    // first rect carries the foreground color chosen in the editor.
    const modules = matrix.length
    const oldW = oldGroup.width || modules
    const moduleSize = oldW > 0 ? oldW / modules : 4
    let color = DEFAULT_QR_COLOR
    const firstChild =
        typeof oldGroup.getObjects === 'function' ? oldGroup.getObjects()[0] : null
    if (firstChild && typeof firstChild.fill === 'string' && firstChild.fill) {
        color = firstChild.fill
    }
    const specs = qrMatrixToRectSpecs(matrix, moduleSize, color)
    const rects = specs.map(
        (s) =>
            new fabric.Rect({
                left: s.left,
                top: s.top,
                width: s.size,
                height: s.size,
                fill: s.fill,
            })
    )
    return new fabric.Group(rects)
}

/**
 * Regenerate every chart (_chartSpec) and QR (_qrContent) layer on the
 * canvas in place. Idempotent: regeneration from the same resolved spec
 * produces the same group, and the custom prop is carried over to the new
 * group so a second pass converges rather than drifting.
 *
 * A QR whose resolved content cannot be encoded (empty record value) hides
 * the layer instead of aborting the render; a chart spec that fails to
 * generate is a scene authoring bug and propagates.
 */
export async function regenerateDynamicGroups(fabric, canvas) {
    const targets = collectTargets(canvas)
    // Deepest first: a nested element regenerates before an ancestor that
    // would replace it wholesale; detached leftovers are then skipped.
    targets.sort((a, b) => depth(a) - depth(b))
    for (const target of targets) {
        if (!isAttached(target, canvas)) continue
        const container = target.group || canvas
        let replacement = null
        let prop = null
        let value = null
        if (target[CHART_SPEC_PROP]) {
            prop = CHART_SPEC_PROP
            value = target[CHART_SPEC_PROP]
            replacement = await buildChartGroup(fabric, value)
        } else if (typeof target[QR_PROP] === 'string') {
            prop = QR_PROP
            value = target[QR_PROP]
            try {
                replacement = buildQrGroup(fabric, value, target)
            } catch (err) {
                // Bound content resolved to something unencodable: hide the
                // layer rather than failing the whole render.
                target.visible = false
                target.opacity = 0
                console.error(`render-odoo: QR regeneration failed, layer hidden: ${err.message}`)
                continue
            }
        }
        if (!replacement) continue
        replacement[prop] = value
        copyPlacement(target, replacement)
        replaceInContainer(container, target, replacement)
        replacement.setCoords?.()
    }
    canvas.requestRenderAll?.()
}

function depth(obj) {
    let d = 0
    let cur = obj.group
    while (cur) {
        d += 1
        cur = cur.group
    }
    return d
}
