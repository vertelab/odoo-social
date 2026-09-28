/** @odoo-module **/

// Editor copy of render_service/chart_spec.mjs (design D3 in
// openspec/changes/editor-grid-dynamic-elements). scripts/check_chart_sync.py
// fails the build on any functional drift between this file and the
// render-side original, so the code below is a VERBATIM copy except for the
// import line: the service module imports substituteText/xmlEscape from
// ./render_core.mjs, which is not part of the web assets, so this copy
// carries the two helpers inline. Both are byte-identical copies from
// render_service/render_core.mjs (substituteText mirrors the editor utils'
// resolveTokens behavior exactly), keeping this module dependency-free for
// the browser AND directly importable by the node parity check.
//
// THE ONLY DIFFERENCE from render_service/chart_spec.mjs is:
//   - the header comment above
//   - the import line replaced by the two inline helpers below
// Everything from `export const CHART_SPEC_PROP` onward is byte-identical.

const TOKEN_RE = /\{\{\s*([a-zA-Z0-9_.-]+)\s*((?:\|[^}|]+)*)\}\}/g

export function xmlEscape(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&apos;')
}

export function substituteText(text, bindings) {
    return String(text ?? '').replace(TOKEN_RE, (match, name, pipes) => {
        if (!Object.prototype.hasOwnProperty.call(bindings, name)) {
            return match
        }
        let v = String(bindings[name] ?? '')
        if (pipes) {
            for (const p of pipes.split('|').filter(Boolean)) {
                v = applyPipeTransform(v, p.trim())
            }
        }
        return v
    })
}

function applyPipeTransform(value, pipe) {
    if (!pipe) return value
    switch (pipe) {
        case 'lower':
        case 'lowercase':
            return value.toLowerCase()
        case 'upper':
        case 'uppercase':
            return value.toUpperCase()
        case 'title':
            return value
                .replace(/\b\p{L}/gu, (c) => c.toUpperCase())
                .replace(/\B\p{L}+/gu, (m) => m.toLowerCase())
        case 'trim':
            return value.trim()
        case 'capitalize':
            return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase()
        default:
            return value
    }
}

// Custom property carrying the chart spec on a fabric group (design D6).
export const CHART_SPEC_PROP = '_chartSpec'

// Default palette, used when options.colors is missing or not an array.
export const DEFAULT_CHART_COLORS = [
    '#2f6fb2',
    '#d95f43',
    '#55a05a',
    '#e0a030',
    '#7a5ba6',
    '#4fb3b3',
]

const SVG_NS = 'http://www.w3.org/2000/svg'

// Fallback canvas size when options.width / options.height are missing.
const DEFAULT_WIDTH = 480
const DEFAULT_HEIGHT = 320
const MIN_SIZE = 64

// Number of value gridlines above the baseline (spec: "4 steps").
const GRID_STEPS = 4

// Axis, grid and label styling. Fixed values keep the output deterministic.
const COLOR_TEXT = '#333333'
const COLOR_AXIS = '#444444'
const COLOR_GRID = '#e0e0e0'
const FONT_FAMILY = 'sans-serif'
const FONT_SIZE_LABEL = 11
const FONT_SIZE_TITLE = 13
const LEGEND_ROW_H = 18
const LEGEND_SWATCH = 8
// Rough per-character width for legend layout math (no text measuring here).
const LEGEND_CHAR_W = 6

const CHART_TYPES = new Set(['bar-v', 'bar-h', 'line', 'area', 'pie', 'donut'])

// Coerce one data cell to a finite, non-negative number. Non-numeric input
// maps to 0 per the data-binding spec: the render never aborts on bad data.
export function coerceChartValue(value) {
    const n = Number(value)
    if (!Number.isFinite(n) || n < 0) return 0
    return n
}

// Format a coordinate for SVG output: at most 2 decimals, no trailing zeros,
// so identical input always produces identical markup.
function fmt(n) {
    return String(Number(Number(n).toFixed(2)))
}

// Round a positive scale maximum up to a 1/2/5 * 10^n step so gridline
// labels stay legible. Deterministic; NaN/0/negative fall back to 1.
export function niceCeil(value) {
    const v = Number(value)
    if (!Number.isFinite(v) || v <= 0) return 1
    const exp = Math.floor(Math.log10(v))
    const f = v / 10 ** exp
    const nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10
    return nf * 10 ** exp
}

function resolveColors(spec) {
    const colors = spec && spec.options && spec.options.colors
    if (Array.isArray(colors) && colors.length > 0) {
        return colors.map((c) => String(c))
    }
    return DEFAULT_CHART_COLORS.slice()
}

function resolveSize(spec) {
    const opts = (spec && spec.options) || {}
    const w = Math.max(MIN_SIZE, Number(opts.width) || DEFAULT_WIDTH)
    const h = Math.max(MIN_SIZE, Number(opts.height) || DEFAULT_HEIGHT)
    return { width: w, height: h }
}

function validateSpec(spec) {
    if (!spec || typeof spec !== 'object') {
        throw new Error('chartSpecToSvg: spec must be an object')
    }
    if (spec.version !== undefined && spec.version !== 1) {
        throw new Error(
            `chartSpecToSvg: unsupported spec version ${JSON.stringify(spec.version)}, expected 1`
        )
    }
    if (!CHART_TYPES.has(spec.type)) {
        throw new Error(
            `chartSpecToSvg: unsupported chart type ${JSON.stringify(spec.type)}`
        )
    }
}

// Highest plotted value across all series (clamped at 0), for the scale.
function maxValue(spec) {
    let max = 0
    for (const s of spec.series || []) {
        for (const v of s.values || []) {
            const n = coerceChartValue(v)
            if (n > max) max = n
        }
    }
    return max
}

function svgOpen(width, height) {
    return (
        `<svg xmlns="${SVG_NS}" width="${fmt(width)}" height="${fmt(height)}" ` +
        `viewBox="0 0 ${fmt(width)} ${fmt(height)}">`
    )
}

function titleNode(spec, width) {
    if (!spec.title) return ''
    const y = FONT_SIZE_TITLE + 6
    return (
        `<text class="chart-title" x="${fmt(width / 2)}" y="${y}" ` +
        `text-anchor="middle" font-family="${FONT_FAMILY}" ` +
        `font-size="${FONT_SIZE_TITLE}" fill="${COLOR_TEXT}">` +
        `${xmlEscape(spec.title)}</text>`
    )
}

// One legend row per entry: swatch + escaped label, centered as a block.
function legendNodes(entries, width, yStart, swatch) {
    const widths = entries.map(
        (e) => LEGEND_SWATCH + 4 + String(e.label).length * LEGEND_CHAR_W + 16
    )
    const total = widths.reduce((a, b) => a + b, 0) - 16
    let x = (width - total) / 2
    const out = []
    entries.forEach((e, i) => {
        const y = yStart + i * LEGEND_ROW_H
        if (swatch === 'rect') {
            out.push(
                `<rect class="legend-swatch" x="${fmt(x)}" y="${fmt(y)}" ` +
                    `width="${LEGEND_SWATCH}" height="${LEGEND_SWATCH}" fill="${e.color}"/>`
            )
        } else {
            const cy = y + LEGEND_SWATCH / 2
            out.push(
                `<circle class="legend-swatch" cx="${fmt(x + LEGEND_SWATCH / 2)}" ` +
                    `cy="${fmt(cy)}" r="${LEGEND_SWATCH / 2}" fill="${e.color}"/>`
            )
        }
        out.push(
            `<text class="legend-label" x="${fmt(x + LEGEND_SWATCH + 4)}" ` +
                `y="${fmt(y + LEGEND_SWATCH)}" font-family="${FONT_FAMILY}" ` +
                `font-size="${FONT_SIZE_LABEL}" fill="${COLOR_TEXT}">` +
                `${xmlEscape(e.label)}</text>`
        )
        x += widths[i]
    })
    return out.join('')
}

// Shared frame for the cartesian types: margins, scale, 4 gridlines with
// value labels, baseline axes and category labels.
function cartesianFrame(spec, width, height, titleH, legendH, verticalBars) {
    const plotLeft = 46
    const plotRight = width - 12
    const plotTop = 10 + titleH + legendH
    const plotBottom = height - 30
    const plotW = Math.max(1, plotRight - plotLeft)
    const plotH = Math.max(1, plotBottom - plotTop)
    const scaleMax = niceCeil(maxValue(spec))
    const categories = Array.isArray(spec.categories) ? spec.categories : []
    const yOf = (v) => plotBottom - (coerceChartValue(v) / scaleMax) * plotH

    const parts = []
    // Horizontal gridlines and value labels belong to the vertical-bar
    // value axis; bar-h redraws them vertically in its own renderer.
    if (verticalBars) {
        for (let i = 1; i <= GRID_STEPS; i += 1) {
            const gv = (scaleMax * i) / GRID_STEPS
            const gy = yOf(gv)
            parts.push(
                `<line class="grid" x1="${fmt(plotLeft)}" y1="${fmt(gy)}" ` +
                    `x2="${fmt(plotRight)}" y2="${fmt(gy)}" stroke="${COLOR_GRID}"/>`
            )
        }
        for (let i = 0; i <= GRID_STEPS; i += 1) {
            const gv = (scaleMax * i) / GRID_STEPS
            const gy = yOf(gv)
            parts.push(
                `<text class="value-label" x="${fmt(plotLeft - 5)}" y="${fmt(gy + 3)}" ` +
                    `text-anchor="end" font-family="${FONT_FAMILY}" ` +
                    `font-size="${FONT_SIZE_LABEL}" fill="${COLOR_TEXT}">${fmt(gv)}</text>`
            )
        }
    }
    // Baseline axes.
    parts.push(
        `<line class="axis" x1="${fmt(plotLeft)}" y1="${fmt(plotBottom)}" ` +
            `x2="${fmt(plotRight)}" y2="${fmt(plotBottom)}" stroke="${COLOR_AXIS}"/>`
    )
    parts.push(
        `<line class="axis" x1="${fmt(plotLeft)}" y1="${fmt(plotTop)}" ` +
            `x2="${fmt(plotLeft)}" y2="${fmt(plotBottom)}" stroke="${COLOR_AXIS}"/>`
    )

    const slotW = plotW / Math.max(1, categories.length)
    categories.forEach((cat, i) => {
        if (verticalBars) {
            parts.push(
                `<text class="cat-label" x="${fmt(plotLeft + slotW * (i + 0.5))}" ` +
                    `y="${fmt(plotBottom + 15)}" text-anchor="middle" ` +
                    `font-family="${FONT_FAMILY}" font-size="${FONT_SIZE_LABEL}" ` +
                    `fill="${COLOR_TEXT}">${xmlEscape(cat)}</text>`
            )
        } else {
            const slotH = plotH / Math.max(1, categories.length)
            parts.push(
                `<text class="cat-label" x="${fmt(plotLeft - 6)}" ` +
                    `y="${fmt(plotTop + slotH * (i + 0.5) + 4)}" text-anchor="end" ` +
                    `font-family="${FONT_FAMILY}" font-size="${FONT_SIZE_LABEL}" ` +
                    `fill="${COLOR_TEXT}">${xmlEscape(cat)}</text>`
            )
        }
    })

    return {
        plotLeft,
        plotTop,
        plotRight,
        plotBottom,
        plotW,
        plotH,
        scaleMax,
        yOf,
        slotW,
        frame: parts,
    }
}

function seriesLegendEntries(spec, colors) {
    return (spec.series || []).map((s, i) => ({
        label: s.name ?? `Serie ${i + 1}`,
        color: colors[i % colors.length],
    }))
}

function renderBarV(spec, width, height, titleH, legendH, colors) {
    const frame = cartesianFrame(spec, width, height, titleH, legendH, true)
    const series = spec.series || []
    const nSeries = Math.max(1, series.length)
    const categories = Array.isArray(spec.categories) ? spec.categories : []
    const inner = frame.slotW * 0.15
    const barW = (frame.slotW - 2 * inner) / nSeries
    const parts = [frame.frame.join('')]
    categories.forEach((_cat, i) => {
        series.forEach((s, j) => {
            const v = coerceChartValue((s.values || [])[i])
            const h = (v / frame.scaleMax) * frame.plotH
            const x = frame.plotLeft + frame.slotW * i + inner + barW * j + barW * 0.05
            const y = frame.plotBottom - h
            parts.push(
                `<rect class="bar" x="${fmt(x)}" y="${fmt(y)}" ` +
                    `width="${fmt(barW * 0.9)}" height="${fmt(h)}" ` +
                    `fill="${colors[j % colors.length]}"/>`
            )
        })
    })
    return parts.join('')
}

function renderBarH(spec, width, height, titleH, legendH, colors) {
    const frame = cartesianFrame(spec, width, height, titleH, legendH, false)
    const series = spec.series || []
    const nSeries = Math.max(1, series.length)
    const categories = Array.isArray(spec.categories) ? spec.categories : []
    const slotH = frame.plotH / Math.max(1, categories.length)
    const inner = slotH * 0.15
    const barH = (slotH - 2 * inner) / nSeries
    const parts = [frame.frame.join('')]
    // Value gridlines run vertically for horizontal bars.
    const gridV = []
    for (let i = 1; i <= GRID_STEPS; i += 1) {
        const gv = (frame.scaleMax * i) / GRID_STEPS
        const gx = frame.plotLeft + (gv / frame.scaleMax) * frame.plotW
        gridV.push(
            `<line class="grid" x1="${fmt(gx)}" y1="${fmt(frame.plotTop)}" ` +
                `x2="${fmt(gx)}" y2="${fmt(frame.plotBottom)}" stroke="${COLOR_GRID}"/>`
        )
    }
    for (let i = 0; i <= GRID_STEPS; i += 1) {
        const gv = (frame.scaleMax * i) / GRID_STEPS
        const gx = frame.plotLeft + (gv / frame.scaleMax) * frame.plotW
        gridV.push(
            `<text class="value-label" x="${fmt(gx)}" y="${fmt(frame.plotBottom + 15)}" ` +
                `text-anchor="middle" font-family="${FONT_FAMILY}" ` +
                `font-size="${FONT_SIZE_LABEL}" fill="${COLOR_TEXT}">${fmt(gv)}</text>`
        )
    }
    parts.push(gridV.join(''))
    categories.forEach((_cat, i) => {
        series.forEach((s, j) => {
            const v = coerceChartValue((s.values || [])[i])
            const w = (v / frame.scaleMax) * frame.plotW
            const y = frame.plotTop + slotH * i + inner + barH * j + barH * 0.05
            parts.push(
                `<rect class="bar" x="${fmt(frame.plotLeft)}" y="${fmt(y)}" ` +
                    `width="${fmt(w)}" height="${fmt(barH * 0.9)}" ` +
                    `fill="${colors[j % colors.length]}"/>`
            )
        })
    })
    return parts.join('')
}

function renderLineOrArea(spec, width, height, titleH, legendH, colors, area) {
    const frame = cartesianFrame(spec, width, height, titleH, legendH, true)
    const categories = Array.isArray(spec.categories) ? spec.categories : []
    const parts = [frame.frame.join('')]
    for (const [j, s] of (spec.series || []).entries()) {
        const color = colors[j % colors.length]
        const pts = categories.map((_c, i) => {
            const v = coerceChartValue((s.values || [])[i])
            const x = frame.plotLeft + frame.slotW * (i + 0.5)
            const y = frame.yOf(v)
            return { x, y }
        })
        if (pts.length === 0) continue
        if (area) {
            const d =
                `M ${fmt(pts[0].x)} ${fmt(frame.plotBottom)} ` +
                pts.map((p) => `L ${fmt(p.x)} ${fmt(p.y)}`).join(' ') +
                ` L ${fmt(pts[pts.length - 1].x)} ${fmt(frame.plotBottom)} Z`
            parts.push(
                `<path class="area" d="${d}" fill="${color}" fill-opacity="0.35" ` +
                    `stroke="${color}" stroke-width="2"/>`
            )
        } else {
            const points = pts.map((p) => `${fmt(p.x)},${fmt(p.y)}`).join(' ')
            parts.push(
                `<polyline class="line" points="${points}" fill="none" ` +
                    `stroke="${color}" stroke-width="2"/>`
            )
        }
        for (const p of pts) {
            parts.push(
                `<circle class="point" cx="${fmt(p.x)}" cy="${fmt(p.y)}" r="3" fill="${color}"/>`
            )
        }
    }
    return parts.join('')
}

function renderPieOrDonut(spec, width, height, titleH, legendH, colors, donut) {
    const categories = Array.isArray(spec.categories) ? spec.categories : []
    const series = (spec.series || [])[0]
    const values = categories.map((_c, i) => coerceChartValue((series?.values || [])[i]))
    const total = values.reduce((a, b) => a + b, 0)

    const legendRows = legendH / LEGEND_ROW_H
    const cy =
        titleH + (height - titleH - legendRows * LEGEND_ROW_H) / 2 + 6
    const cx = width / 2
    const r = Math.max(8, Math.min(width - cx, (height - titleH - legendH) / 2) - 6)
    const r0 = donut ? r * 0.58 : 0

    const parts = []
    if (total <= 0) {
        // No plottable data: emit a neutral placeholder disc, still valid SVG.
        parts.push(
            `<circle class="empty-chart" cx="${fmt(cx)}" cy="${fmt(cy)}" r="${fmt(r)}" ` +
                `fill="${COLOR_GRID}"/>`
        )
        return { body: parts.join(''), cy, r }
    }

    let angle = -Math.PI / 2
    const lastIndex = values.length - 1
    values.forEach((v, i) => {
        if (v <= 0) return
        const frac = v / total
        const start = angle
        // Close the final slice exactly on the start angle: no rounding gap.
        const end = i === lastIndex ? -Math.PI / 2 : start + frac * 2 * Math.PI
        angle = end
        const large = frac > 0.5 ? 1 : 0
        const x1 = cx + r * Math.cos(start)
        const y1 = cy + r * Math.sin(start)
        const x2 = cx + r * Math.cos(end)
        const y2 = cy + r * Math.sin(end)
        const color = colors[i % colors.length]
        let d
        if (donut) {
            const xi1 = cx + r0 * Math.cos(start)
            const yi1 = cy + r0 * Math.sin(start)
            const xi2 = cx + r0 * Math.cos(end)
            const yi2 = cy + r0 * Math.sin(end)
            d =
                `M ${fmt(x1)} ${fmt(y1)} ` +
                `A ${fmt(r)} ${fmt(r)} 0 ${large} 1 ${fmt(x2)} ${fmt(y2)} ` +
                `L ${fmt(xi2)} ${fmt(yi2)} ` +
                `A ${fmt(r0)} ${fmt(r0)} 0 ${large} 0 ${fmt(xi1)} ${fmt(yi1)} Z`
        } else {
            d =
                `M ${fmt(cx)} ${fmt(cy)} L ${fmt(x1)} ${fmt(y1)} ` +
                `A ${fmt(r)} ${fmt(r)} 0 ${large} 1 ${fmt(x2)} ${fmt(y2)} Z`
        }
        parts.push(`<path class="slice" d="${d}" fill="${color}"/>`)
        const mid = start + frac * Math.PI
        const rm = donut ? (r + r0) / 2 : r * 0.6
        const tx = cx + rm * Math.cos(mid)
        const ty = cy + rm * Math.sin(mid)
        parts.push(
            `<text class="pct-label" x="${fmt(tx)}" y="${fmt(ty + 3)}" ` +
                `text-anchor="middle" font-family="${FONT_FAMILY}" ` +
                `font-size="${FONT_SIZE_LABEL}" fill="#ffffff">` +
                `${Math.round(frac * 100)}%</text>`
        )
    })
    return { body: parts.join(''), cy, r }
}

/**
 * Render a chart spec to an SVG string. Deterministic for identical input.
 * Bar marks carry class "bar" and appear exactly
 * categories.length * series.length times for bar-v / bar-h; the legend and
 * grid carry their own classes so tests can count precisely.
 */
export function chartSpecToSvg(spec) {
    validateSpec(spec)
    const { width, height } = resolveSize(spec)
    const colors = resolveColors(spec)
    const categories = Array.isArray(spec.categories) ? spec.categories : []
    const isPie = spec.type === 'pie' || spec.type === 'donut'
    const legendEntries = isPie
        ? categories.map((c, i) => ({ label: c, color: colors[i % colors.length] }))
        : seriesLegendEntries(spec, colors)
    // Pie/donut always show a category legend; cartesian types show one only
    // for multiple series (a single series is obvious from the data table).
    const showLegend = isPie ? legendEntries.length > 0 : (spec.series || []).length > 1
    const legendH = showLegend ? legendEntries.length * LEGEND_ROW_H : 0
    const titleH = spec.title ? 24 : 0

    const body = (() => {
        switch (spec.type) {
            case 'bar-v':
                return renderBarV(spec, width, height, titleH, legendH, colors)
            case 'bar-h':
                return renderBarH(spec, width, height, titleH, legendH, colors)
            case 'line':
                return renderLineOrArea(spec, width, height, titleH, legendH, colors, false)
            case 'area':
                return renderLineOrArea(spec, width, height, titleH, legendH, colors, true)
            case 'pie':
                return renderPieOrDonut(spec, width, height, titleH, legendH, colors, false).body
            case 'donut':
                return renderPieOrDonut(spec, width, height, titleH, legendH, colors, true).body
            default:
                // validateSpec already rejects anything reaching this branch.
                throw new Error(`chartSpecToSvg: unsupported chart type ${JSON.stringify(spec.type)}`)
        }
    })()

    const legend = showLegend
        ? legendNodes(
              legendEntries,
              width,
              titleH + 6,
              spec.type === 'bar-v' || spec.type === 'bar-h' ? 'rect' : 'circle'
          )
        : ''

    return (
        svgOpen(width, height) +
        '<rect class="chart-bg" x="0" y="0" width="100%" height="100%" fill="#ffffff"/>' +
        titleNode(spec, width) +
        legend +
        body +
        '</svg>'
    )
}

/**
 * Return a NEW spec with every string cell of categories and series values
 * run through substituteText so {{tokens}} resolve at render time. Number
 * cells pass through untouched (chartSpecToSvg coerces them later). The
 * input spec is not mutated.
 */
export function substituteChartSpec(spec, bindings = {}) {
    if (!spec || typeof spec !== 'object') return spec
    const out = { ...spec }
    if (Array.isArray(spec.categories)) {
        out.categories = spec.categories.map((c) =>
            typeof c === 'string' ? substituteText(c, bindings) : c
        )
    }
    if (Array.isArray(spec.series)) {
        out.series = spec.series.map((s) => {
            if (!s || typeof s !== 'object') return s
            const copy = { ...s }
            if (Array.isArray(s.values)) {
                copy.values = s.values.map((v) =>
                    typeof v === 'string' ? substituteText(v, bindings) : v
                )
            }
            return copy
        })
    }
    return out
}
