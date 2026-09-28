# Render Service (social.image.template)

Server-side Fabric.js renderer for `social.image.template` in Odoo
(`social_marketing`). Deployment is handled by Salt (LXD container or
systemd service on the Odoo minion); the code lives here so it is versioned
with the module.

## API

```
POST /render
  Authorization: Bearer <RENDER_TOKEN>
  {
    "scene_json": { ... Fabric canvas.toJSON() ... },
    "width": 1200,                   # integer 16..8192
    "height": 630,                   # integer 16..8192, width*height <= 67108864
    "bindings": { "headline": "Sommarerbjudande", "cta": "Läs mer" },
    "format": "png" | "svg"          # default png
  }
  → image/png  (default)  |  image/svg+xml (format=svg)

GET /health → { "status": "ok", "service": "render-odoo", "fonts_registered": 2 }
GET /fonts          (bearer token) → { "fonts": [{ "family": "...", "file": "..." }] }
POST /fonts/reload  (bearer token) → rescan the fonts directory
```

Text layers in the scene may contain `{{field}}` tokens; values from
`bindings` are substituted at render time. Tokens support dotted relation
paths (`{{categ_id.name}}`) and chained pipe transforms
(`{{name|upper|trim}}`); available pipes: `upper`, `lower`, `title`,
`capitalize`, `trim` (with `uppercase`/`lowercase` aliases). Unknown
tokens are left untouched.

Custom props (namespaced with `_`, they survive Fabric `loadFromJSON`):

- `"_hideIfEmpty": { "field": "is_new" }` on any layer: hidden when the
  bound value is empty (e.g. a coloured label behind a text that may be
  absent).
- `"_required": { "field": "image_1920" }` on any layer: aborts the render
  with HTTP 400 and an error naming the layer when the bound value is
  empty.
- `"_dataBinding": { "field": "image_1920" }` on an image layer: swaps the
  layer's src for the bound value (typically a `data:` URL produced by
  Odoo from a binary field). An empty value hides the layer. The new image
  is re-fitted to the layer's design-time frame with object-fit: cover
  semantics (scale to fill, crop overflow centered), matching the editor
  preview.

Image layers may only reference `data:` URLs (self-contained, from the
browser editor or from Odoo binary fields) or `/web/image/...` paths
under `API_BASE_URL`; relative `/web/image` paths are rewritten against
`API_BASE_URL` so the container can fetch them. Anything else (other
http(s) hosts, `file://`, other relative paths) is refused with HTTP
400 naming the offending layer, before any fetch happens. The scan
walks nested groups and runs both on the scene as posted and on the
scene after binding substitution.

`/web/image` fetches carry no credentials, so they only render public
attachments. Images that are not public must be bound from Odoo as
binary fields, which the binding engine already encodes as `data:` URLs
(see `_dataBinding` above); an absolute URL under `API_BASE_URL` in the
scene passes the allowlist but still fetches unauthenticated.

Binding resolution itself lives in Odoo
(`social_image_creator/models/social_image_binding.py`): the model walks
the scene, reads the referenced fields from the chosen record and sends
plain `{field_path: value}` bindings. The service only substitutes.

## Fonts

Brand fonts are registered server-side (design D6) so PNGs render
identically to the editor. Drop `.ttf`/`.otf` files in `fonts/`; the
file basename without extension is the family name used in Fabric
(`fonts/README.md` documents the convention, including the CDN trade-
off: Google Fonts loaded only via the editor's CDN are NOT registered,
rendered PNGs fall back for them, and parity-safe fonts are the ones in
`fonts/`). Registration happens at startup and on `POST /fonts/reload`;
`GET /fonts` and the `fonts_registered` field on `/health` list what is
registered.

## Fabric version lockstep

The editor loads a bundled Fabric from
`social_image_creator/static/lib/fabric/index.min.js`; the service pins
Fabric in `package.json`. Scene JSON is not portable across Fabric
versions, so the two must match:

```bash
make check-fabric   # scripts/check_fabric_sync.py
```

Bump both in the same commit.

## Security

- Bearer token (`RENDER_TOKEN`); unauthenticated requests are rejected
  with 401. Startup refuses an empty token and the known placeholder
  values (`change-me`, `changeme`, `change_me`, `token`, `secret`,
  `password`, case-insensitive); `RENDER_ALLOW_NO_AUTH=1` is the
  explicit opt-in for local development.
- Scene image srcs are allowlisted: `data:` URLs and `/web/image` paths
  under `API_BASE_URL` only, scanned before Fabric loads the scene.
  See "Image layers" above for the non-public-image rule.
- Canvas size is capped: width and height must be integers 16..8192
  with a pixel product of at most 67108864; larger requests get a 400
  without a canvas being allocated.
- Binding values are injected as text only. For `format=svg` output the
  substituted text is XML-escaped, so a value like `<script>` can never
  inject markup into the produced SVG. PNG output is raster and inert.
- Request body limited to 8 MB (`MAX_BODY_MB`).
- Run the container without outbound network access beyond the Odoo
  API (`API_BASE_URL`), e.g. with firewall or proxy egress rules. The
  allowlist is the primary control; a strict egress profile means a bad
  URL cannot leak data even if the allowlist is ever bypassed.

## Environment

| Variable        | Default            | Description                                          |
|-----------------|--------------------|------------------------------------------------------|
| `PORT`          | `8600`             | HTTP port                                            |
| `RENDER_TOKEN`  | (none, required)   | Bearer token; empty and placeholder values refuse startup |
| `API_BASE_URL`  | `http://odoo:8069` | Odoo base for `/web/image` URL rewriting             |
| `MAX_BODY_MB`   | `8`                | Max JSON body size in MB                             |
| `FONTS_DIR`     | `./fonts`          | Directory scanned for font registration              |

## Tests

```bash
cd render_service
npm test                 # all tests; test_auth/test_security need node-canvas
node test_core.mjs       # fabric-free unit tests, run anywhere
node test_binding.mjs
node test_fonts.mjs
```

## Local dev

```bash
cd render_service
npm install
RENDER_TOKEN=dev-token API_BASE_URL=http://localhost:8069 node server.mjs
curl -H "Authorization: Bearer dev-token" -X POST localhost:8600/render \
  -H 'Content-Type: application/json' \
  -d '{"scene_json":{"version":"6.9.1","objects":[{"type":"textbox","left":60,"top":60,"width":600,"fontSize":48,"fontFamily":"Arial","fill":"#1a1a1a","text":"{{headline}}"}],"background":"#ffffff"},"width":1200,"height":630,"bindings":{"headline":"Hej världen"}}' \
  -o out.png
```
