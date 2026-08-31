# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SocialBrandLogo(models.Model):
    """A logo variant in a brand's kit.

    The image builder picks a variant by name (see
    ``social.brand.get_kit_logo``), for instance the inverted mark for a dark
    background.
    """

    _name = 'social.brand.logo'
    _description = 'Social Brand Logo'
    _order = 'sequence, id'

    VARIANTS = [
        ('primary', 'Primary'),
        ('inverted', 'Inverted'),
        ('mark', 'Mark'),
        ('wordmark', 'Wordmark'),
        ('other', 'Other'),
    ]

    brand_id = fields.Many2one(
        'social.brand', string='Brand', required=True, ondelete='cascade',
        index=True)
    name = fields.Char('Name', required=True)
    variant = fields.Selection(
        VARIANTS, string='Variant', required=True, default='primary')
    image = fields.Binary('Image', attachment=True, required=True)
    sequence = fields.Integer('Sequence', default=10)
