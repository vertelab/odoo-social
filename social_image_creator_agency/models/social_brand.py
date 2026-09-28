# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class SocialBrand(models.Model):
    """Brand kit for the image editor (spec: agency-brand-kit): a color
    palette beyond the single brand color, plus uploaded fonts.

    Palette is a JSON list of hex strings (simplest shape that covers the
    spec; a one2many of color lines would add no behavior). Fonts live in
    ``social.brand.font``; the logo already exists on the base model and is
    reused. All of it reaches the editor through the brand asset providers
    registered in static/src/js/brand_provider.js.
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
