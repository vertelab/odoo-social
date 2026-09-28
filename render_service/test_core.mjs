// render_service/test_core.mjs: unit tests for render_core.mjs (no canvas needed)
import assert from 'node:assert/strict'
import {
    absolutizeFileUrl,
    applyBindingsToScene,
    applyTextTransform,
    assertSceneImageUrlsSafe,
    computeAutofitFontSize,
    parseMarkdownSegments,
    SceneImageUrlError,
    substituteText,
    xmlEscape,
} from './render_core.mjs'

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
        { type: 'textbox', text: '<b>{{cta}}</b>', _hideIfEmpty: { field: 'cta' } },
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

// 6. absolutizeFileUrl: strict allowlist (design D3)
// data: URLs pass through untouched
assert.equal(absolutizeFileUrl('data:image/png;base64,AAA'), 'data:image/png;base64,AAA')
// empty and non-string srcs are left alone
assert.equal(absolutizeFileUrl(''), '')
assert.equal(absolutizeFileUrl(undefined), undefined)
assert.equal(absolutizeFileUrl(null), null)
// /web/image paths are absolutized against apiBase
assert.equal(absolutizeFileUrl('/web/image/1', 'http://odoo:8069'), 'http://odoo:8069/web/image/1')
// without apiBase the path stays relative (callers must pass apiBase)
assert.equal(absolutizeFileUrl('/web/image/1', ''), '/web/image/1')
// absolute URLs under apiBase pass; trailing slash on apiBase is trimmed
assert.equal(absolutizeFileUrl('http://odoo:8069/web/image/1', 'http://odoo:8069'), 'http://odoo:8069/web/image/1')
assert.equal(absolutizeFileUrl('http://odoo:8069/web/image/1', 'http://odoo:8069/'), 'http://odoo:8069/web/image/1')
// everything else throws, naming the offending URL
for (const bad of [
    'http://127.0.0.1/x.png',
    'https://evil.example/x.png',
    'file:///etc/passwd',
    '/img/local.png',
    '../secrets.png',
    'not-a-url',
]) {
    assert.throws(() => absolutizeFileUrl(bad, 'http://odoo:8069'), /not allowed|not under/, bad)
}
// a host that merely shares a prefix with the base is still foreign
assert.throws(
    () => absolutizeFileUrl('http://odoo:8069.evil.example/x.png', 'http://odoo:8069'),
    /not under the configured API base/
)
// with an empty apiBase no absolute URL can match, so they all fail closed
assert.throws(
    () => absolutizeFileUrl('http://odoo:8069/web/image/1', ''),
    SceneImageUrlError
)
// the error names the offending URL
{
    const err = (() => {
        try {
            absolutizeFileUrl('file:///etc/passwd', 'http://odoo:8069')
        } catch (e) {
            return e
        }
    })()
    assert.ok(err instanceof SceneImageUrlError)
    assert.ok(err.message.includes('file:///etc/passwd'), 'error names the offending URL')
}
console.log('✓ absolutizeFileUrl (strict allowlist, all branches)')

// 7. assertSceneImageUrlsSafe: pre-flight walk over every image object
{
    // flat scene with a bad src: throws naming the layer and the URL
    const flat = {
        version: '6.9.1',
        objects: [
            { type: 'textbox', text: 'hej' },
            { type: 'image', _layerName: 'Hero', src: 'http://127.0.0.1/x.png' },
        ],
    }
    assert.throws(
        () => assertSceneImageUrlsSafe(flat, 'http://odoo:8069'),
        (err) =>
            err instanceof SceneImageUrlError &&
            err.message.includes('Hero') &&
            err.message.includes('http://127.0.0.1/x.png')
    )
    // no _layerName: falls back to the type
    assert.throws(
        () => assertSceneImageUrlsSafe({ objects: [{ type: 'image', src: 'file:///etc/passwd' }] }, 'http://odoo:8069'),
        /Layer "image"/
    )

    // nested group objects are walked too
    const nested = {
        version: '6.9.1',
        objects: [
            {
                type: 'group',
                objects: [{ type: 'image', _layerName: 'Badge', src: 'file:///etc/passwd' }],
            },
        ],
    }
    assert.throws(() => assertSceneImageUrlsSafe(nested, 'http://odoo:8069'), /Badge/)

    // non-image objects (even with an src prop) and images without src pass;
    // allowlisted srcs pass
    const clean = {
        version: '6.9.1',
        objects: [
            { type: 'rect', src: 'http://evil.example/x.png' }, // not an image: src ignored
            { type: 'image' }, // no src
            { type: 'image', src: '' },
            { type: 'image', src: 'data:image/png;base64,AAA' },
            { type: 'image', src: '/web/image/42' },
            { type: 'image', src: 'http://odoo:8069/web/image/42' },
        ],
    }
    assert.doesNotThrow(() => assertSceneImageUrlsSafe(clean, 'http://odoo:8069'))

    // empty apiBase: data: and relative /web/image still pass, absolute URLs fail
    const cleanRelativeOnly = {
        objects: [
            { type: 'image', src: 'data:image/png;base64,AAA' },
            { type: 'image', src: '/web/image/42' },
        ],
    }
    assert.doesNotThrow(() => assertSceneImageUrlsSafe(cleanRelativeOnly, ''))
    assert.throws(
        () => assertSceneImageUrlsSafe({ objects: [{ type: 'image', src: 'http://odoo:8069/web/image/1' }] }, ''),
        SceneImageUrlError
    )

    // a non-object scene does not crash the scan
    assert.doesNotThrow(() => assertSceneImageUrlsSafe(null, 'http://odoo:8069'))
    assert.doesNotThrow(() => assertSceneImageUrlsSafe('nope', 'http://odoo:8069'))
    console.log('✓ assertSceneImageUrlsSafe (flat, nested, non-image ignored, empty apiBase)')
}

// 8. Render-time case transform (task 2.1): applies to the RESOLVED
// value; the stored scene keeps its token text.
{
    const scene = {
        version: '6.9.1',
        objects: [
            { type: 'textbox', text: '{{name}}', _textTransform: 'upper' },
            { type: 'textbox', text: '{{name}}', _textTransform: 'lower' },
            { type: 'textbox', text: '{{name}}', _textTransform: 'none' },
            { type: 'textbox', text: '**{{name}}**', _textTransform: 'upper' },
        ],
    }
    const out = applyBindingsToScene(scene, { name: 'Acme' })
    assert.equal(out.objects[0].text, 'ACME')
    assert.equal(out.objects[1].text, 'acme')
    assert.equal(out.objects[2].text, 'Acme') // 'none' leaves the value alone
    // Transform runs BEFORE markdown strips the markers: '**ACME**' loses
    // the asterisks, the resolved value keeps its case.
    assert.equal(out.objects[3].text, 'ACME')
    assert.equal(out.objects[3].styles['0'][0].fontWeight, 'bold')
    // The pre-substitution scene is untouched, token intact.
    assert.equal(scene.objects[0].text, '{{name}}')
    assert.equal(scene.objects[3].text, '**{{name}}**')
    assert.equal(applyTextTransform('hej varlden', 'title'), 'Hej Varlden')
    console.log('✓ _textTransform applies to resolved text, token scene untouched')
}

// 9. Inline markdown to per-char styles (task 1.1)
{
    const sceneFor = (text, extra = {}) => ({
        version: '6.9.1',
        objects: [{ type: 'textbox', text, ...extra }],
    })

    // Bold segment: markers stripped, chars 7-14 (incl) bold.
    let out = applyBindingsToScene(sceneFor('Price: **1 299 kr**'), {})
    assert.equal(out.objects[0].text, 'Price: 1 299 kr')
    assert.equal(out.objects[0].styles['0'][0], undefined)
    for (let i = 7; i < 15; i++) {
        assert.equal(out.objects[0].styles['0'][i].fontWeight, 'bold', `char ${i}`)
    }

    // Italic, including the _marker_ form.
    out = applyBindingsToScene(sceneFor('*hej*'), {})
    assert.equal(out.objects[0].text, 'hej')
    for (let i = 0; i < 3; i++) {
        assert.equal(out.objects[0].styles['0'][i].fontStyle, 'italic')
    }
    out = applyBindingsToScene(sceneFor('_hej_'), {})
    assert.equal(out.objects[0].text, 'hej')
    assert.equal(out.objects[0].styles['0'][2].fontStyle, 'italic')

    // Adjacent bold + italic segments on one line.
    out = applyBindingsToScene(sceneFor('**a** *b*'), {})
    assert.equal(out.objects[0].text, 'a b')
    assert.equal(out.objects[0].styles['0'][0].fontWeight, 'bold')
    assert.equal(out.objects[0].styles['0'][2].fontStyle, 'italic')

    // Unmatched marker parses to nothing: text stays literal, no styles.
    out = applyBindingsToScene(sceneFor('**orphan'), {})
    assert.equal(out.objects[0].text, '**orphan')
    assert.equal(out.objects[0].styles, undefined)

    // Escaped markers stay literal when a real segment exists.
    out = applyBindingsToScene(sceneFor('**b** \\*lit\\*'), {})
    assert.equal(out.objects[0].text, 'b *lit*')
    assert.equal(out.objects[0].styles['0'][0].fontWeight, 'bold')
    assert.equal(out.objects[0].styles['0'][2], undefined)

    // Only escaped/unmatched markers: whole text stays as typed.
    out = applyBindingsToScene(sceneFor('\\*not italic\\*'), {})
    assert.equal(out.objects[0].text, '\\*not italic\\*')

    // Multiline: ranges land on fabric line/char indices.
    out = applyBindingsToScene(sceneFor('**a**\n*b*'), {})
    assert.equal(out.objects[0].text, 'a\nb')
    assert.equal(out.objects[0].styles['0'][0].fontWeight, 'bold')
    assert.equal(out.objects[0].styles['1'][0].fontStyle, 'italic')

    // Pre-existing per-char styles survive: other chars, other attrs.
    out = applyBindingsToScene(
        sceneFor('**b** cd', {
            styles: {
                '0': {
                    '0': { fill: '#ff0000' },
                    '5': { textBackgroundColor: '#00ff00' },
                },
            },
        }),
        {}
    )
    assert.equal(out.objects[0].text, 'b cd')
    assert.deepEqual(out.objects[0].styles['0']['0'], {
        fill: '#ff0000',
        fontWeight: 'bold',
    })
    assert.deepEqual(out.objects[0].styles['0']['5'], {
        textBackgroundColor: '#00ff00',
    })

    // Markdown inside a substituted value (the common bound case).
    out = applyBindingsToScene(sceneFor('{{pitch}}'), {
        pitch: 'Köp **nu** eller *ångra*',
    })
    assert.equal(out.objects[0].text, 'Köp nu eller ångra')
    assert.equal(out.objects[0].styles['0'][4].fontWeight, 'bold')
    assert.equal(out.objects[0].styles['0'][13].fontStyle, 'italic')

    // The parser speaks segments; direct shape check.
    assert.deepEqual(parseMarkdownSegments('x **ab** y'), {
        text: 'x ab y',
        segments: [{ start: 2, end: 4, weight: 'bold' }],
    })
    assert.equal(parseMarkdownSegments('plain'), null)
    console.log('✓ markdown to per-char styles (bold, italic, adjacent, unmatched, escaped, multiline, merge)')
}

// 10. Autofit at render time (task 2.2): the editor's binary search,
// driven by an injected measure. Never grows, floors at 4 px.
{
    // The injected measure speaks (lineText, fontDescription); the
    // adapter inside applyBindingsToScene drives it per candidate size.
    const measure = (line, desc) => line.length * desc.fontSize * 0.6
    const sceneFor = (text, fontSize = 40, width = 100) => ({
        version: '6.9.1',
        objects: [
            { type: 'textbox', text, _overflow: 'autofit', width, fontSize },
        ],
    })

    // Long resolved value shrinks to fit: 20 chars * size * 0.6 <= 100.
    let out = applyBindingsToScene(
        sceneFor('{{name}}'),
        { name: 'abcdefghijklmnopqrst' },
        { measure }
    )
    assert.equal(out.objects[0].fontSize, 8)

    // Short value never grows past the designed size.
    out = applyBindingsToScene(sceneFor('{{name}}'), { name: 'ab' }, { measure })
    assert.equal(out.objects[0].fontSize, 40)

    // Floor: even 4 px overflows, so 4 it is.
    out = applyBindingsToScene(
        sceneFor('{{name}}'),
        { name: 'x'.repeat(100) },
        { measure }
    )
    assert.equal(out.objects[0].fontSize, 4)

    // Multiline: the widest LINE (by char count) is measured.
    out = applyBindingsToScene(
        sceneFor('{{name}}', 40, 100),
        { name: 'kort\nabcdefghijklmnopqrst' },
        { measure }
    )
    assert.equal(out.objects[0].fontSize, 8)

    // Without a measure, autofit is a no-op rather than a guess.
    out = applyBindingsToScene(sceneFor('{{name}}'), {
        name: 'x'.repeat(100),
    })
    assert.equal(out.objects[0].fontSize, 40)

    // measure receives the line text and the object's font description.
    const seen = []
    const spyMeasure = (line, desc) => {
        seen.push([line, desc.fontFamily, desc.fontWeight, desc.fontStyle])
        return line.length * desc.fontSize * 0.6
    }
    out = applyBindingsToScene(
        {
            version: '6.9.1',
            objects: [
                {
                    type: 'textbox',
                    text: 'ab',
                    _overflow: 'autofit',
                    width: 100,
                    fontSize: 40,
                    fontFamily: 'Arial',
                    fontWeight: 'bold',
                    fontStyle: 'italic',
                },
            ],
        },
        {},
        { measure: spyMeasure }
    )
    assert.equal(out.objects[0].fontSize, 40) // fits at start size
    assert.ok(seen.length > 0)
    assert.deepEqual(seen[0], ['ab', 'Arial', 'bold', 'italic'])

    // The mirrored binary search, directly: its own measure speaks
    // (fontSize, widestLineText).
    const coreMeasure = (size, line) => line.length * size * 0.6
    assert.equal(
        computeAutofitFontSize({
            text: 'abcdefghijklmnopqrst',
            boxWidth: 100,
            startSize: 40,
            measure: coreMeasure,
        }),
        8
    )
    assert.equal(
        computeAutofitFontSize({
            text: 'x'.repeat(100),
            boxWidth: 100,
            startSize: 40,
            measure: coreMeasure,
        }),
        4
    )
    console.log('✓ autofit shrinks to fit, never grows, floors at 4, no-op without measure')
}

console.log('\nALL render_core TESTS PASSED')
