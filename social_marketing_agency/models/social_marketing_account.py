# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SocialMarketingAccount(models.Model):
    _name = 'social_marketing.account'
    """Social account scoped to a brand (the customer's own accounts)."""

    _inherit = ['social_marketing.account', 'social.brand.focus.mixin']

    brand_id = fields.Many2one(
        'social.brand', string='Brand',
        default=lambda self: self._get_default_brand())
