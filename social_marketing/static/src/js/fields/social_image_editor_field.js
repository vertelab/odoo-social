/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { FileUploader } from "@web/views/fields/file_handler";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { loadFabric } from "@social_marketing/lib/fabric_loader";

/**
 * Fabric.js canvas editor for `social.image.template`.
 *
 * The widget edits the template's scene (stored as Fabric JSON in
 * `scene_json`), exposes a small toolbar (text / shapes / image / SVG /
 * layers / clear), and on save writes both the scene JSON and an SVG
 * master (`svg_master`, base64) back to the record.
 *
 * Canvas pixel size is locked to the record's width/height; the element is
 * CSS-scaled to fit the form (Fabric maps pointer coordinates through the
 * bounding rect, so interaction stays correct at any display scale).
 */
export class SocialImageEditorField extends Component {
    static template = "social.SocialImageEditorField";
    static props = { ...standardFieldProps };

    setup() {
        this.canvasRef = useRef("canvasRef");
        this.state = useState({
            fabricVersion: null,
            busy: false,
            selectedId: null,
            hasSelection: false,
            message: "",
        });
        this._fabric = null;
        this._canvas = null;
        this._applying = false;
        this._dirty = false;

        onMounted(() => this._initCanvas());
        onWillUnmount(() => {
            this._commit();
            this._destroyCanvas();
        });

        useRecordObserver(() => {
            if (this._applying) {
                return;
            }
            this._onRecordChange();
        });
    }

    // ------------------------------------------------------------------
    // Canvas lifecycle
    // ------------------------------------------------------------------

    async _initCanvas() {
        this.state.busy = true;
        try {
            const fabric = await loadFabric();
            this._fabric = fabric;
            this.state.fabricVersion = fabric.version;
            const el = this.canvasRef.el;
            const { width, height } = this._dimensions();
            this._canvas = new fabric.Canvas(el, {
                width,
                height,
                backgroundColor: "#ffffff",
                selection: true,
                enableRetinaScaling: true,
            });
            this._applyDisplayScale();
            this._canvas.on({
                "selection:created": () => this._onSelectionChanged(),
                "selection:updated": () => this._onSelectionChanged(),
                "selection:cleared": () => this._onSelectionCleared(),
                "object:modified": () => this._markDirty(),
            });
            this._loadScene(this.props.record.data[this.props.name] || "{}");
            this._renderScene();
        } catch (err) {
            this.state.message = `Fabric failed to load: ${err.message || err}`;
        } finally {
            this.state.busy = false;
        }
    }

    _destroyCanvas() {
        if (this._canvas) {
            this._canvas.dispose();
            this._canvas = null;
        }
    }

    _onRecordChange() {
        if (!this._canvas) {
            return;
        }
        // Re-dimension when width/height changed on the record.
        const { width, height } = this._dimensions();
        if (width !== this._canvas.getWidth() || height !== this._canvas.getHeight()) {
            this._canvas.setDimensions({ width, height });
            this._applyDisplayScale();
            this._renderScene();
        }
    }

    _dimensions() {
        const width = Number(this.props.record.data.width) || 1200;
        const height = Number(this.props.record.data.height) || 630;
        return { width, height };
    }

    _applyDisplayScale() {
        if (!this._canvas || !this.canvasRef.el) {
            return;
        }
        const { width, height } = this._dimensions();
        // Fit the canvas into the form column (~760px), never upscale.
        const scale = Math.min(1, 760 / width);
        this.canvasRef.el.style.width = `${Math.round(width * scale)}px`;
        this.canvasRef.el.style.height = `${Math.round(height * scale)}px`;
        this.canvasRef.el.style.maxWidth = "100%";
    }

    _loadScene(json) {
        if (!this._canvas) {
            return;
        }
        let scene;
        try {
            scene = JSON.parse(json || "{}");
        } catch (_) {
            scene = {};
        }
        this._canvas.loadFromJSON(scene).then(() => {
            this._renderScene();
        });
    }

    _renderScene() {
        if (this._canvas) {
            this._canvas.requestRenderAll();
        }
    }

    // ------------------------------------------------------------------
    // Selection / dirty tracking
    // ------------------------------------------------------------------

    _onSelectionChanged() {
        const obj = this._canvas && this._canvas.getActiveObject();
        this.state.hasSelection = !!obj;
        this.state.selectedId = obj ? obj.id || obj.type : null;
    }

    _onSelectionCleared() {
        this.state.hasSelection = false;
        this.state.selectedId = null;
    }

    _markDirty() {
        this._dirty = true;
    }

    // ------------------------------------------------------------------
    // Toolbar actions
    // ------------------------------------------------------------------

    _addObject(obj) {
        obj.id = `obj_${Math.random().toString(36).slice(2, 9)}`;
        this._canvas.add(obj);
        this._canvas.setActiveObject(obj);
        this._markDirty();
        this._onSelectionChanged();
        this._renderScene();
    }

    addText() {
        if (!this._fabric) {
            return;
        }
        const { Textbox } = this._fabric;
        const { width } = this._dimensions();
        this._addObject(
            new Textbox("Text", {
                left: Math.max(20, width * 0.1),
                top: 60,
                width: Math.max(200, width * 0.6),
                fontSize: 48,
                fontFamily: "Arial, sans-serif",
                fill: "#1a1a1a",
                textAlign: "left",
            })
        );
    }

    addRect() {
        if (!this._fabric) {
            return;
        }
        const { Rect } = this._fabric;
        const { width, height } = this._dimensions();
        this._addObject(
            new Rect({
                left: width * 0.1,
                top: height * 0.2,
                width: 300,
                height: 200,
                fill: "#4f46e5",
            })
        );
    }

    addCircle() {
        if (!this._fabric) {
            return;
        }
        const { Circle } = this._fabric;
        const { width, height } = this._dimensions();
        this._addObject(
            new Circle({
                left: width * 0.1,
                top: height * 0.2,
                radius: 100,
                fill: "#f59e0b",
            })
        );
    }

    addTriangle() {
        if (!this._fabric) {
            return;
        }
        const { Triangle } = this._fabric;
        const { width, height } = this._dimensions();
        this._addObject(
            new Triangle({
                left: width * 0.1,
                top: height * 0.2,
                width: 220,
                height: 220,
                fill: "#10b981",
            })
        );
    }

    addLine() {
        if (!this._fabric) {
            return;
        }
        const { Line } = this._fabric;
        const { width, height } = this._dimensions();
        this._addObject(
            new Line([width * 0.1, height * 0.4, width * 0.8, height * 0.4], {
                stroke: "#334155",
                strokeWidth: 6,
            })
        );
    }

    /**
     * @param {Object} file
     * @param {string} file.data base64 payload
     * @param {string} file.type mime type
     */
    onImageUploaded(file) {
        if (!this._fabric) {
            return;
        }
        this._addImageFromDataUrl(`data:${file.type};base64,${file.data}`);
    }

    onSvgUploaded(file) {
        if (!this._fabric) {
            return;
        }
        this._addImageFromDataUrl(`data:${file.type};base64,${file.data}`);
    }

    _addImageFromDataUrl(url) {
        if (!this._fabric) {
            return;
        }
        const { width, height } = this._dimensions();
        this._fabric.FabricImage.fromURL(url, {
            left: width * 0.1,
            top: height * 0.1,
        })
            .then((img) => {
                // Fit the image within a reasonable frame on first add.
                const maxW = width * 0.6;
                const maxH = height * 0.6;
                const scale = Math.min(1, maxW / (img.width || 1), maxH / (img.height || 1));
                img.scale(scale);
                this._addObject(img);
            })
            .catch((err) => {
                this.state.message = `Image failed to load: ${err.message || err}`;
            });
    }

    deleteSelected() {
        if (!this._fabric) {
            return;
        }
        const obj = this._canvas && this._canvas.getActiveObject();
        if (obj) {
            this._canvas.remove(obj);
            this._markDirty();
            this._onSelectionCleared();
            this._renderScene();
        }
    }

    layerUp() {
        if (!this._fabric) {
            return;
        }
        const obj = this._canvas && this._canvas.getActiveObject();
        if (obj) {
            this._canvas.bringObjectForward(obj);
            this._markDirty();
            this._renderScene();
        }
    }

    layerDown() {
        if (!this._fabric) {
            return;
        }
        const obj = this._canvas && this._canvas.getActiveObject();
        if (obj) {
            this._canvas.sendObjectBackwards(obj);
            this._markDirty();
            this._renderScene();
        }
    }

    clearCanvas() {
        if (!this._canvas) {
            return;
        }
        for (const obj of [...this._canvas.getObjects()]) {
            this._canvas.remove(obj);
        }
        this._markDirty();
        this._onSelectionCleared();
        this._renderScene();
    }

    // ------------------------------------------------------------------
    // Save (scene JSON + SVG master)
    // ------------------------------------------------------------------

    async _commit() {
        if (!this._canvas || !this._dirty) {
            return;
        }
        this._applying = true;
        try {
            const updates = {};
            const sceneJson = JSON.stringify(this._canvas.toJSON());
            updates[this.props.name] = sceneJson;
            let svg = this._canvas.toSVG();
            // Sanitize user-generated SVG before storing (defense in depth:
            // Fabric output is already safe, but never trust client markup
            // when the attachment may be served inline later).
            if (window.DOMPurify) {
                svg = window.DOMPurify.sanitize(svg, {
                    USE_PROFILES: { svg: true, svgFilters: true },
                });
            }
            updates.svg_master = btoa(unescape(encodeURIComponent(svg)));
            this.props.record.update(updates);
            this.state.message = "";
            this._dirty = false;
        } finally {
            this._applying = false;
        }
    }

    onSave() {
        this._commit();
    }
}

SocialImageEditorField.props = { ...standardFieldProps };
SocialImageEditorField.components = { FileUploader };

export const socialImageEditorField = {
    component: SocialImageEditorField,
};

registry.category("fields").add("social_image_editor", socialImageEditorField);
