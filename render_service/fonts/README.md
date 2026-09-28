# Fonts for the render service

Drop font files in this directory to make them available to server-side
rendering. Registered fonts render identically to the editor; fonts that
are only loaded in the editor via the Google Fonts CDN are NOT registered
here and fall back to a default font in rendered PNGs. Parity-safe fonts
are the ones in this directory. This is the documented trade-off of
design D11: self-hosting the CDN fonts is a possible later change.

## Convention: file basename is the family name

The family name used in Fabric (editor `fontFamily`, scene JSON) must
equal the file basename without extension:

| File                        | Family name in Fabric  |
|-----------------------------|------------------------|
| `BrandonGrotesque-Bold.ttf` | `BrandonGrotesque-Bold` |
| `Inter-Regular.otf`         | `Inter-Regular`         |

If the editor uses a different name than the basename, the render service
silently falls back, which is the exact bug this directory exists to fix.

## Supported formats

- `.ttf` and `.otf` are supported everywhere node-canvas runs.
- `.woff` / `.woff2` are attempted but depend on the platform font stack
  (fontconfig in the container); a file that fails to register is logged
  and skipped, never fatal.

## When registration happens

- At service startup: every font file in this directory is registered.
- At runtime: `POST /fonts/reload` (bearer token required) rescans the
  directory, so a new font takes effect without a restart.

`GET /fonts` (bearer token required) lists the registered families and
files; `/health` reports the registered count. Use these to debug
"missing font" issues before suspecting the scene JSON.

## Deployment

The Dockerfile copies this directory into the image. Fonts added here are
versioned with the module, so editor code that references the family name
and the font file itself change in the same commit.
