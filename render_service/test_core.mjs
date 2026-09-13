// render_service/test_core.mjs — unit tests for render_core.mjs (no canvas needed)
import assert from 'node:assert/strict'
import { applyBindingsToScene, substituteText, xmlEscape, absolutizeFileUrl } from './render_core.mjs'

// 1. Token substitution
assert.equal(substituteText('Hej {{headline}}!', { headline: 'Världen' }), 'Hej Världen!')
assert.equal(substituteText('{{a}} {{b}}', { a: 'x' }), 'x {{b}}') // unknown kept
assert.equal(substituteText('{{ headline }}', { headline: 'v' }), 'v') // whitespace tolerated
console.log('✓ token substitution')

// 2. XML escaping (SVG safety)
assert.equal(xmlEscape('<script>alert(1)</script>'), '&lt;script&gt;alert(1)&lt;/script&gt;')
assert.equal(xmlEscape('a & b'), 'a &amp; b')
assert.equal(xmlEscape('"quoted" \'single\''), '&quot;quoted&quot; &apos;single&apos;')
console.log('✓ xml escaping')

// 2b. Escaping must happen exactly once.
//
// server.mjs used to pass escapeXml: true for SVG, and canvas.toSVG() then
// escaped the same text again: '&' became '&amp;amp;', '<' became '&lt;',
// shown literally to whoever opened the file. The SVG path must therefore not
// pre-escape, and this asserts the interaction the two used to get wrong.
{
    const s = { version: '6.9.1', objects: [{ type: 'textbox', text: '{{h}}' }] }
    const preEscaped = applyBindingsToScene(s, { h: 'a & b' }, { escapeXml: true })
    assert.equal(preEscaped.objects[0].text, 'a &amp; b', 'escapeXml: true escapes once')

    const raw = applyBindingsToScene(s, { h: 'a & b' }, { escapeXml: false })
    assert.equal(raw.objects[0].text, 'a & b', 'escapeXml: false leaves it for Fabric')

    // What the bug looked like: one more pass over already-escaped text.
    assert.equal(xmlEscape(raw.objects[0].text), 'a &amp; b', 'raw needs exactly one pass')
    assert.equal(
        xmlEscape(preEscaped.objects[0].text),
        'a &amp;amp; b',
        'double escaping is visible, which is why the SVG path must not pre-escape'
    )
    console.log('✓ escaping happens exactly once')
}

// 3. applyBindingsToScene: substitution + hide-if-empty + escaping + image absolutize
const scene = {
    version: '6.9.1',
    background: '#ffffff',
    objects: [
        { type: 'textbox', text: '{{headline}}' },
        { type: 'textbox', text: '<b>{{cta}}</b>', _hideIfEmpty: { placeholder: 'cta' } },
        { type: 'image', src: '/web/image/42' },
        { type: 'textbox', text: 'static' },
    ],
}
const out = applyBindingsToScene(scene, { headline: 'Sommar', cta: '' }, { escapeXml: true, apiBase: 'http://odoo:8069' })
assert.equal(out.objects[0].text, 'Sommar')
assert.equal(out.objects[1].visible, false) // cta empty → hidden
assert.equal(out.objects[1].opacity, 0)
assert.equal(out.objects[2].src, 'http://odoo:8069/web/image/42')
assert.equal(out.objects[3].text, 'static')

const out2 = applyBindingsToScene(scene, { headline: '<script>x</script>', cta: 'Köp' }, { escapeXml: true })
assert.equal(out2.objects[0].text, '&lt;script&gt;x&lt;/script&gt;')
assert.notEqual(out2.objects[1].visible, false) // visible (not hidden)
assert.equal(out2.objects[1].text, '&lt;b&gt;Köp&lt;/b&gt;')
console.log('✓ applyBindingsToScene (substitute, hide-if-empty, escape, absolutize)')

// 4. PNG path does NOT escape (raster is inert, entities would show literally)
const outPng = applyBindingsToScene(scene, { headline: 'a < b' }, { escapeXml: false })
assert.equal(outPng.objects[0].text, 'a < b')
console.log('✓ PNG path keeps raw text (no escaping)')

// 5. Source scene is not mutated (deep copy)
assert.equal(scene.objects[0].text, '{{headline}}')
assert.equal(scene.objects[1].visible, undefined)
console.log('✓ source scene not mutated')

// 6. absolutizeFileUrl
assert.equal(absolutizeFileUrl('data:image/png;base64,AAA'), 'data:image/png;base64,AAA')
assert.equal(absolutizeFileUrl('http://x/y.png', 'http://b'), 'http://x/y.png')
assert.equal(absolutizeFileUrl('/web/image/1', 'http://odoo:8069'), 'http://odoo:8069/web/image/1')
console.log('✓ absolutizeFileUrl')

console.log('\nALL render_core TESTS PASSED')
