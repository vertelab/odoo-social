# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class DashboardDashboard(models.Model):
    """Per-brand BI dashboard (dashboard_vrtl)."""

    _inherit = 'dashboard.dashboard'

    brand_id = fields.Many2one(
        'social.brand', string='Brand', copy=False,
        help="Brand this dashboard belongs to. Charts are scoped to the brand.")
