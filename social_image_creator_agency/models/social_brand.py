# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
PALETTE_EXAMPLE = '["#003366", "#ff6600"]'


def parse_palette(value):
    """Parse and validate a brand color palette (spec: agency-brand-kit,
    design decision D5).

    ``value`` is what reaches the field: a list (API, imports, editor) or
    a string (hand-typed into the raw JSON widget; Odoo 18 ``fields.Json``
    keeps hand-typed text as a string instead of parsing it). Returns the
    palette as a list of ``#rrggbb`` strings. Raises ValueError with a
    human-readable, translated reason on anything else; the model layer
    turns that into a ValidationError carrying an example. Kept free of
    recordset logic so it stays unit-testable.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            raise ValueError(_("the palette text is not valid JSON"))
    if not isinstance(value, list):
        raise ValueError(_(
            "the palette must be a list of hex colors, not %s.")
            % type(value).__name__)
    for entry in value:
        if not isinstance(entry, str) or not HEX_COLOR_RE.match(entry):
            raise ValueError(_(
                "%r is not a hex color in #rrggbb form.") % (entry,))
    return value


def palette_error_message(reason):
    """Build the friendly, example-bearing error for a palette failure."""
    return _(
        "Color palette: %(reason)s. Expected a JSON list of hex colors "
        "in #rrggbb form, for example %(example)s.",
        reason=reason, example=PALETTE_EXAMPLE)


class SocialBrand(models.Model):
    """Brand kit for the image editor (spec: agency-brand-kit): a color
    palette beyond the single brand color, plus uploaded fonts.

    Palette is a JSON list of hex strings (simplest shape that covers the
    spec; a one2many of color lines would add no behavior). Fonts live in
    ``social.brand.font``; the logo already exists on the base model and is
    reused. All of it reaches the editor through the brand asset providers
    registered in static/src/js/brand_provider.js.

    The palette is validated by :func:`parse_palette` through a constraint
    (decision D5), so imports fail loudly too. ``create``/``write`` also
    normalize hand-typed JSON text into a real list: stored as text it
    would silently break the editor swatches, which expect an array.
    """

    _inherit = 'social.brand'

    palette = fields.Json(
        'Color Palette', default=list,
        help="JSON list of hex colors, e.g. [\"#003366\", \"#ff6600\"]. "
             "Offered as brand colors in the image editor for templates of "
             "this brand.")
    font_ids = fields.One2many(
        'social.brand.font', 'brand_id', string='Brand Fonts',
        help="Fonts uploaded for this brand. The family name must equal the "
             "file basename without extension (the render_service/fonts "
             "convention); copy the file into render_service/fonts/ (or use "
             "the line's Download button) to make it available for "
             "server-side rendering.")

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._prepare_palette_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        return super().write(self._prepare_palette_vals(vals))

    @api.model
    def _prepare_palette_vals(self, vals):
        """Normalize a hand-typed palette string into a parsed list so the
        stored value is real JSON (the editor swatches filter on an array).
        Unparseable text becomes the friendly ValidationError here; values
        that are not strings at all are left for the constraint."""
        if 'palette' not in vals:
            return vals
        value = vals['palette']
        if isinstance(value, str):
            if not value.strip():
                value = False
            else:
                try:
                    value = parse_palette(value)
                except ValueError as e:
                    raise ValidationError(palette_error_message(str(e))) from e
        return dict(vals, palette=value)

    @api.constrains('palette')
    def _check_palette(self):
        for brand in self:
            if not brand.palette:
                continue
            try:
                parse_palette(brand.palette)
            except ValueError as e:
                raise ValidationError(palette_error_message(str(e))) from e
