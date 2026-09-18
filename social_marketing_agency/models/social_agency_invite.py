# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SocialAgencyInvite(models.TransientModel):
    """Invite a customer contact as a portal user for a brand.

    The group is chosen from the brand's ``customer_edit_enabled`` setting:
    disabled → approver group (read + approve), enabled → editor group
    (full editing of own data).
    """

    _name = 'social.agency.invite'
    _description = 'Invite Customer Contact'

    brand_id = fields.Many2one(
        'social.brand', string='Brand', required=True,
        default=lambda self: self._default_brand())
    partner_id = fields.Many2one(
        'res.partner', string='Contact', required=True,
        help="A contact (child partner) of the brand's customer.")
    email = fields.Char('Email')

    @api.model
    def _default_brand(self):
        from odoo.http import request
        if request and request.session.get('social_brand_id'):
            return request.session['social_brand_id']
        return False

    @api.onchange('brand_id')
    def _onchange_brand_id(self):
        if self.brand_id:
            self.partner_id = False
            return {
                'domain': {
                    'partner_id': [
                        ('parent_id', '=', self.brand_id.partner_id.id)],
                },
            }
        return {'domain': {'partner_id': []}}

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.email = self.partner_id.email or ''

    def action_invite(self):
        self.ensure_one()
        brand = self.brand_id
        partner = self.partner_id
        if partner.parent_id.commercial_partner_id != brand.partner_id.commercial_partner_id:
            raise UserError(
                _('The contact must belong to the brand\'s customer '
                  '"%s".', brand.partner_id.name))
        email = self.email or partner.email
        if not email:
            raise UserError(_('An email address is required to invite a contact.'))

        user = self.env['res.users'].sudo().search(
            [('partner_id', '=', partner.id)], limit=1)
        if not user:
            user = self.env['res.users'].sudo().with_context(
                no_reset_password=False).create({
                    'partner_id': partner.id,
                    'login': email,
                    'groups_id': [
                        (6, 0, [self.env.ref('base.group_portal').id])],
                })
        user._assign_customer_group_from_brand(brand)
        brand._sync_dashboard_users()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Contact invited'),
                'message': _('%(name)s is now a customer user for "%(brand)s".',
                             name=user.name, brand=brand.name),
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
