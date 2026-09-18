# -*- coding:utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, models

from odoo.exceptions import UserError


class UtmMedium(models.Model):
    _inherit = 'utm.medium'

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_social_marketing_accounts(self):
        """ Already handled by ondelete='restrict', but let's show a nice error message """
        linked_social_marketing_accounts = self.env['social_marketing.account'].sudo().search([
            ('utm_medium_id', 'in', self.ids)
        ])

        if linked_social_marketing_accounts:
            raise UserError(_(
                "You cannot delete these UTM Mediums as they are linked to the following social accounts in "
                "Social:\n%(social_marketing_accounts)s",
                social_marketing_accounts=', '.join(['"%s"' % name for name in linked_social_marketing_accounts.mapped('name')])))
