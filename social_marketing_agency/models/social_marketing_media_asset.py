# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SocialMarketingMediaAsset(models.Model):
    _name = 'social_marketing.media.asset'
    """Media library asset scoped to a brand."""

    _inherit = ['social_marketing.media.asset', 'social.brand.focus.mixin']

    brand_id = fields.Many2one(
        'social.brand', string='Brand',
        default=lambda self: self._get_default_brand())
