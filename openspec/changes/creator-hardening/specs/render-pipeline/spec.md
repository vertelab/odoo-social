## ADDED Requirements

### Requirement: Scene image URLs are allowlisted

The render service SHALL only load image content from `data:` URLs and from `/web/image` paths resolved against the configured API base URL. Any other URL in a scene (other HTTP hosts, `file://`, other relative paths) SHALL be refused before loading with an error naming the offending layer, and the request SHALL fail with HTTP 400.

#### Scenario: Localhost URL refused

- **WHEN** a scene image src points at `http://127.0.0.1/...` or any non-allowlisted host
- **THEN** the render is refused with an error naming the layer and no outbound fetch occurs

#### Scenario: File URL refused

- **WHEN** a scene image src uses `file://`
- **THEN** the render is refused before any file access occurs

#### Scenario: Web image and data URLs pass

- **WHEN** a scene contains only `data:` URLs and `/web/image` paths under the API base
- **THEN** rendering proceeds normally

### Requirement: Render dimensions are capped

The `/render` endpoint SHALL reject width or height that are not integers in the range 16 to 8192, or whose pixel product exceeds 67108864, with HTTP 400 naming the violated limit.

#### Scenario: Oversized canvas rejected

- **WHEN** a caller posts width 20000 and height 20000
- **THEN** the service responds 400 naming the limit without allocating a canvas

#### Scenario: Valid dimensions pass

- **WHEN** a caller posts dimensions within the caps
- **THEN** rendering proceeds

### Requirement: No placeholder token ships

The render service SHALL refuse to start with a known placeholder token (such as `change-me`), and the shipped Dockerfile SHALL NOT set a default token.

#### Scenario: Placeholder token refused

- **WHEN** the service starts with `RENDER_TOKEN=change-me`
- **THEN** startup fails with a clear message telling the operator to set a real token
