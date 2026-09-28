/** @odoo-module **/

import { Component, markup, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { FileUploader } from "@web/views/fields/file_handler";
import { loadFabric } from "@social_image_creator/lib/fabric_loader";
import {
    EXTRA_PROPS,
    HISTORY_LIMIT,
    applyImageCoverFit,
    buildLayerDescriptors,
    buildToken,
    computeAlignmentDeltas,
    computeAutofitFontSize,
    computeDisplayScale,
    computeDistributePositions,
    computeGridLines,
    computeInsertIndex,
    computeSmartSpacing,
    DASH_PRESETS,
    DEFAULT_GRID_SPACING,
    detectStrokePattern,
    gradientAngleToCoords,
    gradientRadialCoords,
    gradientToConfig,
    GRID_SPACING_PRESETS,
    isEmptyBindingValue,
    moveItem,
    newLayerId,
    opacityPercentFromFraction,
    parseShadowColor,
    buildShadowColor,
    resolveTextForPreview,
    resolveTokens,
    restoreSceneProps,
    roundToGrid,
    snapBoxFromRect,
    snapBoxToGuides,
    stashSceneProps,
    toHexColor,
    widestLine,
} from "@social_image_creator/js/dialog/social_image_editor_utils";
import {
    chartSpecToSvg,
    substituteChartSpec,
    CHART_SPEC_PROP,
} from "@social_image_creator/js/dialog/chart_library";
import {
    qrContentToMatrix,
    qrMatrixToRectSpecs,
    initQrGenerator,
    QR_PROP,
} from "@social_image_creator/js/dialog/qr_library";
import { loadQr } from "@social_image_creator/lib/qr_loader";
import {
    TABLE_PROP,
    addTableColumn,
    addTableRow,
    buildTableGroup,
    normalizeTableData,
    removeTableColumn,
    removeTableRow,
    starterTableData,
    syncTableTexts,
} from "@social_image_creator/js/dialog/table_library";
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
// Bottom message line (toast) auto-clear delay, unless dismissed earlier.
const MESSAGE_TIMEOUT_MS = 8000;
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
        this.gridMenuRef = useRef("gridMenuRef");
        this.insertDataRef = useRef("insertDataRef");
        this.chartMenuRef = useRef("chartMenuRef");
        this.tableMenuRef = useRef("tableMenuRef");
        this.qrMenuRef = useRef("qrMenuRef");
        const gridPrefs = this._readGridPrefs();
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
            // Grid overlay + snap-to-grid (design D1): drawn on
            // contextTop so exports stay clean; the prefs persist per
            // user via localStorage.
            gridVisible: gridPrefs.visible,
            gridSnap: gridPrefs.snap,
            gridSpacing: gridPrefs.spacing,
            gridMenuOpen: false,
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
            // Insert Dynamic Data stepped panel (design D2): model ->
            // field -> target. Reuses the binding contract (model_id,
            // get_binding_fields, {{field}} tokens, _dataBinding on
            // image layers); a template without model_id gets one
            // persisted through the normal ORM write in step 1.
            insertDataOpen: false,
            insertDataStep: "model",
            insertDataSearch: "",
            insertDataResults: [],
            insertDataFieldFilter: "",
            insertDataField: null,
            // Chart, table and QR elements (designs D3/D4/D5): toolbar
            // popovers for inserting, properties-panel editors for
            // reworking an existing element in place.
            chartMenuOpen: false,
            tableMenuOpen: false,
            tableRowsDraft: 3,
            tableColsDraft: 3,
            tableWidthDraft: 400,
            qrMenuOpen: false,
            qrContentDraft: "",
            qrError: "",
            // Set while a table is ungrouped for cell editing: the cell
            // textboxes are loose on the canvas and directly editable.
            tableEditing: null,
        });

        this._fabric = null;
        this._canvas = null;
        this._variants = null;
        this._primaryIndex = 0;
        this._dimensions = { width: 1200, height: 630 };
        this._dirty = false;
        this._saving = false;
        // Set when a close attempt hit a failed flush: the next close
        // asks for explicit discard (close-safety design D1).
        this._closeFailed = false;
        this._history = { stack: [], cursor: -1, suspended: false };
        this._historyTimer = null;
        this._saveTimer = null;
        this._messageTimer = null;
        this._dragIndex = null;
        this._needsRenameFocus = false;
        this._penPoints = [];
        this._penRubber = null;
        this._penHandlers = null;
        // Snapping: guide lines + smart-spacing labels, drawn on contextTop.
        this._snapGuides = { lines: [], distances: [] };
        this._snapAlt = false;
        // Shift during a move locks the drag to the dominant axis.
        this._snapShift = false;
        this._moveStart = null;
        this._companyId = null;
        this._company = null;
        // Live preview: scene snapshot taken before binding resolution,
        // restored verbatim on exit.
        this._previewSnapshot = null;
        // True while restoring the token scene after preview: load events
        // must not mark the (unchanged) scene dirty.
        this._suppressDirty = false;
        // Lazy QR generator wiring (lib/qr_loader -> qr_library).
        this._qrLibPromise = null;
        // Set while a table is ungrouped for cell editing (see D4
        // edit-isolation): original data, captured placement and the
        // loose children waiting to be reassembled.
        this._tableEdit = null;

        this._boundOnKeyDown = (ev) => this._onKeyDown(ev);
        this._boundOnResize = () => this._applyDisplayScale();
        this._boundOnPointerDown = (ev) => this._onGlobalPointerDown(ev);
        this._boundOnSnapKeyDown = (ev) => {
            if (ev.key === "Alt") {
                this._snapAlt = true;
            } else if (ev.key === "Shift") {
                this._snapShift = true;
            }
        };
        this._boundOnSnapKeyUp = (ev) => {
            if (ev.key === "Alt") {
                this._snapAlt = false;
            } else if (ev.key === "Shift") {
                this._snapShift = false;
            }
        };
        this._boundOnObjectMoving = (ev) => this._onObjectMoving(ev);
        this._boundOnObjectScaling = (ev) => this._onObjectScaling(ev);
        this._boundOnDragStart = (ev) => this._onDragStart(ev);
        this._boundDrawOverlays = () => this._drawOverlays();
        this._boundClearSnapGuides = () => {
            this._moveStart = null;
            this._clearSnapGuides();
        };

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
            clearTimeout(this._messageTimer);
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
                        name: _t("Primary"),
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
            this.state.variantName = primary.name || _t("Primary");
            this._dimensions = {
                width: Number(primary.width) || 1200,
                height: Number(primary.height) || 630,
            };
            await this._initCanvas(primary.scene_json || "{}");
        } catch (err) {
            this._showMessage(_t("Editor failed to load: %s", err.message || err));
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
            "mouse:dblclick": (ev) => this._onCanvasDblClick(ev),
        });
        // Alignment guides + smart spacing while dragging (ported from
        // render-engine-os): guides drawn on contextTop, cleared on
        // mouse up. Alt bypasses snapping via the window listeners.
        // The grid overlay paints through the same after:render hook,
        // so it can never enter the exported scene.
        this._canvas.on("object:moving", this._boundOnObjectMoving);
        this._canvas.on("object:scaling", this._boundOnObjectScaling);
        this._canvas.on("mouse:down", this._boundOnDragStart);
        this._canvas.on("mouse:down", (ev) => this._onCanvasPointerDown(ev));
        this._canvas.on("after:render", this._boundDrawOverlays);
        this._canvas.on("mouse:up", this._boundClearSnapGuides);
        let scene = {};
        try {
            scene = JSON.parse(sceneJson || "{}");
        } catch (_) {
            scene = {};
        }
        await this._loadSceneIntoCanvas(scene);
        // Stored scenes keep raw token text: case transform and autofit
        // apply at render time (render-parity design D3), so on load only
        // the edit-time autofit convenience for static text is refreshed.
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
            this.state.bindingFields = await this._fetchBindingFields();
        } catch (_) {
            this.state.bindingModelName = "";
            this.state.bindingFields = [];
        }
    }

    /**
     * Bindable fields of the template's current binding model, via the
     * model's get_binding_fields RPC. Shared by the initial load and
     * the Insert Dynamic Data flow after a model is picked.
     */
    async _fetchBindingFields() {
        const fields = await this.orm.call(
            "social.image.template",
            "get_binding_fields",
            [[this.props.resId]]
        );
        return fields || [];
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
        const token = buildToken(field);
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
    // Insert Dynamic Data (spec: template editor "Insert Dynamic Data
    // flow", design D2): a stepped popover panel in the toolbar. Step 1
    // model (persisted via the normal ORM write when the template had
    // none), step 2 field, step 3 target: token into text or binding
    // onto the active image layer. Everything reuses the binding
    // contract and the Data panel machinery.
    // ------------------------------------------------------------------

    insertDataLabel() {
        return _t("Insert Dynamic Data");
    }

    /**
     * Open/close the stepped panel. With a binding model configured the
     * flow starts at the field step; without one it starts at the model
     * step and preloads the model search.
     */
    toggleInsertDataPanel() {
        if (!this.state.insertDataOpen && !this._assertEditable()) {
            return;
        }
        this.state.insertDataOpen = !this.state.insertDataOpen;
        if (this.state.insertDataOpen) {
            this._resetInsertDataPanel();
            this.state.insertDataStep = this.state.bindingModel
                ? "field"
                : "model";
            if (!this.state.bindingModel) {
                this._searchInsertModels("");
            }
        }
        this._syncGlobalPointerListener();
    }

    closeInsertDataPanel() {
        this.state.insertDataOpen = false;
        this._resetInsertDataPanel();
        this._syncGlobalPointerListener();
    }

    _resetInsertDataPanel() {
        this.state.insertDataStep = "model";
        this.state.insertDataSearch = "";
        this.state.insertDataResults = [];
        this.state.insertDataFieldFilter = "";
        this.state.insertDataField = null;
    }

    async onInsertDataSearchInput(ev) {
        this.state.insertDataSearch = ev.target.value;
        await this._searchInsertModels(this.state.insertDataSearch);
    }

    /**
     * Step 1 search over ir.model. Non-transient and non-abstract
     * models only; the fields of the chosen model come from the
     * template's get_binding_fields either way.
     */
    async _searchInsertModels(term) {
        try {
            const results = await this.orm.call(
                "ir.model",
                "name_search",
                [
                    term || "",
                    [
                        ["transient", "=", false],
                        ["abstract", "=", false],
                    ],
                ],
                { limit: 20 }
            );
            this.state.insertDataResults = (results || []).map(([id, name]) => ({
                id,
                name,
            }));
        } catch (err) {
            this.state.insertDataResults = [];
            this._showMessage(_t("Model search failed: %s", err.message || err));
        }
    }

    /**
     * Step 1 pick: persist model_id on the template through the normal
     * ORM write, then load the model's fields and continue to step 2.
     */
    async onInsertModelPicked(result) {
        if (!result) {
            return;
        }
        try {
            await this.orm.write(this.props.resModel, [this.props.resId], {
                model_id: result.id,
            });
        } catch (err) {
            this._showMessage(
                _t("Could not set the binding model: %s", err.message || err)
            );
            return;
        }
        this.state.bindingModel = result.id;
        try {
            const [meta] = await this.orm.read("ir.model", [result.id], ["model"]);
            this.state.bindingModelName = (meta && meta.model) || "";
            this.state.bindingFields = await this._fetchBindingFields();
        } catch (err) {
            this.state.bindingModelName = "";
            this.state.bindingFields = [];
            this._showMessage(
                _t("Could not load the model fields: %s", err.message || err)
            );
        }
        this.state.insertDataSearch = "";
        this.state.insertDataResults = [];
        this.state.insertDataStep = "field";
    }

    onInsertDataContinueToFields() {
        if (this.state.bindingModel) {
            this.state.insertDataStep = "field";
        }
    }

    filteredInsertDataFields() {
        const f = this.state.insertDataFieldFilter.toLowerCase().trim();
        if (!f) {
            return this.state.bindingFields;
        }
        return this.state.bindingFields.filter(
            (field) =>
                field.name.toLowerCase().includes(f) ||
                (field.field_description || "").toLowerCase().includes(f)
        );
    }

    onInsertDataFieldPicked(field) {
        if (!field) {
            return;
        }
        this.state.insertDataField = field;
        this.state.insertDataStep = "target";
    }

    /**
     * The {{field}} token for the chosen field, shown as a preview in
     * the target step.
     */
    insertDataToken() {
        const field = this.state.insertDataField;
        return field ? buildToken(field.name) : "";
    }

    /**
     * Binary field chosen AND an image layer active: the binding action
     * is available (mirrors the Data panel chip rules).
     */
    insertDataCanBindImage() {
        const field = this.state.insertDataField;
        return !!(
            field &&
            field.type === "binary" &&
            this.state.inspector &&
            this.state.inspector.isImage
        );
    }

    onInsertDataStepBack() {
        if (this.state.insertDataStep === "target") {
            this.state.insertDataStep = "field";
        } else if (this.state.insertDataStep === "field") {
            this.state.insertDataStep = "model";
        }
    }

    /**
     * Target step, text action: insert the token into the active text
     * object (at the caret while editing), or create a new text layer
     * holding the token at the canvas center.
     */
    onInsertDataTokenClick() {
        const field = this.state.insertDataField;
        if (!field) {
            return;
        }
        const active = this._canvas && this._canvas.getActiveObject();
        if (active && isTextType(active.type)) {
            this.onInsertToken(field.name);
        } else {
            this._addTokenTextbox(field.name);
        }
        this.closeInsertDataPanel();
    }

    _addTokenTextbox(fieldName) {
        if (!this._fabric) {
            return;
        }
        const { Textbox } = this._fabric;
        const { width, height } = this._dimensions;
        const boxWidth = Math.min(Math.max(200, Math.round(width * 0.25)), width * 0.8);
        this._addObject(
            new Textbox(buildToken(fieldName), {
                left: Math.round((width - boxWidth) / 2),
                top: Math.round(height / 2) - 24,
                width: boxWidth,
                fontSize: 32,
                fontFamily: "Arial, sans-serif",
                fill: "#1a1a1a",
                textAlign: "center",
            })
        );
    }

    /**
     * Target step, image action: bind the active image layer to the
     * binary field (same code path as the Data panel dropdown).
     */
    onInsertDataBindImageClick() {
        const field = this.state.insertDataField;
        if (!field || field.type !== "binary") {
            return;
        }
        this.onBindImageField(field.name);
        this.closeInsertDataPanel();
    }

    // ------------------------------------------------------------------
    // Chart, table and QR elements (tasks 3.x-5.x, designs D3/D4/D5).
    // All three are fabric groups carrying a plain-data custom prop
    // (_chartSpec / _tableData / _qrContent, EXTRA_PROPS-persisted per
    // D6) and regenerate in place through one shared path that mirrors
    // render_service/dynamic_groups.mjs: preserve the placement
    // transform, carry the prop onto the new group, keep the z-order
    // slot.
    // ------------------------------------------------------------------

    // Shared regeneration plumbing -------------------------------------

    /**
     * Copy the placement transform from one layer to another (ported
     * from copyPlacement in render_service/dynamic_groups.mjs so editor
     * and render agree on what "in place" means).
     */
    _copyPlacement(src, dst) {
        const placement = {
            left: src.left,
            top: src.top,
            scaleX: src.scaleX ?? 1,
            scaleY: src.scaleY ?? 1,
            angle: src.angle ?? 0,
            flipX: !!src.flipX,
            flipY: !!src.flipY,
            originX: src.originX || "left",
            originY: src.originY || "top",
            opacity: src.opacity ?? 1,
            visible: src.visible !== false,
        };
        if (typeof dst.set === "function") {
            dst.set(placement);
        } else {
            Object.assign(dst, placement);
        }
        if (src.selectable === false) dst.selectable = false;
        if (src.evented === false) dst.evented = false;
        if (src._layerName) dst._layerName = src._layerName;
        dst.setCoords?.();
    }

    /**
     * Swap `oldGroup` for `replacement` where it sat (canvas or a parent
     * group), preserving z-order and layer identity, then reselect and
     * report the change. `replacement`'s custom prop must already be
     * attached by the caller (carried prop, idempotent regeneration).
     */
    _swapGroupInPlace(oldGroup, replacement) {
        const fc = this._canvas;
        if (!fc || !oldGroup || !replacement) {
            return;
        }
        if (oldGroup._layerId) {
            replacement._layerId = oldGroup._layerId;
        }
        this._copyPlacement(oldGroup, replacement);
        this._insertGroupReplacement(oldGroup, replacement);
        replacement.setCoords?.();
        if (!oldGroup.group) {
            fc.setActiveObject(replacement);
        }
        fc.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    /**
     * Preview-mode variant of the swap: same placement/z-order
     * semantics, but no selection or dirty side effects; the token
     * scene snapshot restores verbatim on preview exit.
     */
    _swapPreviewGroup(oldGroup, replacement) {
        if (!oldGroup || !replacement) {
            return;
        }
        if (oldGroup._layerId) {
            replacement._layerId = oldGroup._layerId;
        }
        this._copyPlacement(oldGroup, replacement);
        this._insertGroupReplacement(oldGroup, replacement);
        replacement.setCoords?.();
    }

    /**
     * Remove `oldGroup` from its container and insert `replacement` at
     * the same z-index (fabric 6 containers take insertAt(index, [])).
     */
    _insertGroupReplacement(oldGroup, replacement) {
        const container = oldGroup.group || this._canvas;
        if (!container) {
            return;
        }
        const siblings =
            typeof container.getObjects === "function" ? container.getObjects() : [];
        const index = Math.max(0, siblings.indexOf(oldGroup));
        container.remove(oldGroup);
        if (typeof container.insertAt === "function") {
            container.insertAt(index, [replacement]);
        } else {
            container.add(replacement);
        }
    }

    // Chart ------------------------------------------------------------

    /** The six chart types of the D3 contract, for picker and panel. */
    chartTypeOptions() {
        return [
            { type: "bar-v", label: _t("Vertical bar") },
            { type: "bar-h", label: _t("Horizontal bar") },
            { type: "line", label: _t("Line") },
            { type: "area", label: _t("Area") },
            { type: "pie", label: _t("Pie") },
            { type: "donut", label: _t("Donut") },
        ];
    }

    /**
     * Starter data table per the chart spec: three categories, one
     * series "Series 1" with values 10/20/15, on a 480x320 canvas.
     */
    starterChartSpec(type) {
        return {
            version: 1,
            type: type,
            title: "",
            categories: [_t("Category 1"), _t("Category 2"), _t("Category 3")],
            series: [{ name: _t("Series 1"), values: [10, 20, 15] }],
            options: { width: 480, height: 320 },
        };
    }

    toggleChartMenu() {
        if (!this.state.chartMenuOpen && !this._assertEditable()) {
            return;
        }
        this.state.chartMenuOpen = !this.state.chartMenuOpen;
        this._syncGlobalPointerListener();
    }

    /**
     * Build the fabric group for a chart spec: spec -> SVG via the
     * parity copy of render_service/chart_spec.mjs, SVG -> objects via
     * the same loadSVGFromString path as icons. The group carries the
     * spec on _chartSpec (design D6).
     */
    async _buildChartGroup(spec) {
        const svg = chartSpecToSvg(spec);
        const loaded = await this._fabric.loadSVGFromString(svg);
        const objects = ((loaded && loaded.objects) || []).filter(Boolean);
        let group = this._fabric.util.groupSVGElements(
            objects,
            (loaded && loaded.options) || {}
        );
        if (!group || group.type !== "group") {
            group = new this._fabric.Group(group ? [group] : []);
        }
        group[CHART_SPEC_PROP] = spec;
        return group;
    }

    /**
     * Toolbar insert: generate the starter chart of the picked type and
     * add it as one centered layer.
     */
    async insertChart(type) {
        if (!this._fabric || !this._assertEditable()) {
            return;
        }
        const spec = this.starterChartSpec(type);
        try {
            const group = await this._buildChartGroup(spec);
            const { width, height } = this._dimensions;
            group.set({
                originX: "left",
                originY: "top",
                left: Math.floor((width - (group.width || 480)) / 2),
                top: Math.floor((height - (group.height || 320)) / 2),
            });
            group._layerName = _t("Chart");
            this.state.chartMenuOpen = false;
            this._syncGlobalPointerListener();
            this._addObject(group);
        } catch (err) {
            this._showMessage(_t("Chart failed to generate: %s", err.message || err));
        }
    }

    /**
     * Regenerate a chart layer in place from a (possibly edited) spec:
     * carry the spec to the new group, keep the placement. Used by the
     * properties-panel chart editor and by preview resolution.
     */
    async _commitChartSpec(group, spec) {
        const replacement = await this._buildChartGroup(spec);
        replacement[CHART_SPEC_PROP] = spec;
        this._swapGroupInPlace(group, replacement);
    }

    _selectedChartGroup() {
        const obj = this._canvas && this._canvas.getActiveObject();
        return obj && obj[CHART_SPEC_PROP] ? obj : null;
    }

    /** Chart panel: switch type, keep the data table. */
    onChartTypeChange(type) {
        const group = this._selectedChartGroup();
        const draft = this.state.inspector.chart;
        if (!group || !draft) {
            return;
        }
        draft.type = type;
        this._commitChartDraft(group, draft);
    }

    onChartTitleChange(ev) {
        const group = this._selectedChartGroup();
        const draft = this.state.inspector.chart;
        if (!group || !draft) {
            return;
        }
        draft.title = ev.target.value;
        this._commitChartDraft(group, draft);
    }

    onChartCategoryChange(index, ev) {
        const group = this._selectedChartGroup();
        const draft = this.state.inspector.chart;
        if (!group || !draft || !draft.categories[index]) {
            return;
        }
        draft.categories[index] = ev.target.value;
        this._commitChartDraft(group, draft);
    }

    onChartSeriesNameChange(index, ev) {
        const group = this._selectedChartGroup();
        const draft = this.state.inspector.chart;
        if (!group || !draft || !draft.series[index]) {
            return;
        }
        draft.series[index].name = ev.target.value;
        this._commitChartDraft(group, draft);
    }

    /**
     * One data cell. Values stay strings in the spec: they may hold a
     * {{token}}, and chartSpecToSvg coerces non-numeric input to 0 per
     * the data-binding spec.
     */
    onChartCellChange(seriesIndex, categoryIndex, ev) {
        const group = this._selectedChartGroup();
        const draft = this.state.inspector.chart;
        if (!group || !draft || !draft.series[seriesIndex]) {
            return;
        }
        draft.series[seriesIndex].values[categoryIndex] = ev.target.value;
        this._commitChartDraft(group, draft);
    }

    onChartAddCategory() {
        const group = this._selectedChartGroup();
        const draft = this.state.inspector.chart;
        if (!group || !draft) {
            return;
        }
        draft.categories.push(_t("Category"));
        for (const series of draft.series) {
            series.values.push("");
        }
        this._commitChartDraft(group, draft);
    }

    onChartRemoveCategory(index) {
        const group = this._selectedChartGroup();
        const draft = this.state.inspector.chart;
        if (!group || !draft || draft.categories.length <= 1) {
            return;
        }
        draft.categories.splice(index, 1);
        for (const series of draft.series) {
            series.values.splice(index, 1);
        }
        this._commitChartDraft(group, draft);
    }

    onChartAddSeries() {
        const group = this._selectedChartGroup();
        const draft = this.state.inspector.chart;
        if (!group || !draft) {
            return;
        }
        draft.series.push({
            name: _t("Series %s", String(draft.series.length + 1)),
            values: draft.categories.map(() => ""),
        });
        this._commitChartDraft(group, draft);
    }

    onChartRemoveSeries(index) {
        const group = this._selectedChartGroup();
        const draft = this.state.inspector.chart;
        if (!group || !draft || draft.series.length <= 1) {
            return;
        }
        draft.series.splice(index, 1);
        this._commitChartDraft(group, draft);
    }

    /**
     * Commit the panel draft: write it back onto the layer and
     * regenerate the chart in place. Failures keep the last good chart
     * on canvas and surface in the message line.
     */
    async _commitChartDraft(group, draft) {
        try {
            await this._commitChartSpec(group, draft);
        } catch (err) {
            this._showMessage(_t("Chart failed to update: %s", err.message || err));
        }
    }

    // Table ------------------------------------------------------------

    toggleTableMenu() {
        if (!this.state.tableMenuOpen && !this._assertEditable()) {
            return;
        }
        this.state.tableMenuOpen = !this.state.tableMenuOpen;
        this._syncGlobalPointerListener();
    }

    /**
     * Toolbar insert: build the table from the rows/cols/width prompt
     * (evenly sized cells) and add it as one centered layer. The whole
     * table is a single group carrying _tableData (design D4).
     */
    insertTable() {
        if (!this._fabric || !this._assertEditable()) {
            return;
        }
        const clamp = (value, fallback) => {
            const n = Math.round(Number(value));
            if (!Number.isFinite(n) || n < 1) {
                return fallback;
            }
            return Math.min(50, n);
        };
        const rows = clamp(this.state.tableRowsDraft, 3);
        const cols = clamp(this.state.tableColsDraft, 3);
        const width = Math.max(40, Number(this.state.tableWidthDraft) || 400);
        const cellWidth = Math.round(width / cols);
        const group = buildTableGroup(
            this._fabric,
            starterTableData(rows, cols, cellWidth)
        );
        const { width: canvasW, height: canvasH } = this._dimensions;
        group.set({
            originX: "left",
            originY: "top",
            left: Math.floor((canvasW - group.width) / 2),
            top: Math.floor((canvasH - group.height) / 2),
        });
        group._layerName = _t("Table");
        this.state.tableMenuOpen = false;
        this._syncGlobalPointerListener();
        this._addObject(group);
    }

    onTableRowsDraftChange(ev) {
        this.state.tableRowsDraft = ev.target.value;
    }

    onTableColsDraftChange(ev) {
        this.state.tableColsDraft = ev.target.value;
    }

    onTableWidthDraftChange(ev) {
        this.state.tableWidthDraft = ev.target.value;
    }

    _selectedTableGroup() {
        const obj = this._canvas && this._canvas.getActiveObject();
        return obj && obj[TABLE_PROP] ? obj : null;
    }

    /**
     * Structural edit for the selected table: rebuild the group from
     * the new data, preserving placement and entered cell text (the
     * structural ops in table_library carry texts across).
     */
    _applyTableData(newData) {
        const group = this._selectedTableGroup();
        if (!group || !this._fabric) {
            return;
        }
        const data = normalizeTableData(newData);
        const rebuilt = buildTableGroup(this._fabric, data);
        rebuilt[TABLE_PROP] = data;
        this._swapGroupInPlace(group, rebuilt);
    }

    onTableAddRow() {
        const group = this._selectedTableGroup();
        if (!group) {
            return;
        }
        this._applyTableData(addTableRow(group[TABLE_PROP]));
    }

    onTableRemoveRow() {
        const group = this._selectedTableGroup();
        if (!group) {
            return;
        }
        this._applyTableData(removeTableRow(group[TABLE_PROP]));
    }

    onTableAddColumn() {
        const group = this._selectedTableGroup();
        if (!group) {
            return;
        }
        this._applyTableData(addTableColumn(group[TABLE_PROP]));
    }

    onTableRemoveColumn() {
        const group = this._selectedTableGroup();
        if (!group) {
            return;
        }
        this._applyTableData(removeTableColumn(group[TABLE_PROP]));
    }

    /**
     * Double-click on a table group: ungroup it so the cell textboxes
     * become directly editable (design D4 edit isolation, the same
     * ungroup math as ungroupSelection). The session remembers the
     * original data, placement and layer identity for reassembly.
     */
    _onCanvasDblClick(ev) {
        const target = ev && ev.target;
        if (!this._canvas || this.state.previewMode || this._tableEdit) {
            return;
        }
        if (
            !target ||
            (target.type || "").toLowerCase() !== "group" ||
            !target[TABLE_PROP]
        ) {
            return;
        }
        this._enterTableEdit(target);
    }

    _enterTableEdit(group) {
        const fc = this._canvas;
        if (!fc || !group || !group[TABLE_PROP] || this._tableEdit) {
            return;
        }
        const data = normalizeTableData(group[TABLE_PROP]);
        const session = {
            data,
            index: this._canvas.getObjects().indexOf(group),
            children: [],
            transform: {
                left: group.left,
                top: group.top,
                scaleX: group.scaleX ?? 1,
                scaleY: group.scaleY ?? 1,
                angle: group.angle ?? 0,
                flipX: !!group.flipX,
                flipY: !!group.flipY,
                originX: group.originX || "center",
                originY: group.originY || "center",
            },
            layerId: group._layerId,
            layerName: group._layerName,
        };
        const util = this._fabric.util;
        const groupMatrix = group.calcTransformMatrix();
        const items = [...group._objects];
        group._objects = [];
        fc.remove(group);
        items.forEach((obj, i) => {
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
            // The cell markers are transient (never serialized), so a
            // reloaded table derives them from the row-major child
            // order: rect, textbox pairs per cell.
            if (obj._tableCellRow == null) {
                const pairIndex = Math.floor(i / 2);
                obj._tableCellRow = Math.floor(pairIndex / data.cols);
                obj._tableCellCol = pairIndex % data.cols;
            }
            const isText = typeof obj.text === "string";
            obj.set({ selectable: isText, evented: isText });
            fc.add(obj);
            session.children.push(obj);
        });
        this._tableEdit = session;
        this.state.tableEditing = { rows: data.rows, cols: data.cols };
        fc.discardActiveObject();
        fc.requestRenderAll();
        this._syncLayers();
    }

    /**
     * Click outside the loose cells ends the session (reassembly, same
     * as the explicit Done button). Clicks on a loose child keep it
     * open so text editing continues.
     */
    _onCanvasPointerDown(ev) {
        const session = this._tableEdit;
        if (!session || !this._canvas) {
            return;
        }
        const target = ev && ev.target;
        if (!target || !session.children.includes(target)) {
            this._exitTableEdit(true);
        }
    }

    /**
     * Reassemble the table group: sync the edited cell texts back into
     * _tableData, rebuild the group through the same path as the
     * structural edits and restore the captured placement. With
     * commit=false (unused today, kept for Escape-to-cancel semantics)
     * the original texts win.
     */
    _exitTableEdit(commit) {
        const session = this._tableEdit;
        const fc = this._canvas;
        if (!session || !fc) {
            return;
        }
        this._tableEdit = null;
        this.state.tableEditing = null;
        let data = session.data;
        if (commit) {
            const entries = session.children
                .filter((child) => typeof child.text === "string")
                .map((child) => ({
                    row: child._tableCellRow,
                    col: child._tableCellCol,
                    text: child.text,
                }));
            data = syncTableTexts(data, entries);
        }
        for (const child of session.children) {
            fc.remove(child);
        }
        const rebuilt = buildTableGroup(this._fabric, data);
        rebuilt[TABLE_PROP] = normalizeTableData(data);
        rebuilt._layerId = session.layerId;
        rebuilt._layerName = session.layerName;
        if (typeof rebuilt.set === "function") {
            rebuilt.set(session.transform);
        } else {
            Object.assign(rebuilt, session.transform);
        }
        rebuilt.setCoords?.();
        // Back into the slot the group occupied before isolation.
        const siblings = fc.getObjects();
        const index = Math.max(
            0,
            Math.min(session.index, siblings.length)
        );
        if (typeof fc.insertAt === "function") {
            fc.insertAt(index, rebuilt);
        } else {
            fc.add(rebuilt);
        }
        fc.setActiveObject(rebuilt);
        fc.requestRenderAll();
        this._syncSelection();
        this._onCanvasChanged();
    }

    // QR ---------------------------------------------------------------

    toggleQrMenu() {
        if (!this.state.qrMenuOpen && !this._assertEditable()) {
            return;
        }
        this.state.qrMenuOpen = !this.state.qrMenuOpen;
        if (!this.state.qrMenuOpen) {
            this.state.qrError = "";
        }
        this._syncGlobalPointerListener();
    }

    onQrContentDraftChange(ev) {
        this.state.qrContentDraft = ev.target.value;
        this.state.qrError = "";
    }

    /**
     * Load the vendored QR generator once and wire it into qr_library
     * (design D5: same library as the render side's npm package, a
     * fixture test asserts identical matrices).
     */
    async _ensureQrLib() {
        if (!this._qrLibPromise) {
            this._qrLibPromise = loadQr().then((lib) => {
                initQrGenerator(lib);
                return lib;
            });
        }
        return this._qrLibPromise;
    }

    /**
     * Build the QR group: content -> module matrix -> one Rect per dark
     * module. The group is modules * moduleSize square and carries the
     * content on _qrContent (design D6).
     */
    _buildQrGroup(content, { moduleSize = 4, color = "#000000" } = {}) {
        const matrix = qrContentToMatrix(content);
        const specs = qrMatrixToRectSpecs(matrix, moduleSize, color);
        const rects = specs.map(
            (s) =>
                new this._fabric.Rect({
                    left: s.left,
                    top: s.top,
                    width: s.size,
                    height: s.size,
                    originX: "left",
                    originY: "top",
                    fill: s.fill,
                    selectable: false,
                    evented: false,
                })
        );
        const group = new this._fabric.Group(rects);
        if (!group.width) {
            group.width = matrix.length * moduleSize;
        }
        if (!group.height) {
            group.height = matrix.length * moduleSize;
        }
        group[QR_PROP] = content;
        return group;
    }

    /**
     * Toolbar insert: validate the content (inline error per the QR
     * spec: unencodable or empty content does not insert), then add the
     * code as one centered layer.
     */
    async insertQr() {
        if (!this._fabric || !this._assertEditable()) {
            return;
        }
        const content = String(this.state.qrContentDraft || "").trim();
        if (!content) {
            this.state.qrError = _t("Enter the QR content first.");
            return;
        }
        let group;
        try {
            await this._ensureQrLib();
            group = this._buildQrGroup(content, {
                moduleSize: 4,
                color: "#000000",
            });
        } catch (err) {
            this.state.qrError = _t(
                "The content cannot be encoded as a QR code."
            );
            return;
        }
        const { width, height } = this._dimensions;
        group.set({
            originX: "left",
            originY: "top",
            left: Math.floor((width - group.width) / 2),
            top: Math.floor((height - group.height) / 2),
        });
        group._layerName = _t("QR code");
        this.state.qrMenuOpen = false;
        this.state.qrContentDraft = "";
        this.state.qrError = "";
        this._syncGlobalPointerListener();
        this._addObject(group);
    }

    /**
     * QR edit in the properties panel: re-encode the content and
     * regenerate the layer in place, deriving module size and color
     * from the layer being replaced (mirrors buildQrGroup on the render
     * side, so a bound QR keeps its design-time size). Unencodable
     * content keeps the previous code and reports in the message line.
     */
    async onQrContentChange(ev) {
        const obj = this._canvas && this._canvas.getActiveObject();
        if (!obj || typeof obj[QR_PROP] !== "string") {
            return;
        }
        const content = String(ev.target.value || "").trim();
        try {
            await this._ensureQrLib();
            const matrix = qrContentToMatrix(content);
            const modules = matrix.length;
            const moduleSize =
                obj.width && obj.width > 0 ? obj.width / modules : 4;
            const firstChild =
                typeof obj.getObjects === "function" ? obj.getObjects()[0] : null;
            const color =
                firstChild && typeof firstChild.fill === "string" && firstChild.fill
                    ? firstChild.fill
                    : "#000000";
            const replacement = this._buildQrGroup(content, {
                moduleSize,
                color,
            });
            replacement[QR_PROP] = content;
            this._swapGroupInPlace(obj, replacement);
        } catch (err) {
            this._showMessage(_t("QR content cannot be encoded."));
            this._syncSelection();
        }
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
            this._showMessage(_t("Record search failed: %s", err.message || err));
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
                this._showMessage(_t("No records found to preview."));
                return;
            }
            this.state.previewRecordId = first.id;
            this.state.previewRecordName = first.name;
        }
        // A table edit session must not leak into the snapshot: reassemble
        // first so the captured (and later restored) scene is the grouped
        // token scene.
        if (this._tableEdit) {
            this._exitTableEdit(true);
        }
        this._previewSnapshot = this._captureScene();
        this._history.suspended = true;
        this.state.previewMode = true;
        this.state.previewSearch = "";
        this.state.previewResults = [];        // Selection off so no edits land on the mutated canvas; they
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
            const measurePreviewLine = (lineText, desc) => {
                const ctx = fc.contextContainer;
                if (!ctx) return 0;
                ctx.font = `${desc.fontStyle || "normal"} ${desc.fontWeight || "normal"} ${desc.fontSize}px ${desc.fontFamily || "sans-serif"}`;
                return ctx.measureText(lineText).width;
            };
            for (const obj of [...fc.getObjects()]) {
                // Conditional visibility (any layer type).
                const hie = obj._hideIfEmpty;
                if (hie && hie.field && isEmptyBindingValue(bindings[hie.field])) {
                    obj.visible = false;
                    continue;
                }
                // Text tokens with pipe transforms, plus the render-time
                // typography pipeline (transform, markdown, autofit) so the
                // preview matches the server output exactly.
                if (typeof obj.text === "string") {
                    const textBefore = obj.text;
                    const stylesBefore = JSON.stringify(obj.styles || {});
                    resolveTextForPreview(obj, bindings, { measure: measurePreviewLine });
                    if (
                        obj.text !== textBefore ||
                        JSON.stringify(obj.styles || {}) !== stylesBefore
                    ) {
                        obj.set("text", obj.text);
                        obj.set("styles", obj.styles || {});
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
                // Chart layers (design D3): substitute bound cells, then
                // regenerate the SVG group in place, mirroring
                // regenerateDynamicGroups on the render side: placement
                // preserved, _chartSpec carried onto the replacement so a
                // second pass over the same bindings converges.
                if (obj[CHART_SPEC_PROP]) {
                    const resolvedSpec = substituteChartSpec(
                        obj[CHART_SPEC_PROP],
                        bindings
                    );
                    try {
                        const rebuilt = await this._buildChartGroup(resolvedSpec);
                        rebuilt[CHART_SPEC_PROP] = resolvedSpec;
                        this._swapPreviewGroup(obj, rebuilt);
                    } catch (err) {
                        // A bad spec is an authoring bug; keep the layer
                        // as-is so the rest of the preview still shows.
                        console.error("editor preview: chart regeneration failed", err);
                    }
                }
                // QR layers (design D5): resolve tokens in the content and
                // regenerate the code from the resolved value. An empty or
                // unencodable resolution hides the layer, exactly the
                // render behavior for an empty record value.
                if (typeof obj[QR_PROP] === "string") {
                    const resolved = resolveTokens(obj[QR_PROP], bindings);
                    try {
                        await this._ensureQrLib();
                        const matrix = qrContentToMatrix(resolved);
                        const modules = matrix.length;
                        const moduleSize =
                            obj.width && obj.width > 0 ? obj.width / modules : 4;
                        const firstChild =
                            typeof obj.getObjects === "function"
                                ? obj.getObjects()[0]
                                : null;
                        const color =
                            firstChild &&
                            typeof firstChild.fill === "string" &&
                            firstChild.fill
                                ? firstChild.fill
                                : "#000000";
                        const rebuilt = this._buildQrGroup(resolved, {
                            moduleSize,
                            color,
                        });
                        rebuilt[QR_PROP] = resolved;
                        this._swapPreviewGroup(obj, rebuilt);
                    } catch (err) {
                        obj.visible = false;
                    }
                }
            }
            fc.renderAll();
        } catch (err) {
            this._showMessage(_t("Preview failed: %s", err.message || err));
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
                    name: _t("Company logo"),
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
                            name: att.name || _t("image"),
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
                    name: file.name || _t("image"),
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
            this._showMessage(_t("Upload failed: %s", err.message || err));
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
            this._showMessage(_t("Icon failed to load: %s", err.message || err));
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

    /**
     * Record where a move begins (pointer + object position) so Shift can
     * lock the drag to the dominant axis relative to this point. Reset on
     * mouse up together with the snap guides.
     */
    _onDragStart(ev) {
        if (!this._canvas) {
            return;
        }
        if (!ev.target) {
            this._moveStart = null;
            return;
        }
        const p = ev.pointer || this._canvas.getPointer(ev.e);
        this._moveStart = {
            pointerX: p.x,
            pointerY: p.y,
            left: ev.target.left || 0,
            top: ev.target.top || 0,
        };
    }

    /**
     * Shift held during a move constrains it to one axis, dominant axis
     * wins (ties count as horizontal). Runs before the snap logic so
     * guides still work along the free axis, and before the Alt bypass
     * so Alt+Shift is a free but axis-locked drag.
     */
    _applyShiftAxisLock(moving, ev) {
        if (!this._snapShift || !this._moveStart) {
            return;
        }
        const fc = this._canvas;
        const p = (ev && (ev.pointer || (ev.e && fc.getPointer(ev.e)))) || null;
        if (!p) {
            return;
        }
        const dx = p.x - this._moveStart.pointerX;
        const dy = p.y - this._moveStart.pointerY;
        if (Math.abs(dx) >= Math.abs(dy)) {
            moving.top = this._moveStart.top;
        } else {
            moving.left = this._moveStart.left;
        }
        moving.setCoords();
    }

    _onObjectMoving(ev) {
        const fc = this._canvas;
        const moving = ev.target;
        if (!fc || !moving) {
            return;
        }
        this._applyShiftAxisLock(moving, ev);
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

        // Snap-to-grid (design D1) runs last: smart guides keep
        // priority, so on each axis grid rounding applies only when no
        // guide and no equal-gap spacing snap won there. Alt bypasses
        // grid snap together with the guides (early return above).
        if (this.state.gridSnap && !this._snapAlt) {
            const gridStep = Number(this.state.gridSpacing) || DEFAULT_GRID_SPACING;
            if (snap.vAt == null && !spacing.dx) {
                moving.left = roundToGrid(moving.left || 0, gridStep);
            }
            if (snap.hAt == null && !spacing.dy) {
                moving.top = roundToGrid(moving.top || 0, gridStep);
            }
            moving.setCoords();
        }
    }

    /**
     * Snap-to-grid while resizing: round the scaled footprint (width x
     * scaleX, height x scaleY) back onto the grid. Same priority idea
     * as moving: only when the snap toggle is on and Alt is not held.
     * A rounding that would collapse an object to zero leaves it put.
     */
    _onObjectScaling(ev) {
        const obj = ev && ev.target;
        if (!obj || !this.state.gridSnap || this._snapAlt) {
            return;
        }
        const gridStep = Number(this.state.gridSpacing) || DEFAULT_GRID_SPACING;
        const scaledW = (Number(obj.width) || 0) * (Number(obj.scaleX) || 1);
        const scaledH = (Number(obj.height) || 0) * (Number(obj.scaleY) || 1);
        const snappedW = roundToGrid(scaledW, gridStep);
        const snappedH = roundToGrid(scaledH, gridStep);
        if (obj.width && snappedW > 0) {
            obj.scaleX = snappedW / obj.width;
        }
        if (obj.height && snappedH > 0) {
            obj.scaleY = snappedH / obj.height;
        }
        obj.setCoords?.();
    }

    /**
     * after:render hook for everything painted on contextTop (never
     * part of the scene, so exports stay clean): the grid first, the
     * snap guides and spacing labels on top.
     */
    _drawOverlays() {
        const fc = this._canvas;
        const ctx = fc && fc.contextTop;
        if (!ctx) {
            return;
        }
        fc.clearContext(ctx);
        this._drawGrid(ctx);
        this._drawSnapGuides(ctx);
    }

    /**
     * Grid overlay (design D1): viewport-clipped lines computed in
     * canvas coordinates and painted like the snap guides (canvas
     * value x zoom). Never touches the scene or the lower canvas.
     */
    _drawGrid(ctx) {
        if (!this.state.gridVisible) {
            return;
        }
        const fc = this._canvas;
        if (!fc) {
            return;
        }
        const z = fc.getZoom() || 1;
        const vpt = fc.viewportTransform || [1, 0, 0, 1, 0, 0];
        const viewport = {
            left: -vpt[4] / z,
            top: -vpt[5] / z,
            width: fc.getWidth() / z,
            height: fc.getHeight() / z,
        };
        const spacing = Number(this.state.gridSpacing) || DEFAULT_GRID_SPACING;
        const lines = computeGridLines(viewport, spacing, z);
        if (!lines.length) {
            return;
        }
        ctx.save();
        ctx.lineWidth = 1;
        ctx.strokeStyle = "rgba(100, 116, 139, 0.35)";
        ctx.beginPath();
        for (const g of lines) {
            if (g.kind === "v") {
                ctx.moveTo(g.at * z, g.from * z);
                ctx.lineTo(g.at * z, g.to * z);
            } else {
                ctx.moveTo(g.from * z, g.at * z);
                ctx.lineTo(g.to * z, g.at * z);
            }
        }
        ctx.stroke();
        ctx.restore();
    }

    _drawSnapGuides(ctx) {
        const fc = this._canvas;
        if (!fc || !ctx) {
            return;
        }
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
            // The grid is not drag state: put it back immediately.
            this._drawGrid(ctx);
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
            this._showMessage(_t("Exit preview mode to edit the design."));
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
            // Table, chart and QR panel copies (designs D3/D4/D5)
            chart: null,
            qrContent: null,
            table: null,
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
        // Table, chart and QR elements (designs D3/D4/D5): deep copies for
        // the properties-panel editors; the panel commits through the
        // regeneration path, never by mutating these directly.
        inspector.chart = obj[CHART_SPEC_PROP]
            ? JSON.parse(JSON.stringify(obj[CHART_SPEC_PROP]))
            : null;
        inspector.qrContent =
            typeof obj[QR_PROP] === "string" ? obj[QR_PROP] : null;
        inspector.table = obj[TABLE_PROP]
            ? JSON.parse(JSON.stringify(obj[TABLE_PROP]))
            : null;
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

    /**
     * Add at a captured stack position instead of on top: used when an
     * async load (image from URL) resolves after other objects were
     * added, so the late object keeps its pick-order slot instead of
     * overtaking them. Same side effects as _addObject otherwise.
     */
    _addObjectAt(obj, index) {
        if (!this._assertEditable()) {
            return;
        }
        obj._layerId = newLayerId();
        this._canvas.insertAt(index, obj);
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
            new Textbox(_t("Text"), {
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
                // The grid is not pen state: put it back immediately.
                this._drawGrid(ctx);
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
     * Grid overlay toggle (design D1). The grid itself is painted on
     * contextTop in the after:render hook, so toggling only needs a
     * re-render; prefs persist per user.
     */
    toggleGrid() {
        this.state.gridVisible = !this.state.gridVisible;
        this._writeGridPrefs();
        if (this._canvas) {
            this._canvas.requestRenderAll();
        }
    }

    toggleGridMenu() {
        this.state.gridMenuOpen = !this.state.gridMenuOpen;
        this._syncGlobalPointerListener();
    }

    onGridSnapChange(ev) {
        this.state.gridSnap = !!(ev.target && ev.target.checked);
        this._writeGridPrefs();
    }

    setGridSpacing(spacing) {
        this.state.gridSpacing = GRID_SPACING_PRESETS.includes(spacing)
            ? spacing
            : DEFAULT_GRID_SPACING;
        this._writeGridPrefs();
        if (this._canvas) {
            this._canvas.requestRenderAll();
        }
    }

    gridSpacingPresets() {
        return GRID_SPACING_PRESETS;
    }

    /**
     * Per-user grid prefs from localStorage. Unknown or invalid values
     * fall back to hidden grid, snap off, default spacing.
     */
    _readGridPrefs() {
        const fallback = {
            visible: false,
            snap: false,
            spacing: DEFAULT_GRID_SPACING,
        };
        let raw = null;
        try {
            raw =
                window.localStorage &&
                window.localStorage.getItem("social_image_editor_grid");
        } catch (_) {
            return fallback;
        }
        if (!raw) {
            return fallback;
        }
        try {
            const parsed = JSON.parse(raw);
            return {
                visible: !!parsed.visible,
                snap: !!parsed.snap,
                spacing: GRID_SPACING_PRESETS.includes(parsed.spacing)
                    ? parsed.spacing
                    : DEFAULT_GRID_SPACING,
            };
        } catch (_) {
            return fallback;
        }
    }

    _writeGridPrefs() {
        try {
            if (window.localStorage) {
                window.localStorage.setItem(
                    "social_image_editor_grid",
                    JSON.stringify({
                        visible: this.state.gridVisible,
                        snap: this.state.gridSnap,
                        spacing: this.state.gridSpacing,
                    })
                );
            }
        } catch (_) {}
    }

    /**
     * One shared window mousedown listener for all open dropdowns;
     * attached while at least one menu is open.
     */
    _syncGlobalPointerListener() {
        if (
            this.state.fontPickerOpen ||
            this.state.shapesOpen ||
            this.state.gridMenuOpen ||
            this.state.insertDataOpen ||
            this.state.chartMenuOpen ||
            this.state.tableMenuOpen ||
            this.state.qrMenuOpen
        ) {
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
        if (!this._fabric || !this._canvas) {
            return;
        }
        const { width, height } = this._dimensions;
        // Capture the intended z-position NOW: the image lands whenever
        // the load finishes, and objects added in between must stay ABOVE
        // it or the visible order contradicts the pick order.
        const insertIndex = this._canvas.getObjects().length;
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
                if (this._canvas.getObjects().length === insertIndex) {
                    this._addObject(img);
                } else {
                    this._addObjectAt(img, insertIndex);
                }
            })
            .catch((err) => {
                this._showMessage(_t("Image failed to load: %s", err.message || err));
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
        // Write the state back so the re-render (_syncLayers via
        // _onCanvasChanged) does not snap the range input to a stale
        // value mid-drag.
        this.state.opacity = opacityPercentFromFraction(value);
        for (const obj of objects) {
            obj.set("opacity", this.state.opacity / 100);
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
            this._showMessage(_t("Fill with image is not supported for this shape."));
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
            this._showMessage(_t("Fill with image failed: %s", err.message || err));
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
            this._showMessage(_t("Revert to color is not supported for this shape."));
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
        // A table ungroups through the edit-isolation path only: plain
        // ungrouping would detach the cell texts from _tableData.
        if (grp[TABLE_PROP]) {
            this._enterTableEdit(grp);
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
     * Edit-time text props for the live canvas. Per the render-parity
     * design (D3) the case transform is NEVER baked into obj.text here:
     * stored scenes must keep raw {{tokens}} so bindings resolve at
     * render, and the render service applies the transform to the
     * resolved value. Autofit stays as an edit-time convenience for
     * static text only; fitting against placeholder token text is exactly
     * the overflow bug the render-time autofit fixes.
     */
    _applyTextProps(obj) {
        if (!obj || typeof obj.text !== "string") {
            return;
        }
        if (obj._overflow === "autofit" && !obj.text.includes("{{")) {
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
        if (this.state.gridMenuOpen) {
            const el = this.gridMenuRef.el;
            if (el && !el.contains(ev.target)) {
                this.state.gridMenuOpen = false;
            }
        }
        if (this.state.insertDataOpen) {
            const el = this.insertDataRef.el;
            if (el && !el.contains(ev.target)) {
                this.closeInsertDataPanel();
            }
        }
        if (this.state.chartMenuOpen) {
            const el = this.chartMenuRef.el;
            if (el && !el.contains(ev.target)) {
                this.state.chartMenuOpen = false;
            }
        }
        if (this.state.tableMenuOpen) {
            const el = this.tableMenuRef.el;
            if (el && !el.contains(ev.target)) {
                this.state.tableMenuOpen = false;
            }
        }
        if (this.state.qrMenuOpen) {
            const el = this.qrMenuRef.el;
            if (el && !el.contains(ev.target)) {
                this.state.qrMenuOpen = false;
                this.state.qrError = "";
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
        // The indicator promises "directly above the hovered row"; for a
        // downward drag the removal shifts that row up one slot, so insert
        // one slot earlier. toIndex may be state.layers.length (trailing
        // drop zone = append at the bottom).
        const insertIndex = computeInsertIndex(fromIndex, toIndex);
        const newLayers = moveItem(this.state.layers, fromIndex, insertIndex);
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
        // Raw capture, no derivation: case transform and autofit apply at
        // render time (render-parity design D3), so this must NOT rewrite
        // obj.text; stored scenes keep raw {{tokens}} so bindings resolve.
        // _textTransform/_overflow still persist via EXTRA_PROPS. Suspended
        // so the resulting `changed` events cannot schedule extra
        // history/save cycles mid-capture.
        const wasSuspended = this._history.suspended;
        this._history.suspended = true;
        try {
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
        if (key === "delete" || key === "backspace") {
            // Remove the active selection. The guards above suppress this
            // while a text object is in editing mode (and inside inputs).
            ev.preventDefault();
            this.deleteSelected();
            return;
        }
        if (key === "escape") {
            // Unwind in reverse order of opening: open pickers close
            // first, a final Escape closes the dialog itself (subject to
            // the close-safety rule in close()).
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
            if (this.state.fontPickerOpen) {
                this.state.fontPickerOpen = false;
                this.state.fontFilter = "";
                this._syncGlobalPointerListener();
                return;
            }
            if (this.state.shapesOpen) {
                this.state.shapesOpen = false;
                this._syncGlobalPointerListener();
                return;
            }
            if (this.state.gridMenuOpen) {
                this.state.gridMenuOpen = false;
                this._syncGlobalPointerListener();
                return;
            }
            if (this.state.insertDataOpen) {
                this.closeInsertDataPanel();
                return;
            }
            if (this.state.tableEditing) {
                this._exitTableEdit(true);
                return;
            }
            if (this.state.chartMenuOpen) {
                this.state.chartMenuOpen = false;
                this._syncGlobalPointerListener();
                return;
            }
            if (this.state.tableMenuOpen) {
                this.state.tableMenuOpen = false;
                this._syncGlobalPointerListener();
                return;
            }
            if (this.state.qrMenuOpen) {
                this.state.qrMenuOpen = false;
                this.state.qrError = "";
                this._syncGlobalPointerListener();
                return;
            }
            ev.preventDefault();
            this.close();
            return;
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
     * Show the bottom message line as a toast: dismissible and
     * auto-clearing after MESSAGE_TIMEOUT_MS (ux task 6.1). The timer is
     * reset on every new message, and a stale timer never clears a newer
     * message. An unresolved save error keeps the bar (with the Retry
     * button) via state.saveState even after the text clears.
     */
    _showMessage(text) {
        this.state.message = text;
        clearTimeout(this._messageTimer);
        if (!text) {
            return;
        }
        this._messageTimer = setTimeout(() => {
            if (this.state.message === text) {
                this.state.message = "";
            }
        }, MESSAGE_TIMEOUT_MS);
    }

    dismissMessage() {
        clearTimeout(this._messageTimer);
        this._messageTimer = null;
        this.state.message = "";
    }

    /**
     * Text of the bottom message line: the current message, or a fallback
     * while a save error is unresolved but the message already cleared.
     */
    messageBarText() {
        return this.state.message || _t("Save failed.");
    }

    /**
     * Retry a failed save (retry button in the message bar, close-safety
     * design D1): flush immediately and report the outcome through the
     * usual save-state and message plumbing.
     */
    async retrySave() {
        await this._flushSave();
    }

    /**
     * Persist the live scene into the primary variant (variants JSONB, so
     * the legacy width/height/scene_json mirrors stay in sync via the
     * model's write override) and regenerate the SVG master with the same
     * DOMPurify + btoa pipeline as the old inline field.
     *
     * @returns {Promise<boolean>} true when the scene is safely persisted
     *   (nothing dirty, or the write succeeded), false when a write was
     *   attempted and failed; the caller (close) decides whether staying
     *   open is required.
     */
    async _flushSave() {
        if (this.state.previewMode) {
            // Never persist the resolved preview over the token scene.
            await this._exitPreview();
        }
        if (this._tableEdit) {
            // Never persist a table mid-edit (ungrouped loose cells):
            // reassemble so the saved scene is the grouped table.
            this._exitTableEdit(true);
        }
        if (!this._canvas || !this._dirty || this._saving) {
            return true;
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
            this._closeFailed = false;
            this.dismissMessage();
            return true;
        } catch (err) {
            this.state.saveState = "error";
            this._showMessage(_t("Autosave failed: %s", err.message || err));
            return false;
        } finally {
            this._saving = false;
        }
    }

    /**
     * Close the editor. Awaits the final save flush (close-safety design
     * D1): while a save is in flight closing is blocked, and when the
     * flush fails the dialog stays open with the message line and its
     * retry button, keeping the edits. A second close attempt after a
     * failure asks for explicit discard and only then closes unsaved.
     */
    async close() {
        if (this._saving) {
            // A flush owns the scene right now; closing would strand it.
            return;
        }
        clearTimeout(this._saveTimer);
        if (this.state.previewMode) {
            await this._exitPreview();
        }
        const saved = await this._flushSave();
        if (saved) {
            this._closeFailed = false;
            this.props.close();
            return;
        }
        if (!this._closeFailed) {
            // First failure: stay open; the message line plus its retry
            // button carry the error, the edits and the dirty flag remain.
            this._closeFailed = true;
            return;
        }
        // Second attempt after a failure: explicit discard only.
        const discard = window.confirm(
            _t(
                "The changes could not be saved. Close the editor and discard your edits?"
            )
        );
        if (!discard) {
            return;
        }
        this._dirty = false;
        this.props.close();
    }
}
