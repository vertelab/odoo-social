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
    "width": 1200,
    "height": 630,
    "bindings": { "headline": "Sommarerbjudande", "cta": "Läs mer" },
    "format": "png" | "svg"          # default png
  }
  → image/png  (default)  |  image/svg+xml (format=svg)

GET /health → { "status": "ok", "service": "render-odoo" }
```

Text layers in the scene may contain `{{placeholder}}` tokens; values from
`bindings` are substituted at render time. A layer with
`"_hideIfEmpty": { "placeholder": "name" }` is hidden when the bound value
is empty (e.g. a coloured label behind a text that may be absent).

Image layers store either `data:` URLs (self-contained, from the browser
editor) or `/web/image/...` URLs (Odoo attachments); relative `/web/image`
paths are rewritten against `API_BASE_URL` so the container can fetch them.

## Security

- Bearer token (`RENDER_TOKEN`); unauthenticated requests are rejected
  with 401 (unless `RENDER_TOKEN` is unset = dev mode).
- Binding values are injected as text only. For `format=svg` output the
  substituted text is XML-escaped, so a value like `<script>` can never
  inject markup into the produced SVG. PNG output is raster and inert.
- Request body limited to 8 MB (`MAX_BODY_MB`).

## Environment

| Variable        | Default            | Description                              |
|-----------------|--------------------|------------------------------------------|
| `PORT`          | `8600`             | HTTP port                                |
| `RENDER_TOKEN`  | `change-me`        | Bearer token (set from Odoo pillar)      |
| `API_BASE_URL`  | `http://odoo:8069` | Odoo base for `/web/image` URL rewriting |
| `MAX_BODY_MB`   | `8`                | Max JSON body size in MB                 |

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
