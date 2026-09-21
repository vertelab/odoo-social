/** @odoo-module **/

import { Component, markup, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { FileUploader } from "@web/views/fields/file_handler";
import { loadFabric } from "@social_image_creator/lib/fabric_loader";
import {
    EXTRA_PROPS,
    HISTORY_LIMIT,
    applyCaseTransform,
    applyImageCoverFit,
    buildLayerDescriptors,
    computeAlignmentDeltas,
    computeAutofitFontSize,
    computeDisplayScale,
    computeDistributePositions,
    computeSmartSpacing,
    DASH_PRESETS,
    detectStrokePattern,
    gradientAngleToCoords,
    gradientRadialCoords,
    gradientToConfig,
    isEmptyBindingValue,
    moveItem,
    newLayerId,
    parseShadowColor,
    buildShadowColor,
    resolveTokens,
    restoreSceneProps,
    snapBoxFromRect,
    snapBoxToGuides,
    stashSceneProps,
    toHexColor,
    widestLine,
} from "@social_image_creator/js/dialog/social_image_editor_utils";
import {
    BASIC_SHAPES,
    PARAM_SHAPES,
    SHAPE_META,
    SHAPES,
    isImageType,
    isTextType,
} from "@social_image_creator/js/dialog/shape_library";
import {
    GOOGLE_FONTS,
    SYSTEM_FONTS,
    ensureFontLoaded,
    isGoogleFont,
    loadAllGoogleFontsCss,
} from "@social_image_creator/js/dialog/google_fonts";
import { searchIcons } from "@social_image_creator/js/dialog/icon_library";
import {
    COMPANY_BRAND_COLOR_FIELDS,
    collectBrandColors,
    collectBrandFonts,
} from "@social_image_creator/js/dialog/brand_assets";

const HISTORY_DEBOUNCE_MS = 500;
const AUTOSAVE_DEBOUNCE_MS = 1500;
const AUTOFIT_MIN_SIZE = 6;
// Snap threshold in SCREEN pixels (zoom-aware): 6px feels right at any
// zoom level. Hold Alt during drag to bypass snapping entirely.
const SNAP_THRESHOLD_PX = 6;

/**
 * Full-screen modal editor for `social.image.template` (design decision D4).
 *
 * Loads the primary variant's scene from the record, edits it on a Fabric
 * canvas (pixel-exact, CSS-scaled to fit) and autosaves the scene back
 * into the variant list plus a regenerated SVG master. Owns the layer
 * panel (topmost first) and a bounded undo/redo history of full scene
 * snapshots (decision D5).
 *
 * The dialog talks to the saved record through the ORM service; it is
 * only opened for saved records (the launcher button is disabled on new
 * records, design.md "Modal editor + unsaved record").
 */
export class SocialImageEditorDialog extends Component {
    static template = "social.SocialImageEditorDialog";
    static components = { FileUploader };
    static props = {
        resModel: String,
        resId: Number,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.canvasRef = useRef("canvasRef");
        this.canvasAreaRef = useRef("canvasAreaRef");
        this.renameInputRef = useRef("renameInputRef");
        this.fontPickerRef = useRef("fontPickerRef");
        this.shapesMenuRef = useRef("shapesMenuRef");
        this.state = useState({
            busy: true,
            fabricVersion: null,
            message: "",
            templateName: "",
            variantName: "",
            layers: [],
            selectedIds: [],
            hasSelection: false,
            editingLayerId: null,
            renameDraft: "",
            dropTargetIndex: null,
            canUndo: false,
            canRedo: false,
            saveState: "clean",
            opacity: 100,
            selectionCount: 0,
            // Object toolbox
            penMode: false,
            shapesOpen: false,
            // Properties panel
            inspector: this._emptyInspector(),
            shapeParamDefs: [],
            // Font picker
            fontPickerOpen: false,
            fontFilter: "",
            fontLoading: false,
            fontsCssLoaded: false,
            // Icon picker
            iconPickerOpen: false,
            iconFilter: "",
            iconColor: "#1a1a1a",
            // Media library (company-shared brand images)
            mediaPickerOpen: false,
            mediaFilter: "",
            mediaItems: [],
            mediaLoading: false,
            // Brand assets (colors from res.company fields, fonts from
            // the brand font registry; both empty until the glue module
            // or a customization provides them)
            brandColors: [],
            brandFonts: [],
            // Data binding (template model_id set): bindable fields feed
            // the Data panel chips; preview mode resolves tokens against
            // a picked record.
            bindingModel: null,
            bindingModelName: "",
            bindingFields: [],
            bindingFieldFilter: "",
            previewMode: false,
            previewBusy: false,
            previewSearch: "",
            previewResults: [],
            previewRecordId: null,
            previewRecordName: "",
        });

        this._fabric = null;
        this._canvas = null;
        this._variants = null;
        this._primaryIndex = 0;
        this._dimensions = { width: 1200, height: 630 };
        this._dirty = false;
        this._saving = false;
        this._history = { stack: [], cursor: -1, suspended: false };
        this._historyTimer = null;
        this._saveTimer = null;
        this._dragIndex = null;
        this._needsRenameFocus = false;
        this._penPoints = [];
        this._penRubber = null;
        this._penHandlers = null;
        // Snapping: guide lines + smart-spacing labels, drawn on contextTop.
        this._snapGuides = { lines: [], distances: [] };
        this._snapAlt = false;
        this._companyId = null;
        this._company = null;
        // Live preview: scene snapshot taken before binding resolution,
        // restored verbatim on exit.
        this._previewSnapshot = null;
        // True while restoring the token scene after preview: load events
        // must not mark the (unchanged) scene dirty.
        this._suppressDirty = false;

        this._boundOnKeyDown = (ev) => this._onKeyDown(ev);
        this._boundOnResize = () => this._applyDisplayScale();
        this._boundOnPointerDown = (ev) => this._onGlobalPointerDown(ev);
        this._boundOnSnapKeyDown = (ev) => {
            if (ev.key === "Alt") {
                this._snapAlt = true;
            }
        };
        this._boundOnSnapKeyUp = (ev) => {
            if (ev.key === "Alt") {
                this._snapAlt = false;
            }
        };
        this._boundOnObjectMoving = (ev) => this._onObjectMoving(ev);
        this._boundDrawSnapGuides = () => this._drawSnapGuides();
        this._boundClearSnapGuides = () => this._clearSnapGuides();

        onMounted(async () => {
            window.addEventListener("keydown", this._boundOnKeyDown);
            window.addEventListener("resize", this._boundOnResize);
            window.addEventListener("keydown", this._boundOnSnapKeyDown);
            window.addEventListener("keyup", this._boundOnSnapKeyUp);
            await this._init();
        });
        onWillUnmount(() => {
            window.removeEventListener("keydown", this._boundOnKeyDown);
            window.removeEventListener("resize", this._boundOnResize);
            window.removeEventListener("keydown", this._boundOnSnapKeyDown);
            window.removeEventListener("keyup", this._boundOnSnapKeyUp);
            window.removeEventListener("mousedown", this._boundOnPointerDown);
            this._unbindPen();
            clearTimeout(this._historyTimer);
            clearTimeout(this._saveTimer);
            if (this._canvas) {
                this._canvas.dispose();
                this._canvas = null;
            }
        });
        onPatched(() => {
            if (this._needsRenameFocus && this.renameInputRef.el) {
                this._needsRenameFocus = false;
                this.renameInputRef.el.focus();
                this.renameInputRef.el.select();
            }
        });
    }

    // ------------------------------------------------------------------
    // Init / load
    // ------------------------------------------------------------------

    async _init() {
        try {
            const [record] = await this.orm.read(
                this.props.resModel,
                [this.props.resId],
                ["name", "variants", "width", "height", "company_id", "model_id"]
            );
            await this._loadBrandContext(record);
            await this._loadBindingContext(record);
            this._variants = (record && record.variants) || null;
            if (!this._variants || !this._variants.length) {
                this._variants = [
                    {
                        name: "Primary",
                        width: (record && record.width) || 1200,
                        height: (record && record.height) || 630,
                        scene_json: "{}",
                        is_primary: true,
                    },
                ];
            }
            this._primaryIndex = Math.max(
                0,
                this._variants.findIndex((v) => v.is_primary)
            );
            const primary = this._variants[this._primaryIndex];
            this.state.templateName = (record && record.name) || "";
            this.state.variantName = primary.name || "Primary";
            this._dimensions = {
                width: Number(primary.width) || 1200,
                height: Number(primary.height) || 630,
            };
            await this._initCanvas(primary.scene_json || "{}");
        } catch (err) {
            this.state.message = `Editor failed to load: ${err.message || err}`;
        } finally {
            this.state.busy = false;
        }
    }

    async _initCanvas(sceneJson) {
        const fabric = await loadFabric();
        this._fabric = fabric;
        this.state.fabricVersion = fabric.version;
        const { width, height } = this._dimensions;
        this._canvas = new fabric.Canvas(this.canvasRef.el, {
            width,
            height,
            backgroundColor: "#ffffff",
            selection: true,
            enableRetinaScaling: true,
        });
        this._applyDisplayScale();
        this._canvas.on({
            "object:added": () => this._onCanvasChanged(),
            "object:modified": () => this._onCanvasChanged(),
            "object:removed": () => this._onCanvasChanged(),
            "selection:created": () => this._syncSelection(),
            "selection:updated": () => this._syncSelection(),
            "selection:cleared": () => this._syncSelection(),
            "editing:exited": (ev) => this._onTextEditingExited(ev),
        });
        // Alignment guides + smart spacing while dragging (ported from
        // render-engine-os): guides drawn on contextTop, cleared on
        // mouse up. Alt bypasses snapping via the window listeners.
        this._canvas.on("object:moving", this._boundOnObjectMoving);
        this._canvas.on("after:render", this._boundDrawSnapGuides);
        this._canvas.on("mouse:up", this._boundClearSnapGuides);
        let scene = {};
        try {
            scene = JSON.parse(sceneJson || "{}");
        } catch (_) {
            scene = {};
        }
        await this._loadSceneIntoCanvas(scene);
        // Derived text props (case transform, autofit) are part of the
        // render, so a freshly loaded scene gets them applied up front.
        this._applyTextPropsToAll();
        // Baseline snapshot so undo can return to the loaded state.
        this._pushHistory();
        this._syncLayers();
        this._syncSelection();
    }

    /**
     * loadFromJSON with custom-prop stashing: see stashSceneProps for why
     * object-valued `_`-props are held aside during enlivening.
     */
    async _loadSceneIntoCanvas(scene) {
        const { sanitized, stashed } = stashSceneProps(scene);
        this._canvas.clear();
        this._canvas.backgroundColor = "#ffffff";
        await this._canvas.loadFromJSON(sanitized);
        const objects = this._canvas.getObjects();
        restoreSceneProps(objects, stashed);
        for (const obj of objects) {
            if (!obj._layerId) {
                obj._layerId = newLayerId();
            }
            // Image filters serialize natively in the scene JSON; after
            // enlivening the filter instances are live again but the
            // filtered bitmap must be re-rendered once.
            if (isImageType(obj.type) && obj.filters && obj.filters.length) {
                obj.applyFilters();
            }
        }
        this._canvas.renderAll();
    }

    // ------------------------------------------------------------------
    // Brand assets and media library (spec: template editor "Brand assets
    // in the editor"). Colors come from brand color fields on the
    // template's company when such fields exist (none do in stock Odoo;
    // the agency glue module registers more providers via
    // brand_assets.js). The media library lists image attachments on the
    // company's templates plus the company logo.
    // ------------------------------------------------------------------

    /**
     * Load company, brand colors, brand fonts and the media item list.
     * Fully fail-soft: any ORM error leaves the corresponding editor
     * feature empty rather than breaking the editor load.
     *
     * @param {Object} record the template record as read in _init
     */
    async _loadBrandContext(record) {
        this._companyId =
            record && record.company_id ? record.company_id[0] : null;
        this._company = null;
        if (this._companyId) {
            try {
                // Only request brand color fields that actually exist;
                // stock Odoo has none, so this is normally just name+logo.
                const info = await this.orm.call("res.company", "fields_get", [
                    [],
                ]);
                const colorFields = COMPANY_BRAND_COLOR_FIELDS.filter(
                    (f) => info && info[f]
                );
                const companies = await this.orm.read(
                    "res.company",
                    [this._companyId],
                    ["name", "logo", ...colorFields]
                );
                this._company = (companies && companies[0]) || null;
            } catch (_) {
                this._company = null;
            }
        }
        this.state.brandColors = collectBrandColors(this._company);
        this.state.brandFonts = collectBrandFonts();
        await this._loadMediaItems();
    }

    // ------------------------------------------------------------------
    // Data binding (spec: data-binding; design D1: resolution happens in
    // Odoo, substitution in the editor preview / render service)
    // ------------------------------------------------------------------

    /**
     * Load the template's binding model and its bindable fields (feeds
     * the Data panel). Fail-soft: no binding model leaves the panel
     * empty and the rest of the editor untouched.
     *
     * @param {Object} record the template record as read in _init
     */
    async _loadBindingContext(record) {
        this.state.bindingModel = null;
        this.state.bindingModelName = "";
        this.state.bindingFields = [];
        if (!record || !record.model_id) {
            return;
        }
        this.state.bindingModel = record.model_id[0];
        try {
            const [meta] = await this.orm.read(
                "ir.model",
                [record.model_id[0]],
                ["model"]
            );
            this.state.bindingModelName = (meta && meta.model) || "";
            const fields = await this.orm.call(
                "social.image.template",
                "get_binding_fields",
                [[this.props.resId]]
            );
            this.state.bindingFields = fields || [];
        } catch (_) {
            this.state.bindingModelName = "";
            this.state.bindingFields = [];
        }
    }

    filteredBindingFields() {
        const f = this.state.bindingFieldFilter.toLowerCase().trim();
        if (!f) {
            return this.state.bindingFields;
        }
        return this.state.bindingFields.filter(
            (field) =>
                field.name.toLowerCase().includes(f) ||
                (field.field_description || "").toLowerCase().includes(f)
        );
    }

    /**
     * Binary fields only: the valid targets for an image `_dataBinding`.
     */
    bindingImageFields() {
        return this.state.bindingFields.filter((field) => field.type === "binary");
    }

    /**
     * Data panel chip click: insert a {{field}} token into the selected
     * text, or bind the selected image to the field.
     */
    onFieldChipClick(field) {
        if (this.state.inspector.isText) {
            this.onInsertToken(field.name);
        } else if (this.state.inspector.isImage) {
            this.onBindImageField(field.name);
        }
    }

    /**
     * Insert a {{field}} token at the cursor of the active text object.
     *
     * Fabric.js v6 quirk (ported from render-engine-os): while a textbox
     * is in editing mode, the real current text + cursor live on
     * `obj.hiddenTextarea`, not on `obj.text`. Reading obj.text and
     * writing back without also syncing hiddenTextarea means the next
     * keystroke fires hiddenTextarea's input handler, which reads the
     * pre-insert value and wipes the token. Read from hiddenTextarea
     * when editing, write to BOTH stores, and reposition the cursor.
     */
    onInsertToken(field) {
        const fc = this._canvas;
        const obj = fc && fc.getActiveObject();
        if (!obj || !isTextType(obj.type) || !field) {
            return;
        }
        const token = `{{${field}}}`;
        const wasEditing = !!obj.isEditing;
        const ta = wasEditing ? obj.hiddenTextarea : null;
        const sourceText = ta ? ta.value : (obj.text ?? "");
        const start = ta
            ? (ta.selectionStart ?? sourceText.length)
            : (typeof obj.selectionStart === "number"
                  ? obj.selectionStart
                  : sourceText.length);
        const end = ta
            ? (ta.selectionEnd ?? start)
            : (typeof obj.selectionEnd === "number" ? obj.selectionEnd : start);

        const newText = sourceText.slice(0, start) + token + sourceText.slice(end);
        const newCursor = start + token.length;

        obj.set("text", newText);

        if (wasEditing && ta) {
            ta.value = newText;
            try {
                ta.selectionStart = newCursor;
                ta.selectionEnd = newCursor;
            } catch (_) {}
            obj.selectionStart = newCursor;
            obj.selectionEnd = newCursor;
            try {
                obj._updateTextarea?.();
            } catch (_) {}
            try {
                obj.initDelayedCursor?.();
            } catch (_) {}
        } else {
            // Drop the user into editing right after the token so they can
            // keep typing static text without double-clicking (which would
            // word-select the token and a stray keystroke would wipe it).
            try {
                obj.enterEditing?.();
                obj.selectionStart = newCursor;
                obj.selectionEnd = newCursor;
                if (obj.hiddenTextarea) {
                    obj.hiddenTextarea.value = newText;
                    try {
                        obj.hiddenTextarea.selectionStart = newCursor;
                        obj.hiddenTextarea.selectionEnd = newCursor;
                    } catch (_) {}
                }
                obj.initDelayedCursor?.();
            } catch (_) {}
        }

        fc.renderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    /**
     * "Bind to field" dropdown for image layers: sets or clears
     * `_dataBinding: {field}`. An empty value hides the layer at render
     * time; the cover-fit re-fit keeps the new image inside the
     * design-time frame.
     */
    onDataBindingChange(ev) {
        this.onBindImageField(ev.target.value || null);
    }

    /**
     * Bind the selected image layer to a binary field. `field` null or
     * empty clears the binding.
     */
    onBindImageField(field) {
        const obj = this._canvas && this._canvas.getActiveObject();
        if (!obj || !isImageType(obj.type)) {
            return;
        }
        if (field) {
            obj._dataBinding = { field: field };
        } else {
            delete obj._dataBinding;
            if (obj._required && !obj._hideIfEmpty) {
                delete obj._required;
            }
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    /**
     * `_hideIfEmpty: {field}` on any layer: hidden when the resolved
     * value is empty. Empty option clears the rule.
     */
    onHideIfEmptyChange(ev) {
        const field = ev.target.value;
        for (const obj of this._selectedObjects()) {
            if (field) {
                obj._hideIfEmpty = { field: field };
            } else {
                delete obj._hideIfEmpty;
                if (obj._required && !obj._dataBinding) {
                    delete obj._required;
                }
            }
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    /**
     * `_required: {field}` on any layer: aborts the render with a clear
     * error when the value is empty. The checkbox binds to the same
     * field as the image binding or the hide-if-empty rule, whichever
     * the layer has.
     */
    onRequiredChange(ev) {
        const checked = ev.target.checked;
        for (const obj of this._selectedObjects()) {
            if (checked) {
                const field =
                    (obj._dataBinding && obj._dataBinding.field) ||
                    (obj._hideIfEmpty && obj._hideIfEmpty.field);
                if (field) {
                    obj._required = { field: field };
                }
            } else {
                delete obj._required;
            }
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    // ------------------------------------------------------------------
    // Live data preview (spec: template editor "Live data preview"):
    // snapshot the token scene, resolve bindings against a picked record
    // (resolution in Odoo, per design D1), mutate the live canvas, and
    // restore the exact token scene on exit.
    // ------------------------------------------------------------------

    async onTogglePreview() {
        if (this.state.previewMode) {
            await this._exitPreview();
        } else {
            await this._enterPreview();
        }
    }

    async onPreviewSearchInput(ev) {
        this.state.previewSearch = ev.target.value;
        await this._searchPreviewRecords(this.state.previewSearch);
    }

    async _searchPreviewRecords(term) {
        if (!this.state.bindingModelName) {
            this.state.previewResults = [];
            return;
        }
        try {
            const results = await this.orm.call(
                this.state.bindingModelName,
                "name_search",
                [term || ""],
                { limit: 20 }
            );
            this.state.previewResults = (results || []).map(([id, name]) => ({
                id,
                name,
            }));
        } catch (err) {
            this.state.previewResults = [];
            this.state.message = `Record search failed: ${err.message || err}`;
        }
    }

    async onPreviewRecordPicked(result) {
        this.state.previewRecordId = result.id;
        this.state.previewRecordName = result.name;
        this.state.previewResults = [];
        this.state.previewSearch = "";
        // Back to the exact token scene before applying the new record.
        if (this._previewSnapshot) {
            this._suppressDirty = true;
            try {
                await this._restoreSnapshot(this._previewSnapshot, {
                    persist: false,
                });
            } finally {
                this._suppressDirty = false;
            }
        }
        await this._applyPreviewBindings();
    }

    async _enterPreview() {
        const fc = this._canvas;
        if (!fc || this.state.previewMode || !this.state.bindingModelName) {
            return;
        }
        if (!this.state.previewRecordId) {
            await this._searchPreviewRecords("");
            const first = this.state.previewResults[0];
            this.state.previewResults = [];
            if (!first) {
                this.state.message = "No records found to preview.";
                return;
            }
            this.state.previewRecordId = first.id;
            this.state.previewRecordName = first.name;
        }
        this._previewSnapshot = this._captureScene();
        this._history.suspended = true;
        this.state.previewMode = true;
        this.state.previewSearch = "";
        this.state.previewResults = [];
        // Selection off so no edits land on the mutated canvas; they
        // would be wiped (silently) on restore anyway.
        fc.skipTargetFind = true;
        fc.selection = false;
        fc.discardActiveObject();
        this._syncSelection();
        await this._applyPreviewBindings();
    }

    async _applyPreviewBindings() {
        const fc = this._canvas;
        if (!fc || !this.state.previewRecordId) {
            return;
        }
        this.state.previewBusy = true;
        try {
            // Design D1: the binding values come from Odoo (same walker as
            // render_for_record), keyed by dotted field path. Binary fields
            // arrive as data URLs.
            const sceneJson = JSON.stringify(this._captureScene());
            const bindings =
                (await this.orm.call(
                    this.props.resModel,
                    "get_preview_bindings",
                    [[this.props.resId], this.state.previewRecordId],
                    { scene_json: sceneJson }
                )) || {};
            for (const obj of fc.getObjects()) {
                // Conditional visibility (any layer type).
                const hie = obj._hideIfEmpty;
                if (hie && hie.field && isEmptyBindingValue(bindings[hie.field])) {
                    obj.visible = false;
                    continue;
                }
                // Text tokens with pipe transforms.
                if (typeof obj.text === "string") {
                    const resolved = resolveTokens(obj.text, bindings);
                    if (resolved !== obj.text) {
                        obj.set("text", resolved);
                    }
                }
                // Bound images: swap src, then cover-fit back into the
                // design-time frame (frame captured BEFORE setSrc, since
                // setSrc resets width/height to the natural dims).
                if (
                    isImageType(obj.type) &&
                    obj._dataBinding &&
                    obj._dataBinding.field
                ) {
                    const value = bindings[obj._dataBinding.field];
                    if (typeof value === "string" && value) {
                        const frameW = obj.getScaledWidth();
                        const frameH = obj.getScaledHeight();
                        await new Promise((resolve) => {
                            try {
                                obj.setSrc(
                                    value,
                                    () => {
                                        applyImageCoverFit(obj, frameW, frameH);
                                        resolve();
                                    },
                                    { crossOrigin: "anonymous" }
                                );
                            } catch (_) {
                                resolve();
                            }
                        });
                    } else {
                        obj.visible = false;
                    }
                }
            }
            fc.renderAll();
        } catch (err) {
            this.state.message = `Preview failed: ${err.message || err}`;
            await this._exitPreview();
        } finally {
            this.state.previewBusy = false;
        }
    }

    async _exitPreview() {
        const fc = this._canvas;
        if (!fc || !this.state.previewMode) {
            return;
        }
        this.state.previewMode = false;
        fc.skipTargetFind = false;
        fc.selection = true;
        if (this._previewSnapshot) {
            this._suppressDirty = true;
            try {
                await this._restoreSnapshot(this._previewSnapshot, {
                    persist: false,
                });
            } finally {
                this._suppressDirty = false;
            }
        }
        this._previewSnapshot = null;
        this._history.suspended = false;
        fc.renderAll();
    }

    async _loadMediaItems() {
        this.state.mediaLoading = true;
        const items = [];
        try {
            if (this._company && this._company.logo) {
                items.push({
                    id: "company-logo",
                    name: "Company logo",
                    url: `/web/image/res.company/${this._companyId}/logo`,
                    kind: "logo",
                });
            }
            if (this._companyId) {
                const templates = await this.orm.search_read(
                    "social.image.template",
                    [["company_id", "=", this._companyId]],
                    ["id"]
                );
                const ids = (templates || []).map((t) => t.id);
                if (ids.length) {
                    const atts = await this.orm.search_read(
                        "ir.attachment",
                        [
                            ["res_model", "=", "social.image.template"],
                            ["res_id", "in", ids],
                            ["mimetype", "=like", "image/%"],
                        ],
                        ["name", "mimetype"],
                        { order: "id desc" }
                    );
                    for (const att of atts || []) {
                        items.push({
                            id: att.id,
                            name: att.name || "image",
                            url: `/web/content/${att.id}`,
                            kind: "image",
                        });
                    }
                }
            }
        } catch (_) {
            // Media library stays empty; the rest of the editor works.
        } finally {
            this.state.mediaItems = items;
            this.state.mediaLoading = false;
        }
    }

    filteredMediaItems() {
        const f = this.state.mediaFilter.toLowerCase().trim();
        if (!f) {
            return this.state.mediaItems;
        }
        return this.state.mediaItems.filter((item) =>
            (item.name || "").toLowerCase().includes(f)
        );
    }

    toggleMediaPicker() {
        this.state.mediaPickerOpen = !this.state.mediaPickerOpen;
        if (this.state.mediaPickerOpen) {
            this._loadMediaItems();
        } else {
            this.state.mediaFilter = "";
        }
    }

    onMediaPicked(item) {
        this.state.mediaPickerOpen = false;
        this.state.mediaFilter = "";
        this._addImageFromUrl(item.url, item.name);
    }

    /**
     * Upload a new image into the company media library: stored as an
     * ir.attachment on the current template (res_model
     * social.image.template), so it shows up for every template of this
     * company. The freshly uploaded image is inserted on the canvas too.
     *
     * @param {Object} file
     * @param {string} file.data base64 payload
     * @param {string} file.type mime type
     * @param {string} [file.name] original filename
     */
    async onMediaUploaded(file) {
        if (!this._assertEditable()) {
            return;
        }
        try {
            await this.orm.create("ir.attachment", [
                {
                    name: file.name || "image",
                    type: "binary",
                    datas: file.data,
                    mimetype: file.type,
                    res_model: this.props.resModel,
                    res_id: this.props.resId,
                },
            ]);
            await this._loadMediaItems();
            this._addImageFromDataUrl(
                `data:${file.type};base64,${file.data}`,
                file.name
            );
        } catch (err) {
            this.state.message = `Upload failed: ${err.message || err}`;
        }
    }

    // ------------------------------------------------------------------
    // Icon picker (Lucide, static library; spec: template editor object
    // toolbox, searchable + recolorable)
    // ------------------------------------------------------------------

    toggleIconPicker() {
        this.state.iconPickerOpen = !this.state.iconPickerOpen;
        if (!this.state.iconPickerOpen) {
            this.state.iconFilter = "";
        }
    }

    /**
     * Icons matching the current filter as {icon, svg} pairs, svg being
     * owl markup for the grid preview in the currently chosen color.
     */
    iconPreviews() {
        return searchIcons(this.state.iconFilter, 400).map((icon) => ({
            icon,
            svg: markup(
                `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="${this.state.iconColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icon.body}</svg>`
            ),
        }));
    }

    iconResultCount() {
        return searchIcons(this.state.iconFilter, 10000).length;
    }

    /**
     * Insert the picked icon as a recolorable SVG group: the Lucide body
     * is wrapped in an <svg> with the chosen stroke color, loaded via
     * fabric.loadSVGFromString and grouped. The group carries _iconName
     * so the fill inspector recolors the child strokes (Lucide icons are
     * stroke-drawn, a plain fill would render blobs) and _layerName so
     * the layer panel shows the icon name. Default size 96px, centered.
     */
    async insertIcon(icon) {
        const fabric = this._fabric;
        if (!fabric || !icon) {
            return;
        }
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 24 24" fill="none" stroke="${this.state.iconColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icon.body}</svg>`;
        try {
            const result = await fabric.loadSVGFromString(svg);
            const objs = ((result && result.objects) || []).filter(Boolean);
            const grp = fabric.util.groupSVGElements(
                objs,
                (result && result.options) || {}
            );
            const { width, height } = this._dimensions;
            grp.set({
                left: Math.floor((width - 96) / 2),
                top: Math.floor((height - 96) / 2),
            });
            grp._iconName = icon.name;
            grp._layerName = icon.name;
            this.state.iconPickerOpen = false;
            this.state.iconFilter = "";
            this._addObject(grp);
        } catch (err) {
            this.state.message = `Icon failed to load: ${err.message || err}`;
        }
    }

    /**
     * Apply a brand swatch color to one of the editor color targets, so
     * every color picker can share one swatch row. kind: fill, stroke,
     * gradientStart, gradientEnd, shadow, text, textBackground.
     */
    applyBrandColor(kind, color) {
        if (kind === "fill") {
            for (const obj of this._selectedObjects()) {
                this._setObjectFill(obj, color);
            }
            this._canvas.requestRenderAll();
            this._onCanvasChanged();
        } else if (kind === "stroke") {
            for (const obj of this._selectedObjects()) {
                obj.set("stroke", color);
            }
            this._canvas.requestRenderAll();
            this._onCanvasChanged();
        } else if (kind === "gradientStart") {
            this._applyGradient({ startColor: color });
        } else if (kind === "gradientEnd") {
            this._applyGradient({ endColor: color });
        } else if (kind === "shadow") {
            this.onShadowChange({ hex: color });
        } else if (kind === "text") {
            for (const obj of this._textObjects()) {
                obj.set("fill", color);
            }
            this._canvas.requestRenderAll();
            this._onCanvasChanged();
        } else if (kind === "textBackground") {
            for (const obj of this._textObjects()) {
                obj.set("textBackgroundColor", color === "#ffffff" ? "" : color);
            }
            this._canvas.requestRenderAll();
            this._syncSelection();
            this._onCanvasChanged();
        }
    }

    /**
     * Fill setter that understands icon groups: Lucide icons are stroke
     * drawn, so "fill" on an icon means recoloring every child stroke.
     */
    _setObjectFill(obj, color) {
        if (obj && obj._iconName && typeof obj.getObjects === "function") {
            for (const child of obj.getObjects()) {
                child.set("stroke", color);
            }
            return;
        }
        obj.set("fill", color);
    }

    // ------------------------------------------------------------------
    // Canvas geometry
    // ------------------------------------------------------------------

    _applyDisplayScale() {
        if (!this._canvas || !this.canvasRef.el) {
            return;
        }
        const { width, height } = this._dimensions;
        const area = this.canvasAreaRef.el;
        const scale = computeDisplayScale(
            width,
            height,
            area ? area.clientWidth - 32 : 0,
            area ? area.clientHeight - 32 : 0
        );
        // CSS-scale only; the backing store stays pixel-exact. This must go
        // through Fabric: it stacks an upper (interaction) canvas inside a
        // container on top of this element, and styling the lower canvas
        // alone leaves those two at full size, so clicks land beside the
        // objects they appear to hit.
        this._canvas.setDimensions(
            {
                width: `${Math.round(width * scale)}px`,
                height: `${Math.round(height * scale)}px`,
            },
            { cssOnly: true }
        );
    }

    // ------------------------------------------------------------------
    // Snapping: canvas/object guides + smart spacing while dragging
    // (ported from render-engine-os; pure math lives in the utils)
    // ------------------------------------------------------------------

    _onObjectMoving(ev) {
        const fc = this._canvas;
        const moving = ev.target;
        if (!fc || !moving) {
            return;
        }
        if (this._snapAlt) {
            this._snapGuides.lines = [];
            this._snapGuides.distances = [];
            return;
        }
        const box = snapBoxFromRect(moving.getBoundingRect());
        const others = [];
        for (const o of fc.getObjects()) {
            if (o === moving || o.visible === false) {
                continue;
            }
            others.push(snapBoxFromRect(o.getBoundingRect()));
        }
        const cw = fc.getWidth();
        const ch = fc.getHeight();
        const zoom = fc.getZoom() || 1;
        // Screen-pixel threshold converted into canvas units for this zoom.
        const threshold = SNAP_THRESHOLD_PX / zoom;

        const vCandidates = [
            { at: cw / 2 },
            { at: 0 },
            { at: cw },
        ];
        const hCandidates = [
            { at: ch / 2 },
            { at: 0 },
            { at: ch },
        ];
        for (const b of others) {
            vCandidates.push({ at: b.left }, { at: b.right }, { at: b.centerX });
            hCandidates.push({ at: b.top }, { at: b.bottom }, { at: b.centerY });
        }

        const snap = snapBoxToGuides(box, vCandidates, hCandidates, threshold);
        if (snap.dx) {
            moving.left = (moving.left || 0) + snap.dx;
        }
        if (snap.dy) {
            moving.top = (moving.top || 0) + snap.dy;
        }
        moving.setCoords();
        const lines = [];
        if (snap.vAt != null) {
            lines.push({ kind: "v", at: snap.vAt });
        }
        if (snap.hAt != null) {
            lines.push({ kind: "h", at: snap.hAt });
        }

        // Smart spacing, re-reading the box after the guide snap above.
        const box2 = snapBoxFromRect(moving.getBoundingRect());
        const spacing = computeSmartSpacing(box2, others, threshold);
        if (spacing.dx) {
            moving.left = (moving.left || 0) + spacing.dx;
        }
        if (spacing.dy) {
            moving.top = (moving.top || 0) + spacing.dy;
        }
        if (spacing.dx || spacing.dy) {
            moving.setCoords();
        }
        this._snapGuides.lines = lines;
        this._snapGuides.distances = spacing.distances;
    }

    _drawSnapGuides() {
        const fc = this._canvas;
        const ctx = fc && fc.contextTop;
        if (!ctx) {
            return;
        }
        fc.clearContext(ctx);
        const lines = this._snapGuides.lines;
        const distances = this._snapGuides.distances || [];
        if (!lines.length && !distances.length) {
            return;
        }
        const z = fc.getZoom();
        ctx.save();
        // Alignment guide lines (green).
        if (lines.length) {
            ctx.lineWidth = 1;
            ctx.strokeStyle = "#22c55e";
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            for (const g of lines) {
                if (g.kind === "v") {
                    ctx.moveTo(g.at * z, 0);
                    ctx.lineTo(g.at * z, fc.getHeight() * z);
                } else {
                    ctx.moveTo(0, g.at * z);
                    ctx.lineTo(fc.getWidth() * z, g.at * z);
                }
            }
            ctx.stroke();
            ctx.setLineDash([]);
        }
        // Spacing distance labels (pink, Photoshop convention).
        if (distances.length) {
            ctx.strokeStyle = "#ec4899";
            ctx.fillStyle = "#ec4899";
            ctx.lineWidth = 1;
            ctx.setLineDash([]);
            ctx.font = "10px ui-sans-serif, system-ui, sans-serif";
            ctx.textBaseline = "middle";
            const tickH = 6;
            for (const d of distances) {
                if (d.kind === "h") {
                    const y = d.y * z;
                    const x1 = d.from * z;
                    const x2 = d.to * z;
                    ctx.beginPath();
                    ctx.moveTo(x1, y);
                    ctx.lineTo(x2, y);
                    ctx.moveTo(x1, y - tickH / 2);
                    ctx.lineTo(x1, y + tickH / 2);
                    ctx.moveTo(x2, y - tickH / 2);
                    ctx.lineTo(x2, y + tickH / 2);
                    ctx.stroke();
                    const tx = (x1 + x2) / 2;
                    const w = ctx.measureText(d.label).width + 6;
                    ctx.fillStyle = "rgba(236,72,153,0.9)";
                    ctx.fillRect(tx - w / 2, y - 8, w, 14);
                    ctx.fillStyle = "#fff";
                    ctx.textAlign = "center";
                    ctx.fillText(d.label, tx, y - 1);
                    ctx.fillStyle = "#ec4899";
                } else {
                    const x = d.x * z;
                    const y1 = d.from * z;
                    const y2 = d.to * z;
                    ctx.beginPath();
                    ctx.moveTo(x, y1);
                    ctx.lineTo(x, y2);
                    ctx.moveTo(x - tickH / 2, y1);
                    ctx.lineTo(x + tickH / 2, y1);
                    ctx.moveTo(x - tickH / 2, y2);
                    ctx.lineTo(x + tickH / 2, y2);
                    ctx.stroke();
                    const ty = (y1 + y2) / 2;
                    const w = ctx.measureText(d.label).width + 6;
                    ctx.fillStyle = "rgba(236,72,153,0.9)";
                    ctx.fillRect(x - w / 2, ty - 7, w, 14);
                    ctx.fillStyle = "#fff";
                    ctx.textAlign = "center";
                    ctx.fillText(d.label, x, ty);
                    ctx.fillStyle = "#ec4899";
                }
            }
        }
        ctx.restore();
    }

    _clearSnapGuides() {
        this._snapGuides.lines = [];
        this._snapGuides.distances = [];
        const ctx = this._canvas && this._canvas.contextTop;
        if (ctx) {
            this._canvas.clearContext(ctx);
        }
    }

    // ------------------------------------------------------------------
    // Change propagation: layers sync, history, autosave
    // ------------------------------------------------------------------

    /**
     * False while live preview is on: the canvas holds resolved record
     * data that restoring would wipe, so structural edits are refused
     * with a hint instead of silently lost.
     */
    _assertEditable() {
        if (this.state.previewMode) {
            this.state.message = "Exit preview mode to edit the design.";
            return false;
        }
        return true;
    }

    _onCanvasChanged() {
        this._syncLayers();
        if (this.state.previewMode || this._suppressDirty) {
            // The resolved preview state (and the restore of the token
            // scene) must never reach autosave.
            return;
        }
        this._markDirty();
        this._scheduleHistory(HISTORY_DEBOUNCE_MS);
        this._scheduleSave(AUTOSAVE_DEBOUNCE_MS);
    }

    _syncLayers() {
        if (!this._canvas) {
            return;
        }
        this.state.layers = buildLayerDescriptors(
            this._canvas.getObjects(),
            SHAPE_META
        );
    }

    _emptyInspector() {
        return {
            isText: false,
            fontFamily: "",
            fontSize: 0,
            bold: false,
            italic: false,
            underline: false,
            textAlign: "left",
            fill: "#000000",
            textBackgroundColor: "",
            lineHeight: 1,
            charSpacing: 0,
            textTransform: "none",
            overflow: "none",
            stroke: "",
            strokeWidth: 0,
            strokePattern: "solid",
            cornerRadius: 0,
            isRect: false,
            isImage: false,
            isGroup: false,
            canFillWithImage: false,
            isFilledWithImage: false,
            gradient: null,
            shadow: {
                enabled: false,
                hex: "#000000",
                alpha: 30,
                blur: 8,
                offsetX: 4,
                offsetY: 4,
            },
            filters: { brightness: 0, contrast: 0, blur: 0, grayscale: false },
            shapeKind: null,
            shapeParams: null,
            // Data binding (Data panel)
            dataBindingField: null,
            hideIfEmptyField: null,
            required: false,
            bindField: null,
        };
    }

    _syncSelection() {
        if (!this._canvas) {
            return;
        }
        const active = this._canvas.getActiveObject();
        if (!active) {
            this.state.hasSelection = false;
            this.state.selectedIds = [];
            this.state.selectionCount = 0;
            this.state.opacity = 100;
            this.state.inspector = this._emptyInspector();
            this.state.shapeParamDefs = [];
            return;
        }
        const objects = active.getObjects ? active.getObjects() : [active];
        this.state.hasSelection = true;
        this.state.selectedIds = objects
            .map((obj) => obj._layerId)
            .filter((id) => !!id);
        this.state.selectionCount = objects.length;
        this.state.opacity = Math.round((active.opacity != null ? active.opacity : 1) * 100);
        // The inspector edits the active object itself; for an
        // ActiveSelection the first member drives the displayed values.
        const obj = objects[0] || active;
        const objType = (obj.type || "").toLowerCase();
        const inspector = this._emptyInspector();
        if (obj._iconName && typeof obj.getObjects === "function") {
            // Lucide icons are stroke drawn: the "fill" the user sees is
            // the first child's stroke color.
            const child = obj
                .getObjects()
                .find((c) => typeof c.stroke === "string" && c.stroke);
            inspector.fill = child ? toHexColor(child.stroke) : "#1a1a1a";
        } else {
            inspector.fill = typeof obj.fill === "string" ? toHexColor(obj.fill) : "#000000";
        }
        inspector.stroke = typeof obj.stroke === "string" ? toHexColor(obj.stroke) : "";
        inspector.strokeWidth = obj.strokeWidth || 0;
        inspector.strokePattern = detectStrokePattern(obj.strokeDashArray);
        inspector.isRect = objType === "rect";
        inspector.cornerRadius = obj.rx || 0;
        inspector.isImage = isImageType(obj.type);
        inspector.isGroup = objType === "group";
        inspector.isFilledWithImage = !!obj._fillImage;
        inspector.canFillWithImage =
            objects.length === 1 &&
            !isTextType(obj.type) &&
            !inspector.isImage &&
            !inspector.isGroup &&
            !inspector.isFilledWithImage &&
            this._isFillableShapeType(objType, obj);
        inspector.gradient = gradientToConfig(obj.fill);
        if (obj.shadow) {
            const parsed = parseShadowColor(obj.shadow.color);
            inspector.shadow = {
                enabled: true,
                hex: parsed.hex,
                alpha: parsed.alpha,
                blur: obj.shadow.blur ?? 8,
                offsetX: obj.shadow.offsetX ?? 4,
                offsetY: obj.shadow.offsetY ?? 4,
            };
        }
        if (inspector.isImage) {
            const filters = obj.filters || [];
            const findFilter = (name) =>
                filters.find(
                    (x) =>
                        x &&
                        (x.type === name ||
                            (x.constructor && x.constructor.name === name))
                );
            const b = findFilter("Brightness");
            const c = findFilter("Contrast");
            const bl = findFilter("Blur");
            const g = findFilter("Grayscale");
            inspector.filters = {
                brightness: b ? b.brightness ?? 0 : 0,
                contrast: c ? c.contrast ?? 0 : 0,
                blur: bl ? bl.blur ?? 0 : 0,
                grayscale: !!g,
            };
        }
        if (isTextType(obj.type)) {
            inspector.isText = true;
            inspector.fontFamily = obj.fontFamily || "Arial";
            inspector.fontSize = Math.round(obj.fontSize || 0);
            inspector.bold = obj.fontWeight === "bold" || obj.fontWeight === "700";
            inspector.italic = obj.fontStyle === "italic";
            inspector.underline = !!obj.underline;
            inspector.textAlign = obj.textAlign || "left";
            inspector.textBackgroundColor =
                typeof obj.textBackgroundColor === "string"
                    ? toHexColor(obj.textBackgroundColor)
                    : "";
            inspector.lineHeight = obj.lineHeight || 1;
            inspector.charSpacing = obj.charSpacing || 0;
            inspector.textTransform = obj._textTransform || "none";
            inspector.overflow = obj._overflow || "none";
        }
        if (!inspector.isImage && obj._shapeKind && PARAM_SHAPES[obj._shapeKind]) {
            const def = PARAM_SHAPES[obj._shapeKind];
            inspector.shapeKind = obj._shapeKind;
            inspector.shapeParams = { ...(obj._shapeParams || def.defaults) };
            this.state.shapeParamDefs = def.params;
        } else {
            this.state.shapeParamDefs = [];
        }
        // Data binding props (Data panel); `bindField` is what the
        // Required checkbox ties `_required` to.
        inspector.dataBindingField =
            (obj._dataBinding && obj._dataBinding.field) || null;
        inspector.hideIfEmptyField =
            (obj._hideIfEmpty && obj._hideIfEmpty.field) || null;
        inspector.required = !!(obj._required && obj._required.field);
        inspector.bindField =
            inspector.dataBindingField || inspector.hideIfEmptyField;
        this.state.inspector = inspector;
    }

    _selectedObjects() {
        if (!this._canvas) {
            return [];
        }
        const active = this._canvas.getActiveObject();
        if (!active) {
            return [];
        }
        return active.getObjects ? active.getObjects() : [active];
    }

    // ------------------------------------------------------------------
    // Toolbar: add objects (ported from the old inline field)
    // ------------------------------------------------------------------

    _addObject(obj) {
        if (!this._assertEditable()) {
            return;
        }
        obj._layerId = newLayerId();
        this._canvas.add(obj);
        this._canvas.setActiveObject(obj);
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    addText() {
        if (!this._fabric) {
            return;
        }
        const { Textbox } = this._fabric;
        const { width } = this._dimensions;
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
        const { width, height } = this._dimensions;
        this._addObject(
            new Rect({
                left: width * 0.1,
                top: height * 0.2,
                width: 300,
                height: 200,
                fill: "#4f46e5",
                rx: 0,
                ry: 0,
            })
        );
    }

    addCircle() {
        if (!this._fabric) {
            return;
        }
        const { Circle } = this._fabric;
        const { width, height } = this._dimensions;
        this._addObject(
            new Circle({
                left: width * 0.1,
                top: height * 0.2,
                radius: 100,
                fill: "#f59e0b",
            })
        );
    }

    /**
     * Ring: a Circle with no fill and a heavy stroke, so the stroke color
     * and width controls in the properties panel shape it directly.
     */
    addRing() {
        if (!this._fabric) {
            return;
        }
        const { Circle } = this._fabric;
        const { width, height } = this._dimensions;
        this._addObject(
            new Circle({
                left: width * 0.1,
                top: height * 0.2,
                radius: 100,
                fill: "",
                stroke: "#f59e0b",
                strokeWidth: 24,
            })
        );
    }

    addTriangle() {
        if (!this._fabric) {
            return;
        }
        const { Triangle } = this._fabric;
        const { width, height } = this._dimensions;
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
        const { width, height } = this._dimensions;
        this._addObject(
            new Line([width * 0.1, height * 0.4, width * 0.8, height * 0.4], {
                stroke: "#334155",
                strokeWidth: 6,
            })
        );
    }

    /**
     * Arrow: a Fabric Group of a shaft Line plus a Triangle head, treated
     * as one object for layer purposes. The group's _shapeKind tags it for
     * the layer label; the group round-trips through save/reload like any
     * other object (design D2 custom props).
     */
    addArrow() {
        if (!this._fabric) {
            return;
        }
        const { Group, Line, Triangle } = this._fabric;
        const { width, height } = this._dimensions;
        const stroke = Math.max(4, Math.floor(height * 0.008));
        const x1 = Math.floor(width * 0.2);
        const x2 = Math.floor(width * 0.7);
        const y = Math.floor(height * 0.5);
        const headSize = stroke * 4;
        const line = new Line([x1, y, x2 - headSize / 2, y], {
            stroke: "#334155",
            strokeWidth: stroke,
        });
        const head = new Triangle({
            left: x2 - headSize / 2,
            top: y,
            width: headSize,
            height: headSize,
            angle: 90,
            fill: "#334155",
            originX: "center",
            originY: "center",
        });
        const group = new Group([line, head], {
            left: Math.floor(width * 0.2),
            top: y,
        });
        group._shapeKind = "arrow";
        this._addObject(group);
    }

    /**
     * Insert a shape from the library (path-based or parametric) via
     * fabric.Path, scaled from the 100x100 viewBox to a default size.
     * Parametric shapes also carry { _shapeKind, _shapeParams } so the
     * properties panel can morph them live and reloads reconstruct them.
     */
    addShapeFromLibrary(kind) {
        if (!this._fabric) {
            return;
        }
        const meta = SHAPE_META[kind];
        if (!meta || !meta.path) {
            return;
        }
        const { Path } = this._fabric;
        const { width, height } = this._dimensions;
        const obj = new Path(meta.path, {
            left: Math.floor(width * 0.2),
            top: Math.floor(height * 0.2),
            fill: "#4f46e5",
        });
        const target = Math.floor(Math.min(width, height) * 0.3);
        obj.scaleX = obj.scaleY = target / 100;
        obj._shapeKind = kind;
        if (meta.parametric && meta.defaults) {
            obj._shapeParams = { ...meta.defaults };
        }
        this.state.shapesOpen = false;
        this._addObject(obj);
    }

    // ------------------------------------------------------------------
    // Pen tool: click to place anchors, rubber-band preview, Shift
    // constrains to 45 degrees, Enter or double-click closes the polygon,
    // Esc cancels. Ported from render-engine-os.
    // ------------------------------------------------------------------

    togglePen() {
        if (!this._assertEditable()) {
            return;
        }
        if (this.state.penMode) {
            this._cancelPen();
        } else {
            this._startPen();
        }
    }

    _startPen() {
        if (!this._canvas) {
            return;
        }
        this.state.shapesOpen = false;
        this.state.fontPickerOpen = false;
        this.state.penMode = true;
        this._penPoints = [];
        this._penRubber = null;
        this._canvas.selection = false;
        this._canvas.discardActiveObject();
        this._canvas.defaultCursor = "crosshair";
        this._canvas.hoverCursor = "crosshair";
        this._canvas.requestRenderAll();

        const onDown = (opt) => this._onPenDown(opt);
        const onMove = (opt) => this._onPenMove(opt);
        const onDblClick = () => this._finalizePen(true);
        this._canvas.on("mouse:down", onDown);
        this._canvas.on("mouse:move", onMove);
        this._canvas.on("mouse:dblclick", onDblClick);
        this._penHandlers = { onDown, onMove, onDblClick };
    }

    _unbindPen() {
        if (this._canvas && this._penHandlers) {
            this._canvas.off("mouse:down", this._penHandlers.onDown);
            this._canvas.off("mouse:move", this._penHandlers.onMove);
            this._canvas.off("mouse:dblclick", this._penHandlers.onDblClick);
        }
        this._penHandlers = null;
    }

    _onPenDown(opt) {
        const p = this._canvas.getPointer(opt.e);
        // Shift constrains the new segment to multiples of 45 degrees.
        const pts = this._penPoints;
        if (opt.e && opt.e.shiftKey && pts.length > 0) {
            const last = pts[pts.length - 1];
            const dx = p.x - last[0];
            const dy = p.y - last[1];
            const ang =
                Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
            const len = Math.hypot(dx, dy);
            p.x = last[0] + Math.cos(ang) * len;
            p.y = last[1] + Math.sin(ang) * len;
        }
        pts.push([p.x, p.y]);
        this._drawPenPreview();
    }

    _onPenMove(opt) {
        if (!this._penPoints.length) {
            return;
        }
        const p = this._canvas.getPointer(opt.e);
        this._penRubber = [p.x, p.y];
        this._drawPenPreview();
    }

    _drawPenPreview() {
        const fc = this._canvas;
        if (!fc) {
            return;
        }
        const ctx = fc.contextTop;
        if (!ctx) {
            return;
        }
        fc.clearContext(ctx);
        const pts = this._penPoints;
        if (!pts.length) {
            return;
        }
        const z = fc.getZoom();
        ctx.save();
        ctx.strokeStyle = "#3b82f6";
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(pts[0][0] * z, pts[0][1] * z);
        for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i][0] * z, pts[i][1] * z);
        }
        if (this._penRubber) {
            ctx.lineTo(this._penRubber[0] * z, this._penRubber[1] * z);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = "#ffffff";
        ctx.strokeStyle = "#3b82f6";
        ctx.lineWidth = 1.5;
        for (const [x, y] of pts) {
            ctx.fillRect(x * z - 4, y * z - 4, 8, 8);
            ctx.strokeRect(x * z - 4, y * z - 4, 8, 8);
        }
        ctx.restore();
    }

    _finalizePen(close) {
        const fc = this._canvas;
        const pts = this._penPoints;
        if (!fc || pts.length < 2) {
            this._cancelPen();
            return;
        }
        let d = `M ${pts[0][0].toFixed(2)} ${pts[0][1].toFixed(2)} `;
        for (let i = 1; i < pts.length; i++) {
            d += `L ${pts[i][0].toFixed(2)} ${pts[i][1].toFixed(2)} `;
        }
        if (close) {
            d += "Z";
        }
        const { Path } = this._fabric;
        const path = new Path(d, {
            fill: close ? "#4f46e5" : "",
            stroke: "#334155",
            strokeWidth: 2,
            strokeLineJoin: "round",
            strokeLineCap: "round",
        });
        this._addObject(path);
        this._cancelPen();
    }

    _cancelPen() {
        this._penPoints = [];
        this._penRubber = null;
        if (this._canvas) {
            const ctx = this._canvas.contextTop;
            if (ctx) {
                this._canvas.clearContext(ctx);
            }
            this._canvas.defaultCursor = "default";
            this._canvas.hoverCursor = "move";
            this._canvas.selection = true;
        }
        this._unbindPen();
        this.state.penMode = false;
    }

    toggleShapesMenu() {
        this.state.shapesOpen = !this.state.shapesOpen;
        this._syncGlobalPointerListener();
    }

    /**
     * One shared window mousedown listener for all open dropdowns;
     * attached while at least one menu is open.
     */
    _syncGlobalPointerListener() {
        if (this.state.fontPickerOpen || this.state.shapesOpen) {
            window.addEventListener("mousedown", this._boundOnPointerDown);
        } else {
            window.removeEventListener("mousedown", this._boundOnPointerDown);
        }
    }

    /**
     * Path-based + parametric shapes for the shapes menu. Primitives
     * (rect, circle, triangle, line, arrow) have dedicated toolbar
     * buttons and are excluded here.
     */
    menuShapes() {
        return SHAPES.filter((s) => s.path);
    }

    menuBasicShapes() {
        return BASIC_SHAPES;
    }

    /**
     * Insert one of the BASIC_SHAPES primitives from the shapes menu.
     */
    addBasicShape(kind) {
        const adders = {
            rect: () => this.addRect(),
            circle: () => this.addCircle(),
            ring: () => this.addRing(),
            triangle: () => this.addTriangle(),
            line: () => this.addLine(),
            arrow: () => this.addArrow(),
        };
        if (!adders[kind]) {
            return;
        }
        this.state.shapesOpen = false;
        this._syncGlobalPointerListener();
        adders[kind]();
    }

    /**
     * @param {Object} file
     * @param {string} file.data base64 payload
     * @param {string} file.type mime type
     */
    onImageUploaded(file) {
        if (!this._assertEditable()) {
            return;
        }
        this._addImageFromDataUrl(`data:${file.type};base64,${file.data}`);
    }

    onSvgUploaded(file) {
        if (!this._assertEditable()) {
            return;
        }
        this._addImageFromDataUrl(`data:${file.type};base64,${file.data}`);
    }

    _addImageFromUrl(url, name) {
        if (!this._fabric) {
            return;
        }
        const { width, height } = this._dimensions;
        this._fabric.FabricImage.fromURL(url, {
            left: width * 0.1,
            top: height * 0.1,
        })
            .then((img) => {
                const maxW = width * 0.6;
                const maxH = height * 0.6;
                const scale = Math.min(
                    1,
                    maxW / (img.width || 1),
                    maxH / (img.height || 1)
                );
                img.scale(scale);
                if (name) {
                    img._mediaName = name;
                }
                this._addObject(img);
            })
            .catch((err) => {
                this.state.message = `Image failed to load: ${err.message || err}`;
            });
    }

    _addImageFromDataUrl(url, name) {
        this._addImageFromUrl(url, name);
    }

    deleteSelected() {
        if (!this._canvas || !this._assertEditable()) {
            return;
        }
        for (const obj of this._selectedObjects()) {
            this._canvas.remove(obj);
        }
        this._canvas.discardActiveObject();
        this._canvas.requestRenderAll();
        this._syncSelection();
    }

    clearCanvas() {
        if (!this._canvas || !this._assertEditable()) {
            return;
        }
        for (const obj of [...this._canvas.getObjects()]) {
            this._canvas.remove(obj);
        }
        this._canvas.discardActiveObject();
        this._canvas.requestRenderAll();
        this._syncSelection();
    }

    onOpacityChange(ev) {
        const objects = this._selectedObjects();
        if (!objects.length) {
            return;
        }
        const value = Number(ev.target.value) / 100;
        for (const obj of objects) {
            obj.set("opacity", value);
        }
        this._canvas.requestRenderAll();
        this._onCanvasChanged();
    }

    // ------------------------------------------------------------------
    // Properties panel: common basics (fill, stroke, opacity)
    // ------------------------------------------------------------------

    onFillChange(ev) {
        this.applyBrandColor("fill", ev.target.value);
    }

    onStrokeColorChange(ev) {
        this.applyBrandColor("stroke", ev.target.value);
    }

    onStrokeWidthChange(ev) {
        const value = Math.max(0, Number(ev.target.value) || 0);
        for (const obj of this._selectedObjects()) {
            obj.set("strokeWidth", value);
        }
        this._canvas.requestRenderAll();
        this._onCanvasChanged();
    }

    /**
     * Stroke style: solid / dashed / dotted via strokeDashArray presets.
     * Dotted uses round line caps so the dots render as circles; the
     * other styles reset the cap to butt (deviation from the reference,
     * which left round caps on after switching away from dotted).
     */
    onStrokePatternChange(ev) {
        const kind = ev.target.value;
        const preset = kind in DASH_PRESETS ? DASH_PRESETS[kind] : null;
        for (const obj of this._selectedObjects()) {
            obj.set("strokeDashArray", preset);
            obj.set("strokeLineCap", kind === "dotted" ? "round" : "butt");
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    /**
     * Corner radius (rx/ry) for rectangles.
     */
    onCornerRadiusChange(ev) {
        const value = Math.max(0, Number(ev.target.value) || 0);
        for (const obj of this._selectedObjects()) {
            if ((obj.type || "").toLowerCase() === "rect") {
                obj.set("rx", value);
                obj.set("ry", value);
            }
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    // ------------------------------------------------------------------
    // Properties panel: gradient fill (ported GradientPanel)
    // ------------------------------------------------------------------

    _styleableObjects() {
        return this._selectedObjects().filter((obj) => {
            const t = (obj.type || "").toLowerCase();
            return t !== "activeselection";
        });
    }

    _gradientValue(key, fallback) {
        const g = this.state.inspector.gradient;
        return g && g[key] != null ? g[key] : fallback;
    }

    gradientType() {
        return this._gradientValue("type", "solid");
    }

    gradientStartColor() {
        return this._gradientValue("startColor", this.state.inspector.fill);
    }

    gradientEndColor() {
        return this._gradientValue("endColor", "#a855f7");
    }

    gradientStartPos() {
        return this._gradientValue("startPos", 0);
    }

    gradientEndPos() {
        return this._gradientValue("endPos", 1);
    }

    gradientAngle() {
        return this._gradientValue("angle", 0);
    }

    // Template helpers. OWL resolves every identifier in a template
    // expression on the component, so bare JS globals like Number() are
    // not available there ("ctx.Number is not a function").
    toNumber(value) {
        return Number(value);
    }

    formatFixed2(value) {
        const num = Number(value);
        return Number.isFinite(num) ? num.toFixed(2) : "";
    }

    gradientStartPosPct() {
        return Math.round(this.gradientStartPos() * 100);
    }

    gradientEndPosPct() {
        return Math.round(this.gradientEndPos() * 100);
    }

    gradientPreviewStyle() {
        const type = this.gradientType();
        const c1 = this.gradientStartColor();
        const c2 = this.gradientEndColor();
        const p1 = Math.round(this.gradientStartPos() * 100);
        const p2 = Math.round(this.gradientEndPos() * 100);
        let bg;
        if (type === "radial") {
            bg = `radial-gradient(circle, ${c1} ${p1}%, ${c2} ${p2}%)`;
        } else if (type === "linear") {
            // CSS linear-gradient measures from top; the panel angle
            // measures from the x axis, hence +90.
            bg = `linear-gradient(${(this.gradientAngle() || 0) + 90}deg, ${c1} ${p1}%, ${c2} ${p2}%)`;
        } else {
            bg = c1;
        }
        return `background: ${bg};`;
    }

    onGradientTypeChange(type) {
        this._applyGradient({ type });
    }

    onGradientStartColorChange(ev) {
        this._applyGradient({ startColor: ev.target.value });
    }

    onGradientEndColorChange(ev) {
        this._applyGradient({ endColor: ev.target.value });
    }

    onGradientStartPosChange(ev) {
        this._applyGradient({ startPos: Number(ev.target.value) });
    }

    onGradientEndPosChange(ev) {
        this._applyGradient({ endPos: Number(ev.target.value) });
    }

    onGradientAngleChange(ev) {
        this._applyGradient({ angle: Number(ev.target.value) });
    }

    /**
     * Apply a (partial) gradient config to every fill-capable selected
     * object. The gradient lives on obj.fill as a native fabric.Gradient
     * so it serializes into the scene JSON without extra plumbing.
     * type "solid" reverts to a plain color fill.
     */
    _applyGradient(patch) {
        const fc = this._canvas;
        if (!fc) {
            return;
        }
        const current = this.state.inspector.gradient || {
            type: "linear",
            angle: 0,
            startColor: this.state.inspector.fill || "#3b82f6",
            endColor: "#a855f7",
            startPos: 0,
            endPos: 1,
        };
        const cfg = { ...current, ...patch };
        const { Gradient } = this._fabric;
        for (const obj of this._styleableObjects()) {
            const w = obj.width || 100;
            const h = obj.height || 100;
            const colorStops = [
                { offset: cfg.startPos ?? 0, color: cfg.startColor || "#000000" },
                { offset: cfg.endPos ?? 1, color: cfg.endColor || "#ffffff" },
            ];
            if (cfg.type === "linear") {
                obj.set(
                    "fill",
                    new Gradient({
                        type: "linear",
                        coords: gradientAngleToCoords(cfg.angle ?? 0, w, h),
                        colorStops,
                    })
                );
            } else if (cfg.type === "radial") {
                obj.set(
                    "fill",
                    new Gradient({
                        type: "radial",
                        coords: gradientRadialCoords(w, h),
                        colorStops,
                    })
                );
            } else {
                obj.set("fill", cfg.startColor || "#cccccc");
            }
        }
        fc.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    // ------------------------------------------------------------------
    // Properties panel: drop shadow (ported ShadowPanel)
    // ------------------------------------------------------------------

    onShadowToggle(ev) {
        const enabled = ev.target.checked;
        for (const obj of this._styleableObjects()) {
            obj.shadow = enabled
                ? new this._fabric.Shadow({
                      color: "rgba(0,0,0,0.3)",
                      blur: 8,
                      offsetX: 4,
                      offsetY: 4,
                  })
                : null;
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    /**
     * @param {Object} patch subset of {hex, alpha, blur, offsetX, offsetY}
     */
    onShadowChange(patch) {
        for (const obj of this._styleableObjects()) {
            if (!obj.shadow) {
                obj.shadow = new this._fabric.Shadow({
                    color: "rgba(0,0,0,0.3)",
                    blur: 8,
                    offsetX: 4,
                    offsetY: 4,
                });
            }
            const next = { ...parseShadowColor(obj.shadow.color), ...patch };
            obj.shadow.color = buildShadowColor(next.hex, next.alpha);
            if (next.blur !== undefined) {
                obj.shadow.blur = next.blur;
            }
            if (next.offsetX !== undefined) {
                obj.shadow.offsetX = next.offsetX;
            }
            if (next.offsetY !== undefined) {
                obj.shadow.offsetY = next.offsetY;
            }
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    // ------------------------------------------------------------------
    // Properties panel: raster image filters (ported ImageFiltersPanel)
    // ------------------------------------------------------------------

    /**
     * @param {string} kind brightness|contrast|grayscale|blur
     */
    onImageFilterChange(kind, value) {
        const f = this._fabric && this._fabric.filters;
        if (!f) {
            return;
        }
        const defs = {
            brightness: {
                ctor: f.Brightness,
                type: "Brightness",
                options: { brightness: value },
                enabled: value !== 0,
            },
            contrast: {
                ctor: f.Contrast,
                type: "Contrast",
                options: { contrast: value },
                enabled: value !== 0,
            },
            grayscale: {
                ctor: f.Grayscale,
                type: "Grayscale",
                options: {},
                enabled: !!value,
            },
            blur: {
                ctor: f.Blur,
                type: "Blur",
                options: { blur: value },
                enabled: value > 0,
            },
        };
        const def = defs[kind];
        if (!def) {
            return;
        }
        for (const obj of this._selectedObjects()) {
            if (!isImageType(obj.type)) {
                continue;
            }
            obj.filters = (obj.filters || []).filter(
                (x) => !(x instanceof def.ctor) && x.type !== def.type
            );
            if (def.enabled) {
                obj.filters.push(new def.ctor(def.options));
            }
            obj.applyFilters();
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    // ------------------------------------------------------------------
    // Properties panel: shape filled with image (ported from
    // render-engine-os ~3977) + revert to color
    // ------------------------------------------------------------------

    /**
     * True for shape types that can be rebuilt as an image clipPath:
     * the primitives, path-based library shapes (known path) and
     * parametric shapes; ad-hoc pen paths carry their path data on the
     * object itself and are handled via that.
     */
    _isFillableShapeType(type, obj) {
        if (type === "rect" || type === "circle" || type === "triangle") {
            return true;
        }
        if (type === "path") {
            if (obj._shapeKind && SHAPE_META[obj._shapeKind]) {
                return true;
            }
            return !!obj.path;
        }
        return false;
    }

    /**
     * Replace the active shape with an uploaded image clipped to the
     * shape's outline. The image cover-fits the shape's bounding box;
     * the clip compensates for the host scale so the mask keeps the
     * original on-canvas size. The new image carries _fillImage plus
     * the shape's identity props so the layer label and revert work.
     *
     * @param {Object} file
     * @param {string} file.data base64 payload
     * @param {string} file.type mime type
     * @param {string} [file.name] original filename
     */
    async onShapeFillImage(file) {
        const fc = this._canvas;
        const obj = fc && fc.getActiveObject();
        if (!fc || !obj || obj.getObjects || !this._assertEditable()) {
            return;
        }
        const type = (obj.type || "").toLowerCase();
        if (isTextType(type) || isImageType(type) || type === "line") {
            return;
        }
        const r = obj.getBoundingRect();
        const cx = r.left + r.width / 2;
        const cy = r.top + r.height / 2;
        // Effective shape scale BEFORE the clip is built; needed to
        // compute the host/clip ratio below.
        const srcScaleX = obj.scaleX || 1;
        const srcScaleY = obj.scaleY || 1;

        // ClipPath shape mirroring the source. ClipPaths render in the
        // host's local coord space relative to the host center; we set
        // clip.scale = src.scale / host.scale after the cover-fit scale
        // is known so the mask comes out at the original display size.
        let clip = null;
        if (type === "rect") {
            clip = new this._fabric.Rect({
                width: obj.width,
                height: obj.height,
                rx: obj.rx || 0,
                ry: obj.ry || 0,
                originX: "center",
                originY: "center",
            });
        } else if (type === "circle") {
            clip = new this._fabric.Circle({
                radius: obj.radius,
                originX: "center",
                originY: "center",
            });
        } else if (type === "triangle") {
            clip = new this._fabric.Triangle({
                width: obj.width,
                height: obj.height,
                originX: "center",
                originY: "center",
            });
        } else if (type === "path") {
            // Parametric shapes rebuild from their current params so a
            // morphed star clips as the morphed star; plain library
            // paths use the catalog path; pen paths use their own data.
            const paramDef =
                obj._shapeKind && PARAM_SHAPES[obj._shapeKind]
                    ? PARAM_SHAPES[obj._shapeKind]
                    : null;
            const d = paramDef
                ? paramDef.build(obj._shapeParams || paramDef.defaults)
                : (obj._shapeKind &&
                      SHAPE_META[obj._shapeKind] &&
                      SHAPE_META[obj._shapeKind].path) ||
                  null;
            if (d) {
                clip = new this._fabric.Path(d, {
                    originX: "center",
                    originY: "center",
                });
            } else if (obj.path) {
                clip = new this._fabric.Path(obj.path, {
                    originX: "center",
                    originY: "center",
                });
            }
        }
        if (!clip) {
            this.state.message = "Fill with image is not supported for this shape.";
            return;
        }

        try {
            const url = `data:${file.type};base64,${file.data}`;
            const img = await this._fabric.FabricImage.fromURL(url);
            const naturalW = img.width || r.width;
            const naturalH = img.height || r.height;
            // Cover-fit: scale up to fully cover the bounding box, the
            // clip crops the rest.
            const scale = Math.max(r.width / naturalW, r.height / naturalH);
            clip.scaleX = srcScaleX / scale;
            clip.scaleY = srcScaleY / scale;
            img.set({
                left: cx,
                top: cy,
                originX: "center",
                originY: "center",
                scaleX: scale,
                scaleY: scale,
                clipPath: clip,
            });
            // Carry over identity + layer props; _fillImage marks the
            // image as a converted shape so "Revert to color" appears.
            img._layerId = obj._layerId;
            img._layerName = obj._layerName;
            img._mediaName = file.name || "image";
            img._shapeKind = obj._shapeKind || type;
            img._shapeParams = obj._shapeParams;
            img._hideIfEmpty = obj._hideIfEmpty || null;
            img._dataBinding = obj._dataBinding || null;
            img._required = obj._required || null;
            img._fillImage = true;
            fc.remove(obj);
            fc.add(img);
            fc.setActiveObject(img);
            fc.requestRenderAll();
            this._syncSelection();
            this._onCanvasChanged();
        } catch (err) {
            this.state.message = `Fill with image failed: ${err.message || err}`;
        }
    }

    /**
     * Revert a shape-image (fabric.Image with _fillImage) back to a
     * colored shape, reconstructed at the same bounding box. Ported
     * from render-engine-os; ad-hoc pen paths rebuild from the clip
     * path data the image still carries.
     */
    onRevertToShape() {
        const fc = this._canvas;
        const obj = fc && fc.getActiveObject();
        if (!fc || !obj || !obj._fillImage || !isImageType(obj.type)) {
            return;
        }
        const r = obj.getBoundingRect();
        const cx = r.left + r.width / 2;
        const cy = r.top + r.height / 2;
        const fill =
            typeof obj.fill === "string" && obj.fill ? toHexColor(obj.fill) : "#cccccc";
        const kind = obj._shapeKind;
        const meta = kind && SHAPE_META[kind] ? SHAPE_META[kind] : null;
        const paramDef = kind && PARAM_SHAPES[kind] ? PARAM_SHAPES[kind] : null;

        let fresh = null;
        if (paramDef) {
            const params = obj._shapeParams || paramDef.defaults;
            fresh = new this._fabric.Path(paramDef.build(params), {
                fill,
                originX: "center",
                originY: "center",
                left: cx,
                top: cy,
            });
            fresh.scaleX = fresh.scaleY = Math.min(r.width, r.height) / 100;
            fresh._shapeParams = params;
        } else if (meta && meta.path) {
            fresh = new this._fabric.Path(meta.path, {
                fill,
                originX: "center",
                originY: "center",
                left: cx,
                top: cy,
            });
            fresh.scaleX = r.width / 100;
            fresh.scaleY = r.height / 100;
        } else if (kind === "rect") {
            fresh = new this._fabric.Rect({
                width: r.width,
                height: r.height,
                fill,
                originX: "center",
                originY: "center",
                left: cx,
                top: cy,
            });
        } else if (kind === "circle") {
            fresh = new this._fabric.Circle({
                radius: Math.min(r.width, r.height) / 2,
                fill,
                originX: "center",
                originY: "center",
                left: cx,
                top: cy,
            });
        } else if (kind === "triangle") {
            fresh = new this._fabric.Triangle({
                width: r.width,
                height: r.height,
                fill,
                originX: "center",
                originY: "center",
                left: cx,
                top: cy,
            });
        } else if (kind === "path" && obj.clipPath && obj.clipPath.path) {
            fresh = new this._fabric.Path(obj.clipPath.path, {
                fill,
                originX: "center",
                originY: "center",
                left: cx,
                top: cy,
            });
            fresh.scaleX = (obj.clipPath.scaleX || 1) * (obj.scaleX || 1);
            fresh.scaleY = (obj.clipPath.scaleY || 1) * (obj.scaleY || 1);
        }
        if (!fresh) {
            this.state.message = "Revert to color is not supported for this shape.";
            return;
        }
        fresh._layerId = obj._layerId;
        fresh._layerName = obj._layerName;
        fresh._hideIfEmpty = obj._hideIfEmpty;
        fresh._dataBinding = obj._dataBinding;
        fresh._required = obj._required;
        fresh._shapeKind = kind;
        fc.remove(obj);
        fc.add(fresh);
        fc.setActiveObject(fresh);
        fc.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    // ------------------------------------------------------------------
    // Multi-select align / distribute / group (ported from
    // render-engine-os). Align targets the selection bounding box;
    // distribute equalizes gaps along one axis (3+ objects).
    // ------------------------------------------------------------------

    _alignRects() {
        return this._selectedObjects().map((o) => o.getBoundingRect());
    }

    alignSelection(kind) {
        const fc = this._canvas;
        const objs = this._selectedObjects();
        if (!fc || objs.length < 2 || !this._assertEditable()) {
            return;
        }
        const deltas = computeAlignmentDeltas(this._alignRects(), kind);
        objs.forEach((obj, i) => {
            obj.left = (obj.left || 0) + deltas[i].dx;
            obj.top = (obj.top || 0) + deltas[i].dy;
            obj.setCoords();
        });
        fc.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    distributeSelection(axis) {
        const fc = this._canvas;
        const objs = this._selectedObjects();
        if (!fc || objs.length < 3 || !this._assertEditable()) {
            return;
        }
        const rects = this._alignRects();
        const starts = computeDistributePositions(
            rects.map((r) => ({
                start: axis === "h" ? r.left : r.top,
                size: axis === "h" ? r.width : r.height,
            }))
        );
        const key = axis === "h" ? "left" : "top";
        objs.forEach((obj, i) => {
            const current = axis === "h" ? rects[i].left : rects[i].top;
            obj[key] = (obj[key] || 0) + (starts[i] - current);
            obj.setCoords();
        });
        fc.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    /**
     * Convert a multi-select (ActiveSelection) into a fabric.Group.
     * Children keep their identity props; the group becomes one layer.
     * Fires object:added/removed so undo history and autosave pick it
     * up through the usual _onCanvasChanged path.
     */
    groupSelection() {
        const fc = this._canvas;
        const active = fc && fc.getActiveObject();
        if (!fc || !active || !this._assertEditable()) {
            return;
        }
        const isSelection =
            (active.type || "").toLowerCase() === "activeselection";
        if (!isSelection) {
            return;
        }
        const items = active.getObjects();
        if (items.length < 2) {
            return;
        }
        // Snapshot identity props before grouping; children lose them
        // in the ActiveSelection -> Group conversion otherwise.
        const childMeta = items.map((o) => ({
            _layerId: o._layerId,
            _layerName: o._layerName,
            _mediaName: o._mediaName,
            _dataBinding: o._dataBinding,
            _hideIfEmpty: o._hideIfEmpty,
            _required: o._required,
            _shapeKind: o._shapeKind,
            _shapeParams: o._shapeParams,
            _textTransform: o._textTransform,
            _overflow: o._overflow,
        }));
        fc.discardActiveObject();
        const grp = new this._fabric.Group(items);
        items.forEach((o, i) => Object.assign(o, childMeta[i]));
        grp._layerId = newLayerId();
        fc.add(grp);
        fc.setActiveObject(grp);
        fc.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    /**
     * Decompose a fabric.Group back into individual layers at their
     * as-rendered absolute positions (the group's transform matrix is
     * multiplied into each child, ported from render-engine-os).
     */
    ungroupSelection() {
        const fc = this._canvas;
        const grp = fc && fc.getActiveObject();
        if (!fc || !grp || !this._assertEditable()) {
            return;
        }
        if ((grp.type || "").toLowerCase() !== "group") {
            return;
        }
        const util = this._fabric.util;
        const groupMatrix = grp.calcTransformMatrix();
        const items = [...grp._objects];
        grp._objects = [];
        fc.remove(grp);
        for (const obj of items) {
            const finalMatrix = util.multiplyTransformMatrices(
                groupMatrix,
                obj.calcTransformMatrix()
            );
            const opts = util.qrDecompose(finalMatrix);
            obj.set({
                left: opts.translateX,
                top: opts.translateY,
                scaleX: opts.scaleX,
                scaleY: opts.scaleY,
                angle: opts.angle,
                skewX: opts.skewX,
                skewY: opts.skewY,
                flipX: false,
                flipY: false,
                originX: "center",
                originY: "center",
            });
            obj.setCoords();
            if (!obj._layerId) {
                obj._layerId = newLayerId();
            }
            fc.add(obj);
        }
        // Re-create a multi-select so the user sees they're all selected.
        const sel = new this._fabric.ActiveSelection(items, { canvas: fc });
        fc.setActiveObject(sel);
        fc.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    // ------------------------------------------------------------------
    // Properties panel: typography
    // ------------------------------------------------------------------

    _textObjects() {
        return this._selectedObjects().filter((obj) => isTextType(obj.type));
    }

    /**
     * Apply the derived text props (case transform, autofit) to a single
     * text object. Idempotent, so it is safe to call on every render and
     * after every text edit. `set("text", ...)` fires a `changed` event
     * that can re-enter this path; the transform stabilizes after one
     * application, so the loop terminates.
     */
    _applyTextProps(obj) {
        if (!obj || typeof obj.text !== "string") {
            return;
        }
        const transformed = applyCaseTransform(obj.text, obj._textTransform);
        if (transformed !== obj.text) {
            obj.set("text", transformed);
        }
        if (obj._overflow === "autofit") {
            const size = computeAutofitFontSize({
                text: obj.text,
                boxWidth: obj.width || 0,
                startSize: obj.fontSize || 40,
                minSize: AUTOFIT_MIN_SIZE,
                measure: (fontSize, line) => this._measureTextWidth(obj, fontSize, line),
            });
            if (size !== obj.fontSize) {
                obj.set("fontSize", size);
            }
        }
    }

    _applyTextPropsToAll() {
        if (!this._canvas) {
            return;
        }
        for (const obj of this._canvas.getObjects()) {
            this._applyTextProps(obj);
        }
        this._canvas.requestRenderAll();
    }

    _onTextEditingExited(ev) {
        const obj = ev && ev.target;
        if (!obj || typeof obj.text !== "string") {
            return;
        }
        this._applyTextProps(obj);
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    /**
     * Measure the rendered width of one text line at a given font size
     * using the canvas 2D context, in the object's own font. Used by the
     * autofit calculation; the widest \n-separated line must fit the box.
     */
    _measureTextWidth(obj, fontSize, line) {
        const ctx = this._canvas && this._canvas.contextContainer;
        if (!ctx || typeof ctx.measureText !== "function") {
            return 0;
        }
        const family = obj.fontFamily || "sans-serif";
        const weight = obj.fontWeight || "normal";
        const style = obj.fontStyle || "normal";
        ctx.save();
        ctx.font = `${style} ${weight} ${fontSize}px ${family}`;
        const width = ctx.measureText(line != null ? line : widestLine(obj.text)).width;
        ctx.restore();
        return width;
    }

    // Font picker -----------------------------------------------------

    toggleFontPicker() {
        this.state.fontPickerOpen = !this.state.fontPickerOpen;
        if (this.state.fontPickerOpen) {
            // Lazy: inject the Google Fonts CSS link the first time the
            // picker opens, so the dropdown previews real faces (D11).
            loadAllGoogleFontsCss().then(() => {
                this.state.fontsCssLoaded = true;
            });
        } else {
            this.state.fontFilter = "";
        }
        this._syncGlobalPointerListener();
    }

    _onGlobalPointerDown(ev) {
        if (this.state.fontPickerOpen) {
            const el = this.fontPickerRef.el;
            if (el && !el.contains(ev.target)) {
                this.state.fontPickerOpen = false;
                this.state.fontFilter = "";
            }
        }
        if (this.state.shapesOpen) {
            const el = this.shapesMenuRef.el;
            if (el && !el.contains(ev.target)) {
                this.state.shapesOpen = false;
            }
        }
        this._syncGlobalPointerListener();
    }

    filteredSystemFonts() {
        const f = this.state.fontFilter.toLowerCase().trim();
        return SYSTEM_FONTS.filter((name) => !f || name.toLowerCase().includes(f));
    }

    filteredGoogleFonts() {
        const f = this.state.fontFilter.toLowerCase().trim();
        return GOOGLE_FONTS.filter((name) => !f || name.toLowerCase().includes(f));
    }

    /**
     * Pick a font family. Google Fonts load lazily: the shared CSS link is
     * injected once and document.fonts.load is awaited for the family
     * before the object switches, with a loading state in the picker.
     */
    async onFontFamilyChange(family) {
        const texts = this._textObjects();
        if (!texts.length) {
            return;
        }
        if (isGoogleFont(family)) {
            this.state.fontLoading = true;
            try {
                await ensureFontLoaded(family);
            } finally {
                this.state.fontLoading = false;
            }
        }
        for (const obj of texts) {
            obj.set("fontFamily", family);
            this._applyTextProps(obj);
        }
        this.state.fontPickerOpen = false;
        this.state.fontFilter = "";
        this._syncGlobalPointerListener();
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    onFontSizeChange(ev) {
        const size = Math.max(1, Number(ev.target.value) || 1);
        for (const obj of this._textObjects()) {
            obj.set("fontSize", size);
            this._applyTextProps(obj);
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    toggleBold() {
        const next = !this.state.inspector.bold;
        for (const obj of this._textObjects()) {
            obj.set("fontWeight", next ? "bold" : "normal");
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    toggleItalic() {
        const next = !this.state.inspector.italic;
        for (const obj of this._textObjects()) {
            obj.set("fontStyle", next ? "italic" : "normal");
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    toggleUnderline() {
        const next = !this.state.inspector.underline;
        for (const obj of this._textObjects()) {
            obj.set("underline", next);
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    onTextFillChange(ev) {
        this.applyBrandColor("text", ev.target.value);
    }

    onTextBackgroundChange(ev) {
        const value = ev.target.value;
        for (const obj of this._textObjects()) {
            // "#ffffff" doubles as "no background": an explicit white is
            // indistinguishable from none on the canvas, so store empty.
            obj.set("textBackgroundColor", value === "#ffffff" ? "" : value);
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    onTextAlignChange(align) {
        for (const obj of this._textObjects()) {
            obj.set("textAlign", align);
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    onLineHeightChange(ev) {
        const value = Math.max(0.5, Math.min(3, Number(ev.target.value) || 1));
        for (const obj of this._textObjects()) {
            obj.set("lineHeight", value);
        }
        this._canvas.requestRenderAll();
        this._onCanvasChanged();
    }

    onCharSpacingChange(ev) {
        const value = Math.max(-100, Math.min(800, Number(ev.target.value) || 0));
        for (const obj of this._textObjects()) {
            obj.set("charSpacing", value);
        }
        this._canvas.requestRenderAll();
        this._onCanvasChanged();
    }

    onTextTransformChange(ev) {
        const kind = ev.target.value;
        const value = kind === "none" ? undefined : kind;
        for (const obj of this._textObjects()) {
            obj._textTransform = value;
            this._applyTextProps(obj);
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    onOverflowChange(ev) {
        const autofit = ev.target.checked;
        for (const obj of this._textObjects()) {
            obj._overflow = autofit ? "autofit" : undefined;
            this._applyTextProps(obj);
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    // Parametric shape morph -------------------------------------------

    /**
     * Display value for a morph slider: integers without decimals, floats
     * with two decimals.
     */
    formatShapeParam(param) {
        const value = (this.state.inspector.shapeParams || {})[param.key];
        if (Number.isInteger(param.step)) {
            return String(Math.round(value ?? param.min));
        }
        return Number(value ?? 0).toFixed(2);
    }

    /**
     * Regenerate a parametric shape's path from updated params. Swaps the
     * fabric.Path for a fresh one (dodges bbox/dirty-flag pitfalls);
     * position, scale, rotation and all custom props carry over so the
     * layer feels continuous. Ported from render-engine-os.
     */
    onShapeParamChange(key, value) {
        const active = this._canvas && this._canvas.getActiveObject();
        if (!active || !active._shapeKind || !this._assertEditable()) {
            return;
        }
        const def = PARAM_SHAPES[active._shapeKind];
        if (!def) {
            return;
        }
        const merged = { ...(active._shapeParams || def.defaults), [key]: value };
        const d = def.build(merged);
        const { Path } = this._fabric;
        const fresh = new Path(d, {
            left: active.left,
            top: active.top,
            scaleX: active.scaleX,
            scaleY: active.scaleY,
            angle: active.angle,
            flipX: active.flipX,
            flipY: active.flipY,
            originX: active.originX,
            originY: active.originY,
            fill: active.fill,
            stroke: active.stroke,
            strokeWidth: active.strokeWidth,
            opacity: active.opacity,
        });
        fresh._layerId = active._layerId;
        fresh._layerName = active._layerName;
        fresh._mediaName = active._mediaName;
        fresh._dataBinding = active._dataBinding;
        fresh._hideIfEmpty = active._hideIfEmpty;
        fresh._required = active._required;
        fresh._shapeKind = active._shapeKind;
        fresh._shapeParams = merged;
        this._canvas.remove(active);
        this._canvas.add(fresh);
        this._canvas.setActiveObject(fresh);
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    // ------------------------------------------------------------------
    // Layer panel
    // ------------------------------------------------------------------

    _objectForLayer(layer) {
        if (!this._canvas || !layer || !layer.id) {
            return null;
        }
        return (
            this._canvas.getObjects().find((obj) => obj._layerId === layer.id) ||
            null
        );
    }

    onSelectLayer(layer) {
        const obj = this._objectForLayer(layer);
        if (!obj) {
            return;
        }
        this._canvas.setActiveObject(obj);
        this._canvas.requestRenderAll();
        this._syncSelection();
    }

    onToggleVisible(layer) {
        const obj = this._objectForLayer(layer);
        if (!obj || !this._assertEditable()) {
            return;
        }
        obj.set("visible", obj.visible === false);
        this._canvas.requestRenderAll();
        this._onCanvasChanged();
    }

    onToggleLock(layer) {
        const obj = this._objectForLayer(layer);
        if (!obj || !this._assertEditable()) {
            return;
        }
        if (obj.selectable === false) {
            obj.set("selectable", true);
            obj.set("evented", true);
        } else {
            obj.set("selectable", false);
            obj.set("evented", false);
            if (this._canvas.getActiveObject() === obj) {
                this._canvas.discardActiveObject();
            }
        }
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    async onDuplicateLayer(layer) {
        const obj = this._objectForLayer(layer);
        if (!obj || !this._assertEditable()) {
            return;
        }
        const cloned = await obj.clone([
            "_layerName",
            "_mediaName",
            "_shapeKind",
            "_shapeParams",
            "_textTransform",
            "_overflow",
            "_fillImage",
            "_iconName",
            "_dataBinding",
            "_hideIfEmpty",
            "_required",
        ]);
        cloned._layerId = newLayerId();
        cloned.left = (obj.left || 0) + 20;
        cloned.top = (obj.top || 0) + 20;
        this._canvas.add(cloned);
        this._canvas.setActiveObject(cloned);
        this._canvas.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    onDeleteLayer(layer) {
        const obj = this._objectForLayer(layer);
        if (!obj || !this._assertEditable()) {
            return;
        }
        this._canvas.remove(obj);
        this._canvas.discardActiveObject();
        this._canvas.requestRenderAll();
        this._syncSelection();
    }

    startRename(layer) {
        this.state.editingLayerId = layer.id;
        this.state.renameDraft = layer.label;
        this._needsRenameFocus = true;
    }

    commitRename(layer) {
        if (this.state.editingLayerId !== layer.id) {
            return;
        }
        this.state.editingLayerId = null;
        const obj = this._objectForLayer(layer);
        if (!obj || !this._assertEditable()) {
            return;
        }
        const name = this.state.renameDraft.trim();
        obj._layerName = name || undefined;
        this._canvas.requestRenderAll();
        this._syncLayers();
        this._onCanvasChanged();
    }

    cancelRename() {
        this.state.editingLayerId = null;
        this.state.renameDraft = "";
    }

    onRenameKeyDown(ev, layer) {
        if (ev.key === "Enter") {
            this.commitRename(layer);
        } else if (ev.key === "Escape") {
            ev.stopPropagation();
            this.cancelRename();
        }
    }

    // Native HTML5 drag and drop reorder (Fabric-independent, no dnd-kit).
    // The layer list is topmost-first; the canvas object stack is
    // bottom-first, so the reordered list is reversed before assignment.

    onLayerDragStart(ev, index) {
        this._dragIndex = index;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(index));
    }

    onLayerDragOver(ev, index) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        if (this.state.dropTargetIndex !== index) {
            this.state.dropTargetIndex = index;
        }
    }

    onLayerDragLeave() {
        this.state.dropTargetIndex = null;
    }

    onLayerDrop(ev, index) {
        ev.preventDefault();
        const from = this._dragIndex;
        this._dragIndex = null;
        this.state.dropTargetIndex = null;
        if (from === null || from === index) {
            return;
        }
        this._reorderLayer(from, index);
    }

    onLayerDragEnd() {
        this._dragIndex = null;
        this.state.dropTargetIndex = null;
    }

    _reorderLayer(fromIndex, toIndex) {
        if (!this._assertEditable()) {
            return;
        }
        const objects = this._canvas.getObjects();
        const byId = new Map(objects.map((obj) => [obj._layerId, obj]));
        const newLayers = moveItem(this.state.layers, fromIndex, toIndex);
        const reordered = [...newLayers]
            .reverse()
            .map((layer) => byId.get(layer.id))
            .filter((obj) => !!obj);
        if (reordered.length !== objects.length) {
            return;
        }
        this._canvas._objects = reordered;
        this._canvas.requestRenderAll();
        this._onCanvasChanged();
    }

    // ------------------------------------------------------------------
    // History (bounded snapshot stack, decision D5)
    // ------------------------------------------------------------------

    _captureScene() {
        // Derived text props are part of the render: apply them before
        // serializing so the saved scene and the SVG master match what the
        // user sees. Suspended so the resulting `changed` events cannot
        // schedule extra history/save cycles mid-capture.
        const wasSuspended = this._history.suspended;
        this._history.suspended = true;
        try {
            this._applyTextPropsToAll();
            const base = this._canvas.toObject();
            base.objects = this._canvas
                .getObjects()
                .map((obj) => obj.toObject(EXTRA_PROPS));
            return base;
        } finally {
            this._history.suspended = wasSuspended;
        }
    }

    _pushHistory() {
        const history = this._history;
        if (history.suspended || !this._canvas) {
            return;
        }
        const snapshot = this._captureScene();
        // Skip duplicate snapshots (idempotent renders).
        if (
            history.cursor >= 0 &&
            JSON.stringify(history.stack[history.cursor]) === JSON.stringify(snapshot)
        ) {
            return;
        }
        history.stack = history.stack.slice(0, history.cursor + 1);
        history.stack.push(snapshot);
        if (history.stack.length > HISTORY_LIMIT) {
            history.stack.shift();
        }
        history.cursor = history.stack.length - 1;
        this._syncHistoryState();
    }

    _scheduleHistory(delay) {
        if (this._history.suspended) {
            return;
        }
        clearTimeout(this._historyTimer);
        this._historyTimer = setTimeout(() => this._pushHistory(), delay);
    }

    _syncHistoryState() {
        this.state.canUndo = this._history.cursor > 0;
        this.state.canRedo =
            this._history.cursor < this._history.stack.length - 1;
    }

    /**
     * Restore a snapshot. `persist: false` is used by the live preview
     * (the restored scene is byte-identical to what is already saved, so
     * marking it dirty would only trigger a pointless write).
     */
    async _restoreSnapshot(snapshot, { persist = true } = {}) {
        if (!this._canvas || !snapshot) {
            return;
        }
        this._history.suspended = true;
        try {
            await this._loadSceneIntoCanvas(snapshot);
        } finally {
            // Release on the next tick so load-time events have all fired.
            setTimeout(() => {
                this._history.suspended = false;
            }, 50);
        }
        this._syncLayers();
        this._syncSelection();
        this._syncHistoryState();
        if (persist) {
            this._markDirty();
            this._scheduleSave(AUTOSAVE_DEBOUNCE_MS);
        }
    }

    undo() {
        const history = this._history;
        if (history.cursor <= 0) {
            return;
        }
        history.cursor -= 1;
        this._syncHistoryState();
        this._restoreSnapshot(history.stack[history.cursor]);
    }

    redo() {
        const history = this._history;
        if (history.cursor >= history.stack.length - 1) {
            return;
        }
        history.cursor += 1;
        this._syncHistoryState();
        this._restoreSnapshot(history.stack[history.cursor]);
    }

    // ------------------------------------------------------------------
    // Keyboard shortcuts, active while the dialog is open
    // ------------------------------------------------------------------

    _onKeyDown(ev) {
        const tag = (ev.target && ev.target.tagName || "").toLowerCase();
        const isEditing =
            tag === "input" ||
            tag === "textarea" ||
            (ev.target && ev.target.isContentEditable);
        if (isEditing) {
            return;
        }
        // Live preview: block every edit shortcut; Escape exits preview.
        if (this.state.previewMode) {
            if (ev.key === "Escape") {
                ev.preventDefault();
                this._exitPreview();
            }
            return;
        }
        // Don't intercept while the user edits text inside a Fabric Textbox.
        const active = this._canvas && this._canvas.getActiveObject();
        if (active && active.isEditing) {
            return;
        }
        if (this.state.penMode) {
            if (ev.key === "Enter") {
                ev.preventDefault();
                this._finalizePen(true);
            } else if (ev.key === "Escape") {
                ev.preventDefault();
                this._cancelPen();
            }
            return;
        }
        const key = ev.key.toLowerCase();
        const mod = ev.metaKey || ev.ctrlKey;
        if (key === "escape") {
            if (this.state.iconPickerOpen) {
                this.state.iconPickerOpen = false;
                this.state.iconFilter = "";
                return;
            }
            if (this.state.mediaPickerOpen) {
                this.state.mediaPickerOpen = false;
                this.state.mediaFilter = "";
                return;
            }
        }
        if (mod && key === "g" && ev.shiftKey) {
            ev.preventDefault();
            this.ungroupSelection();
        } else if (mod && key === "g") {
            ev.preventDefault();
            this.groupSelection();
        } else if (mod && key === "z" && !ev.shiftKey) {
            ev.preventDefault();
            this.undo();
        } else if (mod && ((key === "z" && ev.shiftKey) || key === "y")) {
            ev.preventDefault();
            this.redo();
        }
    }

    // ------------------------------------------------------------------
    // Autosave: scene JSON + SVG master back into the primary variant
    // ------------------------------------------------------------------

    _markDirty() {
        this._dirty = true;
        if (this.state.saveState !== "saving") {
            this.state.saveState = "dirty";
        }
    }

    _scheduleSave(delay) {
        clearTimeout(this._saveTimer);
        this._saveTimer = setTimeout(() => this._flushSave(), delay);
    }

    /**
     * Persist the live scene into the primary variant (variants JSONB, so
     * the legacy width/height/scene_json mirrors stay in sync via the
     * model's write override) and regenerate the SVG master with the same
     * DOMPurify + btoa pipeline as the old inline field.
     */
    async _flushSave() {
        if (this.state.previewMode) {
            // Never persist the resolved preview over the token scene.
            await this._exitPreview();
        }
        if (!this._canvas || !this._dirty || this._saving) {
            return;
        }
        this._saving = true;
        this.state.saveState = "saving";
        try {
            const sceneJson = JSON.stringify(this._captureScene());
            this._syncSelection();
            const variants = this._variants.map((variant, index) =>
                index === this._primaryIndex
                    ? { ...variant, scene_json: sceneJson }
                    : { ...variant }
            );
            let svg = this._canvas.toSVG();
            // Sanitize user-generated SVG before storing (defense in depth:
            // Fabric output is already safe, but never trust client markup
            // when the attachment may be served inline later).
            if (window.DOMPurify) {
                svg = window.DOMPurify.sanitize(svg, {
                    USE_PROFILES: { svg: true, svgFilters: true },
                });
            }
            const svgMaster = btoa(unescape(encodeURIComponent(svg)));
            await this.orm.write(this.props.resModel, [this.props.resId], {
                variants,
                svg_master: svgMaster,
            });
            this._variants = variants;
            this._dirty = false;
            this.state.saveState = "saved";
            this.state.message = "";
        } catch (err) {
            this.state.saveState = "error";
            this.state.message = `Autosave failed: ${err.message || err}`;
        } finally {
            this._saving = false;
        }
    }

    async close() {
        clearTimeout(this._saveTimer);
        if (this.state.previewMode) {
            await this._exitPreview();
        }
        await this._flushSave();
        this.props.close();
    }
}
