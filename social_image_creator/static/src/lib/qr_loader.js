/** @odoo-module **/

/**
 * Lazy loader for the vendored qrcode-generator library (design D5 in
 * openspec/changes/editor-grid-dynamic-elements).
 *
 * Mirrors lib/fabric_loader.js in shape (one cached promise, load on first
 * use) but not in mechanism: fabric's UMD build captures the global object
 * itself, so an import() of its URL leaves window.fabric behind and
 * `mod.default || window.fabric` picks it up. The qrcode-generator UMD has
 * no global-capturing branch: it only registers AMD/CJS and otherwise
 * relies on a classic script's top-level `var qrcode` hoisting onto
 * window. Evaluated as an ES module (which is what import() does) that
 * `var` stays module-scoped, so this loader injects two classic <script>
 * tags instead: qrcode.js first, then qrcode_UTF8.js, whose entire content
 * is the assignment qrcode.stringToBytes = qrcode.stringToBytesFuncs['UTF-8'].
 * The UTF-8 override is applied explicitly here too, exactly like
 * render_service/qr_matrix.mjs does on the node side.
 *
 * Browser-only by construction: everything touching document lives inside
 * loadQr(), so the module stays importable under Node for the tests.
 */
let _qrPromise = null;

const QR_BASE_URL = "/social_image_creator/static/lib/qrcode-generator/qrcode.js";
const QR_UTF8_URL = "/social_image_creator/static/lib/qrcode-generator/qrcode_UTF8.js";

function injectScript(src) {
    return new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = src;
        script.onload = () => resolve();
        script.onerror = () =>
            reject(new Error(`qr_loader: failed to load ${src}`));
        document.head.appendChild(script);
    });
}

export function loadQr() {
    if (!_qrPromise) {
        _qrPromise = (async () => {
            await injectScript(QR_BASE_URL);
            const qrcode = window.qrcode;
            if (typeof qrcode !== "function") {
                throw new Error("qr_loader: qrcode global missing after load");
            }
            // UTF-8 byte encoding, byte-identical to what qrcode_UTF8.js
            // applies; without it, non-ASCII content such as Swedish text
            // would encode byte-wise wrong. Idempotent by nature.
            qrcode.stringToBytes = qrcode.stringToBytesFuncs["UTF-8"];
            await injectScript(QR_UTF8_URL);
            return qrcode;
        })();
    }
    return _qrPromise;
}
