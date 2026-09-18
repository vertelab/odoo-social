# -*- coding:utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, models

from odoo.exceptions import UserError


class UtmSource(models.Model):
    _inherit = 'utm.source'

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_social_marketing_posts(self):
        """ Already handled by ondelete='restrict', but let's show a nice error message """
        linked_social_marketing_posts = self.env['social_marketing.post'].sudo().search([
            ('source_id', 'in', self.ids)
        ])

        if linked_social_marketing_posts:
            raise UserError(_(
                "You cannot delete these UTM Sources as they are linked to social_marketing.posts in "
                "Social:\n%(utm_sources)s",
                utm_sources=', '.join(['"%s"' % name for name in self.mapped('name')])))
