# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResUsers(models.Model):
    """User extension: brand assignment and customer group helpers."""

    _inherit = 'res.users'

    brand_ids = fields.Many2many(
        'social.brand', 'social_brand_user_rel', 'user_id', 'brand_id',
        string='Brands',
        help="Brands this agency user works with. The brand kanban root shows "
             "only these brands.")
    brand_count = fields.Integer('Brands', compute='_compute_brand_count')

    @api.depends('brand_ids')
    def _compute_brand_count(self):
        for user in self:
            user.brand_count = len(user.brand_ids)

    def _assign_customer_group_from_brand(self, brand):
        """Place the user in the customer group matching the brand setting.

        ``customer_edit_enabled`` False → approver group (read + approve).
        ``customer_edit_enabled`` True  → editor group (full edit, implies approver).
        """
        self.ensure_one()
        brand.ensure_one()
        group = self.env.ref('social_marketing_agency.group_social_customer_approver')
        if brand.customer_edit_enabled:
            group = self.env.ref('social_marketing_agency.group_social_customer_editor')
        self.write({'groups_id': [(4, group.id)]})
        return group

    def action_view_brands(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Brands',
            'res_model': 'social.brand',
            'view_mode': 'kanban,list,form',
            'domain': [('id', 'in', self.brand_ids.ids)],
        }
