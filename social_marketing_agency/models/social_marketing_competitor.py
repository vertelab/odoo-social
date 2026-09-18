# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SocialMarketingCompetitor(models.Model):
    _name = 'social_marketing.competitor'
    """Competitor scoped to a brand."""

    _inherit = ['social_marketing.competitor', 'social.brand.focus.mixin']

    brand_id = fields.Many2one(
        'social.brand', string='Brand',
        default=lambda self: self._get_default_brand())
