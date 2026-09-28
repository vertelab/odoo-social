// build_icon_library.mjs: generate the static Lucide icon library for the
// social image creator editor.
//
// Usage (from the repo root):
//   node scripts/build_icon_library.mjs
//
// Reads the ESM icon modules from the lucide package installed in
// render-engine-os (path hardcoded below with a LUCIDE_DIR env override)
// and writes social_image_creator/static/src/js/dialog/icon_library.js,
// an Odoo ES module exporting ICON_LIBRARY ([{name, tags, body}, ...],
// body is the inner SVG markup without the outer <svg> tag) plus a pure
// searchIcons helper. Only the curated COMMON_ICONS list below is
// emitted, keeping the bundle small; add names there and re-run when
// more icons are needed. The script prints icon count, output size and
// any requested names that do not exist in the package.

import { readdir, writeFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const LUCIDE_DIR =
    process.env.LUCIDE_DIR ||
    "/home/chrille/dev/projects/render-engine-os/ui/node_modules/lucide/dist/esm/icons";
const OUT_FILE = join(
    here,
    "..",
    "social_image_creator/static/src/js/dialog/icon_library.js"
);

// Curated set of the most useful Lucide icons for social media graphics,
// grouped by theme for readability. Every name must exist in the lucide
// package; the script reports (and skips) unknown names.
const COMMON_ICONS = [
    // Arrows and navigation
    "arrow-up", "arrow-down", "arrow-left", "arrow-right",
    "arrow-up-right", "arrow-up-left", "arrow-down-right", "arrow-down-left",
    "arrow-left-right", "arrow-up-down", "chevron-up", "chevron-down",
    "chevron-left", "chevron-right", "chevrons-up", "chevrons-down",
    "chevrons-left", "chevrons-right", "corner-up-left", "corner-up-right",
    "corner-down-left", "corner-down-right", "move", "move-up-right",
    "move-down-left", "move-diagonal", "refresh-cw", "refresh-ccw",
    "rotate-cw", "rotate-ccw", "repeat", "undo", "redo",

    // Pointers and cursors
    "mouse-pointer", "mouse-pointer-click", "pointer", "hand",
    "locate", "locate-fixed", "crosshair", "maximize", "minimize",
    "maximize-2", "minimize-2", "scan", "scan-line", "fullscreen",
    "arrow-big-up", "arrow-big-down", "arrow-big-left", "arrow-big-right",

    // Communication and social
    "mail", "phone", "message-circle", "message-square", "send", "inbox",
    "at-sign", "link", "link-2", "unlink", "globe", "wifi", "rss", "share",
    "share-2", "megaphone", "bell", "bell-off", "quote", "thumbs-up",
    "thumbs-down", "heart-handshake", "mail-open", "mail-check",

    // Symbols and glyphs
    "heart", "heart-crack", "heart-plus", "heart-minus", "star", "star-half",
    "badge-check", "badge-info", "badge-percent", "badge-question-mark",
    "flag", "flag-triangle-right", "bookmark", "tag", "tags", "gift",
    "award", "trophy", "medal", "crown", "gem", "sparkles", "sparkle",
    "zap", "zap-off", "flame", "snowflake", "sun", "moon", "cloud",
    "cloud-sun", "cloud-rain", "cloud-snow", "cloud-lightning", "cloudy",
    "umbrella", "wind", "droplet", "droplets", "waves-horizontal",
    "waves-vertical",
    "mountain", "tree-pine", "leaf", "leafy-green", "flower", "flower-2",
    "sprout", "recycle", "sunrise", "sunset", "rainbow", "thermometer",

    // People
    "user", "users", "user-plus", "user-minus", "user-check", "user-x",
    "user-round", "users-round", "contact", "contact-round", "smile",
    "frown", "meh", "laugh", "baby", "person-standing", "accessibility",
    "hand-helping", "id-card",

    // Commerce and shopping
    "shopping-cart", "shopping-basket", "shopping-bag", "store", "package",
    "package-2", "box", "boxes", "truck", "credit-card", "banknote",
    "wallet", "receipt", "receipt-text", "percent", "funnel", "funnel-plus",
    "ticket", "ticket-percent", "barcode", "qr-code", "scale", "calculator",
    "piggy-bank", "coins", "circle-dollar-sign", "dollar-sign", "euro",
    "hand-coins", "trending-up", "trending-down", "chart-line",
    "chart-bar", "chart-column", "chart-pie", "activity", "gauge",

    // Time and calendar
    "clock", "alarm-clock", "timer", "hourglass", "calendar",
    "calendar-days", "calendar-check", "calendar-clock", "calendar-x",
    "calendar-heart", "watch",

    // Text editing and content
    "type", "text-cursor", "text-cursor-input", "text-quote", "text-wrap",
    "text-search", "pilcrow", "bold", "italic", "underline",
    "strikethrough", "list", "list-checks", "list-ordered", "spell-check",
    "highlighter", "pen", "pen-line", "pencil", "pencil-line", "brush",
    "paintbrush", "paint-roller", "pipette", "scissors", "clipboard",
    "clipboard-check", "clipboard-list", "copy", "files", "file",
    "file-text", "file-check", "file-x", "file-plus", "file-minus",
    "file-image", "notebook", "book", "book-open", "bookmark-plus",
    "library", "graduation-cap", "newspaper", "feather",

    // Media and photos
    "image", "image-plus", "image-off", "images", "camera", "camera-off",
    "video", "video-off", "film", "clapperboard", "play", "pause",
    "skip-back", "skip-forward", "rewind", "fast-forward", "volume",
    "volume-1", "volume-2", "volume-x", "music", "music-2", "music-3",
    "music-4", "mic", "mic-off", "podcast", "radio", "tv", "lightbulb",
    "lamp", "flashlight", "aperture", "focus", "palette", "swatch-book",

    // Devices
    "smartphone", "tablet", "laptop", "monitor", "watch", "headphones",
    "speaker", "hard-drive", "cpu", "memory-stick", "battery",
    "battery-charging", "power", "power-off", "plug", "plug-zap", "usb",
    "signal", "signal-high", "signal-low", "signal-zero",

    // Travel and places
    "map", "map-pin", "map-pinned", "navigation", "compass", "car",
    "car-front", "bike", "plane", "train-front", "ship", "anchor", "fuel",
    "route", "footprints", "sailboat", "rocket", "plane-takeoff",
    "plane-landing", "luggage", "hotel", "bed", "armchair", "door-open",
    "house", "house-heart", "house-plus", "building", "building-2",
    "warehouse", "factory", "church", "school", "hospital", "stethoscope",
    "pill", "syringe", "heart-pulse", "briefcase",

    // Status and feedback
    "info", "circle-question-mark", "badge-alert", "triangle-alert",
    "octagon-alert", "circle-alert", "check", "check-check", "circle-check",
    "circle-check-big", "x", "circle-x", "plus", "circle-plus", "minus",
    "circle-minus", "square-plus", "square-minus", "square-check",
    "square-x", "square", "square-dashed", "circle", "circle-dashed",
    "triangle", "triangle-right", "diamond", "hexagon", "pentagon",
    "octagon", "dot", "ellipsis", "ellipsis-vertical", "ban",

    // UI controls
    "search", "search-check", "search-x", "funnel-x", "sliders-horizontal",
    "sliders-vertical", "settings", "settings-2", "cog", "wrench",
    "hammer", "toggle-left", "toggle-right", "circle-slash", "slash",
    "external-link", "upload", "download", "cloud-upload", "cloud-download",
    "log-in", "log-out", "user-cog", "panel-left", "panel-right",
    "panel-bottom", "panel-top", "layout-grid", "layout-list",
    "layout-template", "grid-2x2", "grid-2x2-check", "grid-3x3", "rows-2",
    "rows-3", "columns-2", "columns-3", "gallery-vertical",
    "gallery-horizontal", "stretch-horizontal", "stretch-vertical",
    "arrow-left-from-line", "arrow-right-from-line", "arrow-up-from-line",
    "arrow-down-from-line", "fold-horizontal", "fold-vertical",
    "unfold-horizontal", "unfold-vertical",

    // Food and drink
    "apple", "banana", "cherry", "citrus", "grape", "carrot", "salad",
    "pizza", "sandwich", "cookie", "cake", "cake-slice", "candy",
    "candy-cane", "ice-cream-cone", "cup-soda", "coffee", "wine", "beer",
    "milk", "egg", "egg-fried", "fish", "shrimp", "croissant", "utensils",
    "utensils-crossed", "chef-hat", "cooking-pot", "popcorn", "drumstick",
    "soup",

    // Sports, games and hobbies
    "target", "goal", "volleyball", "dumbbell", "gamepad", "gamepad-2",
    "dices", "dice-1", "dice-2", "dice-3", "dice-4", "dice-5", "dice-6",
    "puzzle", "brain", "bot", "bot-message-square", "ghost", "skull",
    "swords", "sword", "wand", "wand-sparkles", "party-popper",
    "cat", "dog", "bird", "rabbit", "turtle", "bug", "bug-off", "snail",
    "paw-print", "bone", "trees", "tree-deciduous", "tree-palm",

    // Nature and science
    "sun-dim", "sun-medium", "sun-moon", "haze", "cloudy", "cloud-drizzle",
    "cloud-fog", "tornado", "thermometer-sun", "thermometer-snowflake",
    "orbit", "satellite", "satellite-dish", "telescope", "microscope",
    "flask-conical", "flask-round", "test-tube", "atom", "dna", "binary",
    "code", "code-xml", "terminal", "square-terminal", "command",
    "keyboard", "bluetooth", "bluetooth-off", "cast", "wifi-off",

    // Work and files
    "kanban", "chart-gantt", "chart-bar", "chart-bar-big", "chart-bar-stacked",
    "chart-pie", "chart-spline", "chart-area", "chart-scatter",
    "presentation", "flip-horizontal-2", "flip-vertical-2", "move-3d",
    "rotate-3d", "scale-3d", "ruler", "drafting-compass", "git-branch",
    "git-commit-horizontal", "git-compare", "git-fork", "git-merge",
    "git-pull-request", "network", "folder", "folder-open", "folder-plus",
    "folder-check", "archive", "archive-restore", "trash", "trash-2",
    "lock", "lock-open", "lock-keyhole", "shield", "shield-check",
    "shield-x", "shield-off", "shield-half", "shield-plus", "key",
    "key-round", "eye", "eye-off", "siren",
];

// Extra searchable keywords per base word, so "picture" also finds
// "image", "sale" finds "badge-percent", and so on.
const SYNONYMS = {
    picture: ["image", "photo"],
    photo: ["image", "camera"],
    arrow: [],
    direction: ["arrow", "navigation", "compass"],
    close: ["x"],
    cancel: ["x", "ban"],
    add: ["plus"],
    remove: ["minus"],
    delete: ["trash"],
    edit: ["pen", "pencil"],
    write: ["pen", "pencil"],
    settings: ["cog", "sliders"],
    profile: ["user", "contact"],
    account: ["user"],
    mail: ["email", "envelope"],
    email: ["mail"],
    phone: ["call", "smartphone"],
    call: ["phone"],
    message: ["chat"],
    chat: ["message"],
    percent: ["sale", "discount", "offer", "percent"],
    badge: ["sale", "discount", "offer"],
    calendar: ["date"],
    date: ["calendar"],
    time: ["clock"],
    download: ["save"],
    save: ["download", "bookmark"],
    search: ["find"],
    find: ["search"],
    warning: ["triangle-alert"],
    error: ["circle-x", "circle-alert"],
    question: ["circle-question-mark"],
    help: ["circle-question-mark"],
    picture2: ["image"],
    image: ["picture"],
    gallery: ["images"],
    movie: ["film", "clapperboard"],
    cinema: ["clapperboard"],
    game: ["gamepad"],
    sport: ["trophy", "dumbbell"],
    fitness: ["dumbbell", "heart-pulse"],
    gym: ["dumbbell"],
    weather: ["cloud", "sun"],
    sunny: ["sun"],
    night: ["moon"],
    rain: ["cloud-rain"],
    snow: ["cloud-snow"],
    nature: ["leaf", "tree-pine"],
    eco: ["leaf", "sprout"],
    gift: ["present"],
    present: ["gift"],
    party: ["party-popper"],
    celebrate: ["party-popper"],
    win: ["trophy"],
    prize: ["trophy", "medal"],
    aim: ["target"],
    launch: ["rocket"],
    startup: ["rocket"],
    grow: ["trending-up", "sprout"],
    chart: ["chart-line", "chart-bar"],
    graph: ["chart-line"],
    stats: ["chart-column"],
    analytics: ["chart-line", "activity"],
    internet: ["globe", "wifi"],
    web: ["globe"],
    world: ["globe"],
    location: ["map-pin"],
    pin: ["map-pin"],
    place: ["map-pin"],
    address: ["map-pin"],
    idea: ["lightbulb"],
    tip: ["lightbulb"],
    alert: ["bell"],
    notification: ["bell"],
    news: ["newspaper"],
    blog: ["pen", "newspaper"],
    article: ["newspaper", "file-text"],
    comment: ["message-circle"],
    reply: ["corner-up-left"],
    like: ["thumbs-up", "heart"],
    love: ["heart"],
    favorite: ["star", "heart", "bookmark"],
    follow: ["user-plus"],
    subscribe: ["rss"],
    feed: ["rss"],
    live: ["radio", "video"],
    stream: ["radio"],
    microphone: ["mic"],
    audio: ["volume"],
    sound: ["volume"],
    mute: ["volume-x"],
    music: ["song"],
    song: ["music"],
    selfie: ["camera"],
    portrait: ["user", "image"],
    tree: ["tree-pine"],
    forest: ["tree-pine"],
    plant: ["sprout"],
    garden: ["flower", "sprout"],
    water: ["droplet"],
    drop: ["droplet"],
    ocean: ["waves"],
    sea: ["waves"],
    space: ["rocket", "orbit"],
    science: ["flask-conical", "atom"],
    lab: ["flask-conical"],
    research: ["microscope"],
    experiment: ["flask-conical"],
    chemistry: ["flask-conical"],
    biology: ["dna"],
    code: ["programming", "terminal"],
    programming: ["code", "terminal"],
    developer: ["code", "terminal"],
    robot: ["bot"],
    automation: ["bot"],
    ai: ["bot", "brain"],
    tool: ["wrench"],
    repair: ["wrench"],
    fix: ["wrench"],
    build: ["hammer"],
    paint: ["paintbrush"],
    color: ["palette"],
    draw: ["pen", "brush"],
    design: ["pen", "palette"],
    art: ["palette"],
    note: ["notebook"],
    memo: ["notebook"],
    document: ["file"],
    page: ["file"],
    paper: ["file"],
    contract: ["file-text"],
    signature: ["pen-line"],
    form: ["clipboard-list"],
    survey: ["clipboard-list"],
    quiz: ["circle-question-mark"],
    exam: ["graduation-cap"],
    degree: ["graduation-cap"],
    education: ["graduation-cap"],
    student: ["graduation-cap"],
    knowledge: ["book", "brain"],
    creative: ["palette", "lightbulb"],
    happy: ["smile"],
    funny: ["laugh"],
    sad: ["frown"],
    romance: ["heart"],
    jewel: ["gem"],
    luxury: ["gem", "crown"],
    royal: ["crown"],
    king: ["crown"],
    boss: ["crown"],
    team: ["users"],
    staff: ["users"],
    employee: ["user"],
    customer: ["user"],
    client: ["user"],
    partner: ["handshake"],
    deal: ["handshake"],
    meeting: ["users", "calendar"],
    conference: ["users", "presentation"],
    slides: ["presentation"],
    pitch: ["presentation", "megaphone"],
    marketing: ["megaphone"],
    promotion: ["megaphone", "badge-percent"],
    advertising: ["megaphone"],
    campaign: ["megaphone", "target"],
    brand: ["tag", "flag"],
    product: ["package", "box"],
    delivery: ["truck"],
    shipping: ["truck"],
    order: ["shopping-cart"],
    purchase: ["shopping-cart"],
    buy: ["shopping-cart"],
    sell: ["store"],
    payment: ["credit-card"],
    card: ["credit-card"],
    cash: ["banknote"],
    money: ["banknote"],
    coin: ["coins"],
    savings: ["piggy-bank"],
    invest: ["trending-up"],
    stock: ["chart-line"],
    finance: ["chart-line"],
    bank: ["landmark"],
    company: ["building"],
    enterprise: ["building"],
    organization: ["building"],
    industry: ["factory"],
    storage: ["warehouse"],
    inventory: ["boxes"],
    logistics: ["truck", "route"],
    worldwide: ["globe"],
    international: ["globe"],
    local: ["map-pin"],
    shop: ["store"],
    market: ["store"],
    restaurant: ["utensils"],
    cafe: ["coffee"],
    hotel: ["bed"],
    sleep: ["bed", "moon"],
    rest: ["bed"],
    relax: ["armchair"],
    wellness: ["heart-pulse"],
    meditation: ["brain", "flower"],
    mind: ["brain"],
    health: ["heart-pulse"],
    doctor: ["stethoscope"],
    medicine: ["pill"],
    pharmacy: ["pill"],
    vaccine: ["syringe"],
    emergency: ["siren"],
    accessible: ["accessibility"],
    discount: ["percent", "badge-percent"],
    coupon: ["ticket-percent"],
    voucher: ["ticket"],
    event: ["calendar", "ticket"],
    appointment: ["calendar"],
    schedule: ["calendar"],
    plan: ["calendar"],
    reminder: ["bell"],
    alarm: ["alarm-clock"],
    deadline: ["hourglass", "timer"],
    urgent: ["alarm-clock", "zap"],
    important: ["star", "triangle-alert"],
    priority: ["arrow-up", "star"],
    newsletter: ["newspaper"],
    story: ["book-open"],
    post: ["send", "message-square"],
    broadcast: ["radio"],
    headset: ["headphones"],
    playlist: ["list-music"],
    album: ["disc"],
    vinyl: ["disc"],
    landscape: ["mountain", "image"],
    beach: ["sun", "waves"],
    planet: ["orbit"],
    mobile: ["smartphone"],
    device: ["smartphone", "laptop"],
    computer: ["laptop", "monitor"],
    screen: ["monitor"],
    display: ["monitor"],
    duplicate: ["copy"],
    paste: ["clipboard"],
    cut: ["scissors"],
    share: ["share-2"],
    send: ["message"],
    mention: ["at-sign"],
    label: ["tag"],
    price: ["tag"],
    sale: ["badge-percent", "percent"],
    cheap: ["badge-percent"],
    offer: ["badge-percent"],
    birthday: ["cake", "party-popper"],
    wedding: ["heart"],
    holiday: ["christmas-tree"],
    christmas: ["christmas-tree"],
    winter: ["snowflake"],
    summer: ["sun"],
    spring: ["flower"],
    autumn: ["leaf"],
    fall: ["leaf"],
};

// Deduplicate while preserving order.
const wanted = [...new Set(COMMON_ICONS)];

function escapeAttr(value) {
    return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function nodeToMarkup(node) {
    return node
        .map(([tag, attrs]) => {
            const a = Object.entries(attrs || {})
                .map(([k, v]) => `${k}="${escapeAttr(v)}"`)
                .join(" ");
            return `<${tag} ${a}/>`;
        })
        .join("");
}

function buildTags(name) {
    const words = name.split("-").filter(Boolean);
    const tags = new Set(words);
    for (const word of words) {
        const syns = SYNONYMS[word];
        if (syns) {
            for (const s of syns) {
                tags.add(s);
            }
        }
    }
    return [...tags];
}

const files = (await readdir(LUCIDE_DIR)).filter((f) => f.endsWith(".mjs"));
const available = new Set(files.map((f) => f.replace(/\.mjs$/, "")));

const entries = [];
const missing = [];
for (const name of wanted) {
    if (!available.has(name)) {
        missing.push(name);
        continue;
    }
    const mod = await import(join(LUCIDE_DIR, `${name}.mjs`));
    const node = mod.default;
    if (!Array.isArray(node) || !node.length) {
        missing.push(`${name} (empty)`);
        continue;
    }
    entries.push({ name, tags: buildTags(name), body: nodeToMarkup(node) });
}

entries.sort((a, b) => a.name.localeCompare(b.name));

const data = entries.map(
    (e) =>
        `    { name: ${JSON.stringify(e.name)}, tags: ${JSON.stringify(e.tags)}, body: ${JSON.stringify(e.body)} }`
);

const output = `/** @odoo-module **/

/**
 * Static Lucide icon library for the social image editor (design: bundle
 * size conscious alternative to render-engine-os importing the whole
 * lucide package). Generated by scripts/build_icon_library.mjs from the
 * lucide package; do not edit by hand, re-run the script instead.
 *
 * Each entry: { name, tags, body } where body is the inner SVG markup
 * (no outer <svg> tag) in a 24x24 viewBox, drawn with stroke, not fill.
 * The editor wraps it in an <svg> with the chosen color as stroke, loads
 * it via fabric.loadSVGFromString and recolors by changing child strokes.
 */

export const ICON_LIBRARY = [
${data.join(",\n")}
];

/**
 * Search the icon library by query against names and tags. Pure function
 * so it can be unit-tested under plain Node. Every whitespace-separated
 * term must match the name or a tag; scoring ranks exact name matches
 * first, then name prefixes, then name substrings, then tag matches.
 * Results come back in score order, stable within a score, capped at
 * limit (default 200).
 */
export function searchIcons(query, limit = 200) {
    const q = (query || "").toLowerCase().trim();
    if (!q) {
        return ICON_LIBRARY.slice(0, limit);
    }
    const terms = q.split(/\\s+/).filter(Boolean);
    const scored = [];
    for (const icon of ICON_LIBRARY) {
        let worst = 0;
        let matched = true;
        for (const term of terms) {
            let score;
            if (icon.name === term) {
                score = 0;
            } else if (icon.name.startsWith(term)) {
                score = 1;
            } else if (icon.name.includes(term)) {
                score = 2;
            } else if (icon.tags.some((t) => t.includes(term))) {
                score = 3;
            } else {
                matched = false;
                break;
            }
            if (score > worst) {
                worst = score;
            }
        }
        if (matched) {
            scored.push({ icon, score: worst });
        }
    }
    scored.sort((a, b) => a.score - b.score);
    return scored.slice(0, limit).map((s) => s.icon);
}
`;

await writeFile(OUT_FILE, output);

const bytes = Buffer.byteLength(output, "utf8");
console.log(`icons written: ${entries.length}`);
console.log(`output size: ${(bytes / 1024).toFixed(1)} KB (${OUT_FILE})`);
if (missing.length) {
    console.log(`unknown/empty names skipped (${missing.length}):`);
    for (const m of missing) {
        console.log(`  - ${m}`);
    }
}
