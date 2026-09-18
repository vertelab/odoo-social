# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class CommunicationPlan(models.Model):
    _name = 'communication.plan'
    """Communication plan scoped to a brand (via its policy)."""

    _inherit = ['communication.plan', 'social.brand.focus.mixin']

    brand_id = fields.Many2one(
        'social.brand', string='Brand', compute='_compute_brand_id', store=True,
        help="Brand of the plan's communication policy.")

    @api.depends('policy_id.brand_id')
    def _compute_brand_id(self):
        for plan in self:
            plan.brand_id = plan.policy_id.brand_id
