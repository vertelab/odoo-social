# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResPartner(models.Model):
    """Customer (res.partner) extension: zero or more brands."""

    _inherit = 'res.partner'

    brand_ids = fields.One2many(
        'social.brand', 'partner_id', string='Brands',
        help="Brands owned by this customer.")
    brand_count = fields.Integer('Brands', compute='_compute_brand_count')

    @api.depends('brand_ids')
    def _compute_brand_count(self):
        for partner in self:
            partner.brand_count = len(partner.brand_ids)

    def action_view_brands(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Brands',
            'res_model': 'social.brand',
            'view_mode': 'kanban,list,form',
            'domain': [('partner_id', 'in', self.ids)],
            'context': {'default_partner_id': self.id},
        }
