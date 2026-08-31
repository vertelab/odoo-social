# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
"""Pure, DB-free core of the data binding feature.

Mirrors the ``*_core`` pattern used on the JS side
(``render_service/render_core.mjs``): everything here is a plain function
over plain data, so it can be reasoned about and unit tested without an
ORM cursor.

The single rule this module exists to enforce: a token is *looked up*,
never evaluated. There is no expression engine here, and there must never
be one. A template body is ordinary text in a database column, so anything
able to write that column would otherwise be able to read (or write) the
whole database through the renderer.
"""

import re

# A token is ``{{ name }}`` with tolerated internal whitespace. The capture
# is deliberately permissive so that a malformed or hostile token is still
# consumed by the substitution (and replaced by an empty string) instead of
# being left visible in the rendered output.
TOKEN_RE = re.compile(r'\{\{([^{}]*)\}\}')


def substitute_tokens(text, values, on_unknown=None):
    """Replace every ``{{ token }}`` in `text` by ``values[token]``.

    `values` is a plain ``{token: string}`` mapping, normally built from the
    bindings registered on the template being rendered. A token that is not
    a key of `values` renders as an empty string, and `on_unknown` (if
    given) is called with the token name so the caller can log it.

    Nothing in `text` is ever evaluated: unknown input is dropped, not run.
    """
    if not text:
        return ''

    def _replace(match):
        token = (match.group(1) or '').strip()
        if token in values:
            value = values[token]
            return '' if value is None else str(value)
        if on_unknown:
            on_unknown(token)
        return ''

    return TOKEN_RE.sub(_replace, str(text))


def collect_tokens(text):
    """Return the ordered list of distinct token names used in `text`."""
    seen = []
    for match in TOKEN_RE.finditer(text or ''):
        token = (match.group(1) or '').strip()
        if token and token not in seen:
            seen.append(token)
    return seen


def web_image_source(model_name, res_id, field_name):
    """Return the ``/web/image/...`` source used by scene image layers.

    This is the convention ``absolutizeFileUrl()`` in
    ``render_service/render_core.mjs`` already understands, so binary
    fields resolve to something the render service can fetch rather than
    to a stringified blob.
    """
    if not (model_name and res_id and field_name):
        return ''
    return '/web/image/%s/%s/%s' % (model_name, res_id, field_name)
