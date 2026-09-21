# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

"""Pure helpers for resolving template bindings against Odoo records.

Design decision D1: binding resolution happens in Odoo, substitution in
Node. This module owns the Odoo side: it walks a Fabric scene JSON, collects
every referenced field (text tokens, ``_hideIfEmpty``, ``_required`` and
``_dataBinding`` custom props), resolves each dotted field path against a
record and formats the values into the plain ``{field_path: value}`` dict
the render service substitutes.

Kept free of Odoo imports so the logic can be checked with plain
``python3`` (see scripts/check_social_image_binding.py). Failures raise
:class:`BindingError` (a ValueError); the model layer converts them to
UserError so both standalone checks and the ORM path exercise identical
logic.
"""

import base64
import re
from datetime import date, datetime

# {{field}} or {{dotted.path}} with optional chained pipes:
#   {{name|upper}}, {{categ_id.name|title|trim}}
# Mirrors the TOKEN_RE in render_service/render_core.mjs exactly.
TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*((?:\|[^}|]+)*)\}\}")

# Relation field types a dotted path may traverse.
RELATION_TYPES = ('many2one', 'one2one', 'reference', 'one2many', 'many2many')

# Custom props that carry a single binding field.
BINDING_PROPS = ('_hideIfEmpty', '_required', '_dataBinding')

_IMAGE_MIME_BY_MAGIC = (
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'\xff\xd8\xff', 'image/jpeg'),
    (b'GIF8', 'image/gif'),
)


class BindingError(ValueError):
    """A template binding could not be resolved (unknown field, illegal
    hop, required layer with an empty value)."""


def iter_tokens(text):
    """Yield (field_path, [pipe, ...]) for every token in `text`."""
    for match in TOKEN_RE.finditer(text or ''):
        pipes = [p.strip() for p in match.group(2).split('|') if p.strip()]
        yield match.group(1), pipes


def collect_scene_fields(scene):
    """Collect every field path referenced by a scene, as an ordered list.

    Picks up ``{{path}}`` tokens in text layers plus the ``field`` of every
    ``_hideIfEmpty`` / ``_required`` / ``_dataBinding`` custom prop. Pipe
    transforms are ignored for collection; they are applied by the
    renderer (Node) and the editor preview, not here.
    """
    fields = []
    seen = set()

    def add(name):
        if name and name not in seen:
            seen.add(name)
            fields.append(name)

    objects = (scene or {}).get('objects') or []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if isinstance(obj.get('text'), str):
            for path, _pipes in iter_tokens(obj['text']):
                add(path)
        for prop in BINDING_PROPS:
            rule = obj.get(prop)
            if isinstance(rule, dict):
                add(rule.get('field'))
    return fields


def resolve_field_path(record, path):
    """Walk a dotted field path against `record` and return the raw value.

    Relation hops traverse readable x2one relations directly and x2many
    relations via their first record. A hop that is not a relation, or a
    computed relation (unreadable in batch), raises BindingError naming
    the token. A missing value along the way (empty relation) returns
    None, which formats to an empty string downstream.
    """
    parts = [p for p in str(path or '').split('.') if p]
    if not parts:
        raise BindingError("Empty token path.")
    current = record
    for index, part in enumerate(parts):
        fields = getattr(current, '_fields', None) or {}
        if part not in fields:
            raise BindingError(
                "Unknown field %r in token %r (model %s)."
                % (part, path, getattr(current, '_name', '?')))
        field = fields[part]
        ftype = getattr(field, 'type', None)
        if index == len(parts) - 1:
            return current[part]
        if ftype not in RELATION_TYPES:
            raise BindingError(
                "Token %r: %r on model %s is not a relation."
                % (path, part, getattr(current, '_name', '?')))
        if getattr(field, 'compute', None):
            raise BindingError(
                "Token %r: relation %r on model %s is computed and "
                "cannot be traversed." % (path, part, current._name))
        value = current[part]
        if not value:
            return None
        if ftype in ('many2one', 'one2one', 'reference'):
            current = value
        else:
            # x2many: predictable, keep it to the first record.
            current = value[:1]
    return None


def guess_image_mimetype(data):
    """Sniff a binary payload's image mimetype from its magic bytes."""
    if not isinstance(data, (bytes, bytearray)):
        return 'application/octet-stream'
    for magic, mimetype in _IMAGE_MIME_BY_MAGIC:
        if data[:len(magic)] == magic:
            return mimetype
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return 'application/octet-stream'


def format_binding_value(value):
    """Format a raw field value for the render service bindings dict.

    - None / False become '' (an unset many2one reads as False)
    - bytes become a data URL (image fields), mimetype sniffed
    - records (many2one leaf) become their display_name
    - recordsets (x2many leaf) become the first record's display_name
    - everything else falls through str(), keeping newlines in text values
    """
    if value is None or value is False:
        return ''
    if isinstance(value, (bytes, bytearray)):
        return 'data:%s;base64,%s' % (
            guess_image_mimetype(value),
            base64.b64encode(bytes(value)).decode('ascii'))
    if isinstance(value, bool):
        return 'True'
    if hasattr(value, '_name'):  # Odoo recordset (many2one or x2many leaf)
        first = value[:1]
        return first.display_name if first else ''
    return str(value)


def is_empty_value(value):
    """Empty means: unset, False, or a whitespace-only string."""
    return (value is None or value is False
            or (isinstance(value, str) and value.strip() == ''))


def build_bindings(record, scene):
    """Resolve every field referenced by `scene` against `record`.

    Returns ``{field_path: formatted_value}``; raises BindingError naming
    the offending token when a path cannot be resolved.
    """
    bindings = {}
    for path in collect_scene_fields(scene):
        value = resolve_field_path(record, path)
        bindings[path] = format_binding_value(value)
    return bindings


def check_required_layers(scene, bindings):
    """Abort when a layer marked `_required` resolves to empty.

    Raises BindingError naming the layer (its `_layerName`, falling back
    to the Fabric type) and the field, so the user can fix the template.
    """
    for obj in (scene or {}).get('objects') or []:
        if not isinstance(obj, dict):
            continue
        rule = obj.get('_required')
        if not isinstance(rule, dict) or not rule.get('field'):
            continue
        field = rule['field']
        if is_empty_value(bindings.get(field)):
            layer = obj.get('_layerName') or obj.get('type') or 'layer'
            raise BindingError(
                'Required binding %r on layer %r resolved to an empty '
                'value.' % (field, layer))
