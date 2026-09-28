// render_service/test_binding.mjs: unit tests for data binding:
// pipe transforms, _hideIfEmpty / _required / _dataBinding shapes and
// cover-fit math. Run: node render_service/test_binding.mjs
import assert from 'node:assert/strict'
import {
    applyBindingsToScene,
    applyPipeTransform,
    computeCoverFit,
    prepareCoverFit,
    RequiredBindingError,
    substituteText,
} from './render_core.mjs'

// 1. Pipe transforms
assert.equal(applyPipeTransform('stol', 'upper'), 'STOL')
assert.equal(applyPipeTransform('STOL', 'lower'), 'stol')
assert.equal(applyPipeTransform('STOL', 'lowercase'), 'stol')
assert.equal(applyPipeTransform('stol', 'uppercase'), 'STOL')
assert.equal(applyPipeTransform('  hej  ', 'trim'), 'hej')
assert.equal(applyPipeTransform('hej varlden', 'title'), 'Hej Varlden')
// Note: JS \b is ASCII-based, so non-ASCII letters (ä, ö, å) count as word
// boundaries; the verbatim port from render-engine-os uppercases them too.
assert.equal(applyPipeTransform('hej världen', 'title'), 'Hej VÄRlden')
assert.equal(applyPipeTransform('sTOL', 'capitalize'), 'Stol')
assert.equal(applyPipeTransform('stol', 'unknown'), 'stol')
console.log('✓ pipe transforms')

// 2. Token substitution with pipes (incl. dotted paths, chained pipes)
assert.equal(substituteText('{{name|upper}}', { name: 'Stol' }), 'STOL')
assert.equal(
    substituteText('{{categ_id.name|title}}', { 'categ_id.name': 'fina stolar' }),
    'Fina Stolar'
)
assert.equal(
    substituteText('{{name|trim|lower}}', { name: '  STOL  ' }),
    'stol'
)
assert.equal(substituteText('{{name|upper}}', {}), '{{name|upper}}') // unknown kept
assert.equal(substituteText('{{missing}}', { name: 'x' }), '{{missing}}')
assert.equal(
    substituteText('A {{a}} B {{b|lower}}', { a: '1', b: 'XYZ' }),
    'A 1 B xyz'
)
console.log('✓ token substitution with pipes')

// 3. _hideIfEmpty with the {field} shape
{
    const scene = {
        version: '6.9.1',
        objects: [
            { type: 'rect', _hideIfEmpty: { field: 'is_new' } },
            { type: 'textbox', text: 'static' },
        ],
    }
    const hidden = applyBindingsToScene(scene, { is_new: '' })
    assert.equal(hidden.objects[0].visible, false)
    assert.equal(hidden.objects[0].opacity, 0)
    const shown = applyBindingsToScene(scene, { is_new: 'True' })
    assert.notEqual(shown.objects[0].visible, false)
    // The legacy {placeholder} shape is no longer honoured (migrated away).
    const legacy = {
        version: '6.9.1',
        objects: [{ type: 'rect', _hideIfEmpty: { placeholder: 'cta' } }],
    }
    const legacyOut = applyBindingsToScene(legacy, { cta: '' })
    assert.notEqual(legacyOut.objects[0].visible, false)
    console.log('✓ _hideIfEmpty {field} hides on empty (legacy shape ignored)')
}

// 4. _required aborts with an error naming the layer
{
    const scene = {
        version: '6.9.1',
        objects: [
            {
                type: 'image',
                src: '/web/image/1',
                _layerName: 'Hero image',
                _dataBinding: { field: 'image_1920' },
                _required: { field: 'image_1920' },
            },
        ],
    }
    assert.throws(
        () => applyBindingsToScene(scene, { image_1920: '' }),
        (err) =>
            err instanceof RequiredBindingError &&
            err.message.includes('Hero image') &&
            err.message.includes('image_1920')
    )
    // Satisfied required passes through and swaps the src.
    const out = applyBindingsToScene(scene, { image_1920: 'data:image/png;base64,AAA' })
    assert.equal(out.objects[0].src, 'data:image/png;base64,AAA')
    // Falls back to the Fabric type when no _layerName is set.
    const unnamed = {
        version: '6.9.1',
        objects: [{ type: 'image', _required: { field: 'logo' } }],
    }
    assert.throws(
        () => applyBindingsToScene(unnamed, { logo: '' }),
        /layer "image"/
    )
    console.log('✓ _required raises RequiredBindingError naming the layer')
}

// 5. _dataBinding: swap src, empty hides, no fitTargets means no marker
{
    const scene = {
        version: '6.9.1',
        objects: [
            { type: 'image', src: '/web/image/9', _dataBinding: { field: 'image_1920' } },
            { type: 'image', src: '/web/image/9', _dataBinding: { field: 'logo' } },
        ],
    }
    const out = applyBindingsToScene(
        scene,
        { image_1920: 'data:image/png;base64,AAA', logo: '' },
        { apiBase: 'http://odoo:8069' }
    )
    assert.equal(out.objects[0].src, 'data:image/png;base64,AAA')
    assert.equal(out.objects[0].visible, undefined)
    assert.equal(out.objects[1].visible, false) // empty binding hides
    assert.equal(out.objects[1].opacity, 0)
    assert.equal(out.objects[1].src, 'http://odoo:8069/web/image/9')
    console.log('✓ _dataBinding swaps src / hides on empty')
}

// 6. Cover-fit: prepareCoverFit captures frame + marker, resets geometry
{
    const obj = {
        type: 'image',
        src: '/web/image/9',
        left: 100,
        top: 50,
        width: 200,
        height: 100,
        scaleX: 2,
        scaleY: 2,
        originX: 'left',
        originY: 'top',
        cropX: 10,
        cropY: 10,
        clipPath: { type: 'rect', width: 200, height: 100 },
        _dataBinding: { field: 'image_1920' },
    }
    const fitTargets = new Map()
    const json = applyBindingsToScene(
        { version: '6.9.1', objects: [obj] },
        { image_1920: 'data:image/png;base64,AAA' },
        { fitTargets }
    )
    const out = json.objects[0]
    assert.equal(fitTargets.size, 1)
    const marker = out.id
    assert.ok(marker.startsWith('arc_fit_'), 'frame marker stashed on obj.id')
    const fit = fitTargets.get(marker)
    assert.equal(fit.frameW, 400) // 200 * scaleX 2
    assert.equal(fit.frameH, 200)
    assert.equal(fit.oldHostScaleX, 2)
    assert.equal(fit.oldHostScaleY, 2)
    assert.equal(fit.hadClipPath, true)
    // Geometry reset so Fabric loads at the new image's natural size.
    assert.equal(out.width, undefined)
    assert.equal(out.height, undefined)
    assert.equal(out.cropX, 0)
    assert.equal(out.cropY, 0)
    assert.equal(out.scaleX, 1)
    assert.equal(out.scaleY, 1)
    assert.equal(out.originX, 'center')
    assert.equal(out.originY, 'center')
    // Frame center for left/top origin: 100 + 400/2, 50 + 200/2.
    assert.equal(out.left, 300)
    assert.equal(out.top, 150)
    console.log('✓ prepareCoverFit frame capture + geometry reset')
}

// 6b. Center-origin frame anchors at the same center
{
    const obj = {
        type: 'image',
        left: 300,
        top: 150,
        width: 200,
        height: 100,
        scaleX: 2,
        scaleY: 2,
        originX: 'center',
        originY: 'center',
        _dataBinding: { field: 'image_1920' },
    }
    const fitTargets = new Map()
    const json = applyBindingsToScene(
        { version: '6.9.1', objects: [obj] },
        { image_1920: 'data:image/png;base64,AAA' },
        { fitTargets }
    )
    assert.equal(json.objects[0].left, 300)
    assert.equal(json.objects[0].top, 150)
    console.log('✓ prepareCoverFit center-origin anchor')
}

// 7. computeCoverFit math (shared with the editor, must stay identical)
{
    // Landscape source into a square frame: the width overflows, so the
    // crop must come from X.
    const f = computeCoverFit(400, 200, 100, 100)
    assert.equal(f.scale, 0.5)
    assert.equal(f.width, 200)
    assert.equal(f.height, 200)
    assert.equal(f.cropX, 100)
    assert.equal(f.cropY, 0)

    // Portrait source into a wide, shorter frame: the width already fills
    // the frame (scale 1) and the overflow is cropped from Y.
    const g = computeCoverFit(200, 400, 200, 100)
    assert.equal(g.scale, 1)
    assert.equal(g.width, 200)
    assert.equal(g.height, 100)
    assert.equal(g.cropX, 0)
    assert.equal(g.cropY, 150)

    // Frame larger than the source still covers (scale up).
    const h = computeCoverFit(50, 50, 100, 100)
    assert.equal(h.scale, 2)
    assert.equal(h.cropX, 0)
    assert.equal(h.cropY, 0)

    // ClipPath compensation uses the inverse host-scale ratio.
    const c = computeCoverFit(400, 200, 100, 100, 2, 2)
    assert.equal(c.clipScaleX, 4) // old host scale 2 / new scale 0.5
    assert.equal(c.clipScaleY, 4)
    console.log('✓ computeCoverFit math')
}

// 8. Full-pipe: substitution + required + hide + data binding in one scene
{
    const scene = {
        version: '6.9.1',
        background: '#ffffff',
        objects: [
            { type: 'textbox', text: '{{name|upper}}' },
            { type: 'textbox', text: '{{categ_id.name}}', _hideIfEmpty: { field: 'categ_id.name' } },
            { type: 'image', src: '/web/image/2', _dataBinding: { field: 'image_1920' } },
            { type: 'rect', _required: { field: 'name' } },
        ],
    }
    const out = applyBindingsToScene(
        scene,
        { name: 'stol', 'categ_id.name': 'Chairs', image_1920: 'data:image/png;base64,AAA' },
        { escapeXml: true }
    )
    assert.equal(out.objects[0].text, 'STOL')
    assert.equal(out.objects[1].text, 'Chairs')
    assert.notEqual(out.objects[1].visible, false)
    assert.equal(out.objects[2].src, 'data:image/png;base64,AAA')
    assert.throws(
        () => applyBindingsToScene(scene, { name: '', 'categ_id.name': '', image_1920: '' }),
        RequiredBindingError
    )
    console.log('✓ combined scene with bindings')
}

console.log('\nALL binding TESTS PASSED')
