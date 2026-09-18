/** @odoo-module **/

/**
 * Lazy loader for Fabric.js v6.
 *
 * Fabric 6's npm `dist/` ships UMD builds (index.min.js). In a browser the
 * UMD wrapper takes the global branch and sets `window.fabric` instead of
 * exporting anything, while in Node (CJS interop) the same file exposes the
 * namespace as the ESM `default` export. We therefore support both: take
 * `mod.default` when present, otherwise fall back to the global that the
 * UMD set during module evaluation.
 *
 * Usage:
 *   import { loadFabric } from "@social_marketing/lib/fabric_loader";
 *   const fabric = await loadFabric();
 *   const canvas = new fabric.Canvas(el);
 */
let _fabricPromise = null;

export async function loadFabric() {
    if (!_fabricPromise) {
        _fabricPromise = import(
            "/social_marketing/static/lib/fabric/index.min.js"
        ).then((mod) => mod.default || window.fabric);
    }
    return _fabricPromise;
}
