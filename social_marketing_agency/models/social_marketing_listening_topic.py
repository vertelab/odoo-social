# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SocialMarketingListeningTopic(models.Model):
    _name = 'social_marketing.listening.topic'
    """Listening topic scoped to a brand — the customer's keyword monitoring."""

    _inherit = ['social_marketing.listening.topic', 'social.brand.focus.mixin']

    brand_id = fields.Many2one(
        'social.brand', string='Brand',
        default=lambda self: self._get_default_brand())
