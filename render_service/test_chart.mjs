// render_service/test_chart.mjs: unit tests for chart_spec.mjs and
// qr_matrix.mjs (no canvas, no fabric needed). Run: node --test test_chart.mjs
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
    chartSpecToSvg,
    CHART_SPEC_PROP,
    coerceChartValue,
    DEFAULT_CHART_COLORS,
    niceCeil,
    substituteChartSpec,
} from './chart_spec.mjs'
import {
    qrContentToMatrix,
    qrMatrixToRectSpecs,
    QR_PROP,
} from './qr_matrix.mjs'

function countOccurrences(haystack, needle) {
    return haystack.split(needle).length - 1
}

const BASE_SPEC = {
    version: 1,
    type: 'bar-v',
    title: 'Försäljning',
    categories: ['Jan', 'Feb', 'Mar'],
    series: [
        { name: 'Stolar', values: [10, 20, 30] },
        { name: 'Bord', values: [5, 15, 25] },
    ],
    options: { width: 480, height: 320 },
}

test('all six chart types produce valid SVG', () => {
    for (const type of ['bar-v', 'bar-h', 'line', 'area', 'pie', 'donut']) {
        const svg = chartSpecToSvg({ ...BASE_SPEC, type })
        assert.ok(svg.startsWith('<svg '), `${type} starts with <svg`)
        assert.ok(svg.endsWith('</svg>'), `${type} closes svg`)
        assert.ok(!svg.includes('NaN'), `${type} has no NaN coordinates`)
    }
})

test('bar-v renders one rect per category per series', () => {
    const svg = chartSpecToSvg(BASE_SPEC)
    assert.equal(countOccurrences(svg, 'class="bar"'), 3 * 2)
})

test('bar-h renders one rect per category per series', () => {
    const svg = chartSpecToSvg({ ...BASE_SPEC, type: 'bar-h' })
    assert.equal(countOccurrences(svg, 'class="bar"'), 3 * 2)
})

test('line renders one polyline per series with point markers', () => {
    const svg = chartSpecToSvg({ ...BASE_SPEC, type: 'line' })
    assert.equal(countOccurrences(svg, 'class="line"'), 2)
    assert.equal(countOccurrences(svg, 'class="point"'), 3 * 2)
    assert.ok(svg.includes('Stolar') && svg.includes('Bord'), 'series legend present')
})

test('area renders one path per series', () => {
    const svg = chartSpecToSvg({ ...BASE_SPEC, type: 'area' })
    assert.equal(countOccurrences(svg, 'class="area"'), 2)
    assert.equal(countOccurrences(svg, 'class="point"'), 3 * 2)
})

test('pie renders one slice per category with percentage labels', () => {
    const svg = chartSpecToSvg({ ...BASE_SPEC, type: 'pie' })
    assert.equal(countOccurrences(svg, 'class="slice"'), 3)
    assert.ok(svg.includes('class="pct-label"'), 'percentage labels present')
    assert.ok(svg.includes('Jan') && svg.includes('Feb') && svg.includes('Mar'))
})

test('donut renders one slice per category with a hole', () => {
    const svg = chartSpecToSvg({ ...BASE_SPEC, type: 'donut' })
    assert.equal(countOccurrences(svg, 'class="slice"'), 3)
})

test('cartesian charts render exactly 4 gridlines', () => {
    for (const type of ['bar-v', 'bar-h', 'line', 'area']) {
        const svg = chartSpecToSvg({ ...BASE_SPEC, type })
        assert.equal(countOccurrences(svg, 'class="grid"'), 4, `${type} gridlines`)
    }
})

test('all text is XML escaped', () => {
    const svg = chartSpecToSvg({
        ...BASE_SPEC,
        title: 'A <script> & "more"',
        categories: ['<script>', 'plain'],
        series: [
            { name: '<b>x</b>', values: [1, 2] },
            { name: 'Andra <i>serien</i>', values: [3, 4] },
        ],
    })
    assert.ok(svg.includes('&lt;script&gt;'), 'category escaped')
    assert.ok(svg.includes('A &lt;script&gt; &amp; &quot;more&quot;'), 'title escaped')
    assert.ok(svg.includes('&lt;b&gt;x&lt;/b&gt;'), 'series name escaped')
    assert.ok(!svg.includes('<script>'), 'no raw script tag')
    assert.ok(!svg.includes('<b>'), 'no raw series markup')
})

test('coercion: numeric strings plot, non-numeric map to 0', () => {
    assert.equal(coerceChartValue('12.5'), 12.5)
    assert.equal(coerceChartValue(7), 7)
    assert.equal(coerceChartValue('abc'), 0)
    assert.equal(coerceChartValue(NaN), 0)
    assert.equal(coerceChartValue(undefined), 0)
    assert.equal(coerceChartValue(-4), 0)
    const svg = chartSpecToSvg({
        version: 1,
        type: 'bar-v',
        categories: ['A'],
        series: [{ name: 'S', values: ['abc'] }],
        options: { width: 200, height: 200 },
    })
    assert.ok(!svg.includes('NaN'))
    assert.equal(countOccurrences(svg, 'class="bar"'), 1)
})

test('default palette is used when options.colors is missing', () => {
    const svg = chartSpecToSvg(BASE_SPEC)
    assert.ok(svg.includes(DEFAULT_CHART_COLORS[0]), 'first series uses palette color 0')
    assert.ok(svg.includes(DEFAULT_CHART_COLORS[1]), 'second series uses palette color 1')
})

test('options.colors overrides the default palette', () => {
    const svg = chartSpecToSvg({ ...BASE_SPEC, options: { width: 480, height: 320, colors: ['#123456'] } })
    assert.ok(svg.includes('#123456'))
    assert.ok(!svg.includes(`"${DEFAULT_CHART_COLORS[0]}"`))
})

test('deterministic: identical input produces identical SVG', () => {
    const a = chartSpecToSvg(BASE_SPEC)
    const b = chartSpecToSvg(JSON.parse(JSON.stringify(BASE_SPEC)))
    assert.equal(a, b)
})

test('empty and single-point data still render', () => {
    const empty = chartSpecToSvg({
        version: 1,
        type: 'bar-v',
        categories: [],
        series: [],
        options: { width: 200, height: 200 },
    })
    assert.ok(empty.startsWith('<svg '))
    const single = chartSpecToSvg({
        version: 1,
        type: 'pie',
        categories: ['Enda'],
        series: [{ name: 'S', values: [5] }],
        options: { width: 200, height: 200 },
    })
    assert.equal(countOccurrences(single, 'class="slice"'), 1)
    assert.ok(single.includes('>100%</text>'), 'single slice is labelled 100%')
})

test('pie with no plottable data renders a placeholder disc', () => {
    const svg = chartSpecToSvg({
        version: 1,
        type: 'donut',
        categories: ['A'],
        series: [{ name: 'S', values: [0] }],
        options: { width: 200, height: 200 },
    })
    assert.equal(countOccurrences(svg, 'class="slice"'), 0)
    assert.ok(svg.includes('class="empty-chart"'))
})

test('unknown type and unsupported version throw clearly', () => {
    assert.throws(() => chartSpecToSvg({ ...BASE_SPEC, type: 'scatter' }), /unsupported chart type/)
    assert.throws(() => chartSpecToSvg({ ...BASE_SPEC, version: 2 }), /unsupported spec version/)
})

test('niceCeil rounds up to legible steps', () => {
    assert.equal(niceCeil(0), 1)
    assert.equal(niceCeil(9), 10)
    assert.equal(niceCeil(15), 20)
    assert.equal(niceCeil(30), 50)
    assert.equal(niceCeil(120), 200)
})

test('substituteChartSpec resolves tokens and leaves numbers untouched', () => {
    const spec = {
        version: 1,
        type: 'bar-v',
        title: '{{headline}}',
        categories: ['{{month}}', 'Februari'],
        series: [
            { name: 'S', values: ['{{value}}', 12.5, '{{missing}}'] },
        ],
        options: { width: 480, height: 320 },
    }
    const out = substituteChartSpec(spec, { headline: 'Rapport', month: 'Januari', value: '7' })
    assert.equal(out.categories[0], 'Januari')
    assert.equal(out.categories[1], 'Februari')
    assert.equal(out.series[0].values[0], '7')
    assert.equal(out.series[0].values[1], 12.5, 'number cell stays a number')
    assert.equal(out.series[0].values[2], '{{missing}}', 'unknown token kept')
    assert.equal(out.title, '{{headline}}', 'title is not part of the cell contract')
    assert.notEqual(out, spec, 'returns a new spec object')
    assert.equal(spec.categories[0], '{{month}}', 'input not mutated')
})

test('module constants are exported', () => {
    assert.equal(CHART_SPEC_PROP, '_chartSpec')
    assert.equal(QR_PROP, '_qrContent')
    assert.equal(DEFAULT_CHART_COLORS.length, 6)
})

// --- QR -----------------------------------------------------------------

test('qrContentToMatrix produces a square odd-sized matrix', () => {
    const m = qrContentToMatrix('HELLO WORLD')
    assert.equal(m.length, m[0].length, 'square')
    assert.equal(m.length % 2, 1, 'odd module count')
    assert.ok(m.length >= 21, 'at least version 1')
    assert.equal(m[0][0], true, 'top-left finder pattern corner is dark')
})

test('qrContentToMatrix is deterministic', () => {
    const a = qrContentToMatrix('ABC-123')
    const b = qrContentToMatrix('ABC-123')
    assert.deepEqual(a, b)
})

test('qrContentToMatrix encodes UTF-8 Swedish text without error', () => {
    // Without the qrcode_UTF8.js stringToBytes patch this threw or encoded
    // byte-wise wrong; the assertion is that non-ASCII content encodes at
    // all and lands in a valid square matrix.
    const m = qrContentToMatrix('ÅÄÖ åäö')
    assert.equal(m.length, m[0].length)
    assert.equal(m.length % 2, 1)
    // And it must differ from ASCII-only content of the same char length,
    // proving the multibyte path was taken.
    const ascii = qrContentToMatrix('AAAAAAA')
    assert.notDeepEqual(m, ascii)
})

test('qrContentToMatrix error levels produce valid matrices', () => {
    for (const level of ['L', 'M', 'Q', 'H']) {
        const m = qrContentToMatrix('test', { errorLevel: level })
        assert.equal(m.length % 2, 1)
    }
})

test('qrContentToMatrix rejects empty, over-long and bad-level input', () => {
    assert.throws(() => qrContentToMatrix(''), /content is empty/)
    assert.throws(() => qrContentToMatrix('x'.repeat(5000)), /too long/)
    assert.throws(() => qrContentToMatrix('x', { errorLevel: 'Z' }), /errorLevel/)
})

test('qrMatrixToRectSpecs emits one rect per dark module on a grid', () => {
    const matrix = qrContentToMatrix('HELLO')
    const dark = matrix.reduce((n, row) => n + row.filter(Boolean).length, 0)
    const specs = qrMatrixToRectSpecs(matrix, 4, '#112233')
    assert.equal(specs.length, dark)
    for (const s of specs) {
        assert.equal(s.size, 4)
        assert.equal(s.fill, '#112233')
        assert.equal(s.left % 4, 0, 'left on module grid')
        assert.equal(s.top % 4, 0, 'top on module grid')
    }
    const maxCol = Math.max(...specs.map((s) => s.left / 4))
    const maxRow = Math.max(...specs.map((s) => s.top / 4))
    assert.ok(maxCol <= matrix.length - 1 && maxRow <= matrix.length - 1)
})

test('qrMatrixToRectSpecs validates its input', () => {
    assert.throws(() => qrMatrixToRectSpecs([], 4), /non-empty/)
    assert.throws(() => qrMatrixToRectSpecs([[true]], 0), /moduleSize/)
    assert.throws(() => qrMatrixToRectSpecs([[true], [true, false]], 4), /square/)
})
