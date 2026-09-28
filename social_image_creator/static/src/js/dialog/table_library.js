/** @odoo-module **/

/**
 * Pure table helpers for the editor's table element (design D4 in
 * openspec/changes/editor-grid-dynamic-elements) plus the fabric group
 * builder. The data model and the structural ops are plain-data and
 * unit-tested under Node; buildTableGroup converts the data into one
 * fabric Group (background Rects + one Textbox per cell) and is exercised
 * with a fabric stub in the static tests.
 *
 * Data model (stored on the group as `_tableData`, EXTRA_PROPS-persisted):
 *   {
 *     rows:   positive int,
 *     cols:   positive int,
 *     cellWidth?: positive number,   // px per column; evenly sized cells
 *     header: bool,                  // row 0 renders with the header fill
 *     cells:  { "row,col": string }  // sparse; missing cells render empty
 *   }
 */

export const TABLE_PROP = "_tableData";

/** Default total width when the data carries no cellWidth. */
export const TABLE_DEFAULT_WIDTH = 400;
/** Row height in px; text is vertically centered inside it. */
export const TABLE_CELL_HEIGHT = 36;
/** Header row background. */
export const TABLE_HEADER_FILL = "#4f46e5";
/** Body zebra fills, alternating by body row index. */
export const TABLE_BODY_FILLS = ["#ffffff", "#f1f5f9"];
export const TABLE_HEADER_TEXT = "#ffffff";
export const TABLE_BODY_TEXT = "#1a1a1a";
export const TABLE_TEXT_FONT = "Arial, sans-serif";
export const TABLE_FONT_SIZE = 14;
const TABLE_CELL_PADDING = 6;

const MIN_TABLE_SIDE = 1;
const MAX_TABLE_SIDE = 50;

/** The "r,c" storage key for one cell. */
export function tableCellKey(row, col) {
    return `${row},${col}`;
}

function clampSide(value, fallback) {
    const n = Math.round(Number(value));
    if (!Number.isFinite(n)) {
        return fallback;
    }
    return Math.min(MAX_TABLE_SIDE, Math.max(MIN_TABLE_SIDE, n));
}

/**
 * Coerce arbitrary input (e.g. parsed from an older scene JSON) into a
 * valid table data object: sane row/col counts, boolean header, string
 * cells, out-of-range cell keys dropped. Never throws on user data.
 */
export function normalizeTableData(data) {
    const src = data && typeof data === "object" ? data : {};
    const rows = clampSide(src.rows, 3);
    const cols = clampSide(src.cols, 3);
    const cells = {};
    if (src.cells && typeof src.cells === "object") {
        for (const key of Object.keys(src.cells)) {
            const parts = String(key).split(",");
            const row = Number(parts[0]);
            const col = Number(parts[1]);
            if (
                parts.length === 2 &&
                Number.isInteger(row) &&
                Number.isInteger(col) &&
                row >= 0 &&
                row < rows &&
                col >= 0 &&
                col < cols
            ) {
                cells[tableCellKey(row, col)] = String(src.cells[key] ?? "");
            }
        }
    }
    const out = {
        rows,
        cols,
        header: src.header !== false,
        cells,
    };
    const cellWidth = Number(src.cellWidth);
    if (Number.isFinite(cellWidth) && cellWidth > 0) {
        out.cellWidth = cellWidth;
    }
    return out;
}

/** New table data with `rows` x `cols` empty cells. */
export function starterTableData(rows, cols, cellWidth) {
    return normalizeTableData({ rows, cols, cellWidth });
}

/**
 * Insert an empty row at `index` (default: after the last row). Cells of
 * rows at or below the insertion point shift down; all other text is
 * preserved. Returns a NEW data object.
 */
export function addTableRow(data, index) {
    const t = normalizeTableData(data);
    if (t.rows >= MAX_TABLE_SIDE) {
        return t;
    }
    const at = clampInsertIndex(index, t.rows + 1, t.rows);
    const cells = {};
    for (const key of Object.keys(t.cells)) {
        const [row, col] = key.split(",").map(Number);
        cells[tableCellKey(row >= at ? row + 1 : row, col)] = t.cells[key];
    }
    return { ...t, rows: t.rows + 1, cells };
}

/**
 * Remove the row at `index` (default: the last row). At least one row
 * always remains; cells of rows below shift up. Returns a NEW data object.
 */
export function removeTableRow(data, index) {
    const t = normalizeTableData(data);
    if (t.rows <= MIN_TABLE_SIDE) {
        return t;
    }
    const at = clampInsertIndex(index, t.rows, t.rows - 1);
    const cells = {};
    for (const key of Object.keys(t.cells)) {
        const [row, col] = key.split(",").map(Number);
        if (row === at) {
            continue;
        }
        cells[tableCellKey(row > at ? row - 1 : row, col)] = t.cells[key];
    }
    return { ...t, rows: t.rows - 1, cells };
}

/**
 * Insert an empty column at `index` (default: after the last column).
 * Cells of columns at or right of the insertion point shift right. Returns
 * a NEW data object.
 */
export function addTableColumn(data, index) {
    const t = normalizeTableData(data);
    if (t.cols >= MAX_TABLE_SIDE) {
        return t;
    }
    const at = clampInsertIndex(index, t.cols + 1, t.cols);
    const cells = {};
    for (const key of Object.keys(t.cells)) {
        const [row, col] = key.split(",").map(Number);
        cells[tableCellKey(row, col >= at ? col + 1 : col)] = t.cells[key];
    }
    return { ...t, cols: t.cols + 1, cells };
}

/**
 * Remove the column at `index` (default: the last column). At least one
 * column always remains; cells of columns right of it shift left. Returns
 * a NEW data object.
 */
export function removeTableColumn(data, index) {
    const t = normalizeTableData(data);
    if (t.cols <= MIN_TABLE_SIDE) {
        return t;
    }
    const at = clampInsertIndex(index, t.cols, t.cols - 1);
    const cells = {};
    for (const key of Object.keys(t.cells)) {
        const [row, col] = key.split(",").map(Number);
        if (col === at) {
            continue;
        }
        cells[tableCellKey(row, col > at ? col - 1 : col)] = t.cells[key];
    }
    return { ...t, cols: t.cols - 1, cells };
}

function clampInsertIndex(index, length, fallback) {
    const n = Math.round(Number(index));
    if (!Number.isFinite(n)) {
        return fallback;
    }
    return Math.min(length - 1, Math.max(0, n));
}

/** One cell text written into a NEW data object (no-op when out of range). */
export function setTableCellText(data, row, col, text) {
    const t = normalizeTableData(data);
    const r = Math.round(Number(row));
    const c = Math.round(Number(col));
    if (
        !Number.isInteger(r) ||
        !Number.isInteger(c) ||
        r < 0 ||
        r >= t.rows ||
        c < 0 ||
        c >= t.cols
    ) {
        return t;
    }
    const cells = { ...t.cells };
    cells[tableCellKey(r, c)] = String(text ?? "");
    return { ...t, cells };
}

/**
 * Sync edited cell texts back into the data (table edit isolation
 * reassembly). `entries` is [{row, col, text}]; last write wins. Returns a
 * NEW data object.
 */
export function syncTableTexts(data, entries) {
    let t = normalizeTableData(data);
    for (const entry of entries || []) {
        if (!entry) {
            continue;
        }
        t = setTableCellText(t, entry.row, entry.col, entry.text);
    }
    return t;
}

/** px width of one column for the given (normalized) data. */
export function tableCellWidth(data) {
    const t = normalizeTableData(data);
    return t.cellWidth || Math.round(TABLE_DEFAULT_WIDTH / t.cols);
}

/**
 * Build the fabric group for a table: one background Rect and one Textbox
 * per cell, children in row-major order (rect, textbox, rect, textbox, ...),
 * each carrying `_tableCellRow` / `_tableCellCol` markers so edit
 * isolation can map edited text back to its cell. The group carries
 * `_tableData` and its natural size is cols * cellWidth x rows *
 * TABLE_CELL_HEIGHT. Cell positions are locked relative to the group: the
 * children are created at group-local coordinates and never move
 * independently while grouped.
 */
export function buildTableGroup(fabric, data) {
    const t = normalizeTableData(data);
    const cellW = tableCellWidth(t);
    const { Rect, Textbox, Group } = fabric;
    const children = [];
    for (let row = 0; row < t.rows; row += 1) {
        const isHeader = t.header && row === 0;
        const bodyIndex = t.header ? row - 1 : row;
        const fill = isHeader
            ? TABLE_HEADER_FILL
            : TABLE_BODY_FILLS[Math.abs(bodyIndex) % TABLE_BODY_FILLS.length];
        const textFill = isHeader ? TABLE_HEADER_TEXT : TABLE_BODY_TEXT;
        for (let col = 0; col < t.cols; col += 1) {
            const left = col * cellW;
            const top = row * TABLE_CELL_HEIGHT;
            const rect = new Rect({
                left,
                top,
                width: cellW,
                height: TABLE_CELL_HEIGHT,
                originX: "left",
                originY: "top",
                fill,
                stroke: TABLE_BODY_TEXT,
                strokeWidth: 0.5,
                selectable: false,
                evented: false,
            });
            rect._tableCellRow = row;
            rect._tableCellCol = col;
            const text = new Textbox(t.cells[tableCellKey(row, col)] || "", {
                left: left + TABLE_CELL_PADDING,
                top: top + Math.round((TABLE_CELL_HEIGHT - TABLE_FONT_SIZE) / 2),
                width: cellW - 2 * TABLE_CELL_PADDING,
                originX: "left",
                originY: "top",
                fontSize: TABLE_FONT_SIZE,
                fontFamily: TABLE_TEXT_FONT,
                fill: textFill,
                selectable: false,
                evented: false,
            });
            text._tableCellRow = row;
            text._tableCellCol = col;
            children.push(rect, text);
        }
    }
    const group = new Group(children);
    group.width = group.width || t.cols * cellW;
    group.height = group.height || t.rows * TABLE_CELL_HEIGHT;
    group[TABLE_PROP] = t;
    return group;
}
