// render_service/test_dynamic_parity.mjs: fixture tests for the render-side
// dynamic element flow: applyBindingsToScene substitutes {{tokens}} inside
// _chartSpec cells and _qrContent strings, and the pure generators then
// produce geometry from the resolved values. Run: node --test test_dynamic_parity.mjs
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { applyBindingsToScene } from './render_core.mjs'
import { chartSpecToSvg } from './chart_spec.mjs'
import { qrContentToMatrix } from './qr_matrix.mjs'

const BINDINGS = {
    'product.name': 'Bord',
    'product.weight': 12.5,
    'product.default_code': 'ABC-123',
    'categ.name': 'Kök',
}

test('chart group: bound cells resolve and the SVG reflects them', () => {
    const scene = {
        version: '6.9.1',
        objects: [
            {
                type: 'group',
                left: 40,
                top: 40,
                _chartSpec: {
                    version: 1,
                    type: 'bar-v',
                    title: 'Data',
                    categories: ['{{categ.name}}', 'Static'],
                    series: [{ name: 'Vikt', values: ['{{product.weight}}', 3] }],
                    options: { width: 320, height: 240 },
                },
                objects: [{ type: 'rect', width: 10, height: 10 }],
            },
        ],
    }
    const out = applyBindingsToScene(scene, BINDINGS)
    const spec = out.objects[0]._chartSpec
    assert.equal(spec.categories[0], 'Kök')
    assert.equal(spec.categories[1], 'Static')
    // Substitution yields strings (substituteText contract); the chart
    // renderer coerces them back to numbers.
    assert.equal(spec.series[0].values[0], '12.5')
    assert.equal(spec.series[0].values[1], 3)
    // The original scene must not be mutated (deep copy in, copy out).
    assert.equal(scene.objects[0]._chartSpec.categories[0], '{{categ.name}}')

    // Round-trip through the generator: the SVG carries the resolved labels
    // and no token syntax.
    const svg = chartSpecToSvg(spec)
    assert.ok(svg.includes('Kök'))
    assert.ok(svg.includes('Static'))
    assert.ok(!svg.includes('{{'))
    assert.ok(!svg.includes('NaN'))
})

test('chart group: unparseable bound cell plots as 0 and never aborts', () => {
    const scene = {
        version: '6.9.1',
        objects: [
            {
                type: 'group',
                _chartSpec: {
                    version: 1,
                    type: 'line',
                    categories: ['A'],
                    series: [{ name: 'S', values: ['{{missing}}'] }],
                    options: { width: 200, height: 200 },
                },
                objects: [],
            },
        ],
    }
    const out = applyBindingsToScene(scene, BINDINGS)
    const svg = chartSpecToSvg(out.objects[0]._chartSpec)
    assert.ok(svg.startsWith('<svg '))
    assert.ok(!svg.includes('NaN'))
})

test('chart spec resolves inside a nested group', () => {
    const scene = {
        version: '6.9.1',
        objects: [
            {
                type: 'group',
                objects: [
                    {
                        type: 'group',
                        _chartSpec: {
                            version: 1,
                            type: 'pie',
                            categories: ['{{categ.name}}'],
                            series: [{ name: 'S', values: ['{{product.weight}}'] }],
                            options: { width: 200, height: 200 },
                        },
                        objects: [],
                    },
                ],
            },
        ],
    }
    const out = applyBindingsToScene(scene, BINDINGS)
    const inner = out.objects[0].objects[0]
    assert.equal(inner._chartSpec.categories[0], 'Kök')
    assert.equal(inner._chartSpec.series[0].values[0], '12.5')
})

test('QR group: bound content resolves and encodes like static content', () => {
    const scene = {
        version: '6.9.1',
        objects: [
            { type: 'group', _qrContent: '{{product.default_code}}', objects: [] },
            { type: 'group', _qrContent: 'ABC-123', objects: [] },
        ],
    }
    const out = applyBindingsToScene(scene, BINDINGS)
    assert.equal(out.objects[0]._qrContent, 'ABC-123')
    assert.equal(out.objects[1]._qrContent, 'ABC-123')
    // Parity between the bound path and the static path: identical resolved
    // content must give an identical module matrix.
    assert.deepEqual(
        qrContentToMatrix(out.objects[0]._qrContent),
        qrContentToMatrix(out.objects[1]._qrContent)
    )
})

test('QR content resolves inside a nested group', () => {
    const scene = {
        version: '6.9.1',
        objects: [
            {
                type: 'group',
                objects: [
                    { type: 'group', _qrContent: '{{product.name}}', objects: [] },
                ],
            },
        ],
    }
    const out = applyBindingsToScene(scene, BINDINGS)
    assert.equal(out.objects[0].objects[0]._qrContent, 'Bord')
})

test('objects without dynamic props are left alone', () => {
    const scene = {
        version: '6.9.1',
        objects: [
            { type: 'textbox', text: '{{product.name}}' },
            { type: 'rect', _chartSpec: null },
            { type: 'group', objects: [{ type: 'textbox', text: 'plain' }] },
        ],
    }
    const out = applyBindingsToScene(scene, BINDINGS)
    assert.equal(out.objects[0].text, 'Bord')
    assert.equal(out.objects[1]._chartSpec, null)
    assert.equal(out.objects[2].objects[0].text, 'plain')
})
