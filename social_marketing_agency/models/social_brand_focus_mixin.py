# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models

from odoo.http import request


class SocialBrandFocusMixin(models.AbstractModel):
    """Brand focus for agency users.

    When an agency user selects a brand (brand kanban root), the selection is
    stored in the session as ``social_brand_id``. Models inheriting this mixin
    then filter their searches and default new records to the focused brand —
    the same pattern as ``social_marketing_account`` uses for the session
    company. Customer (portal) users are scoped by record rules instead and
    never get the session filter applied.
    """

    _name = 'social.brand.focus.mixin'
    _description = 'Brand Focus Mixin'

    @api.model
    def _get_focus_brand(self):
        """Return the focused brand id from the session, or False."""
        if 'brand_id' not in self._fields:
            return False
        # Customer users are scoped by ir.rules, not by the session.
        if self.env.user.share:
            return False
        if request and request.session.get('social_brand_id'):
            return request.session['social_brand_id']
        return False

    @api.model
    def _get_default_brand(self):
        """Default for brand_id fields: the focused brand, or False."""
        return self._get_focus_brand()

    def _search(self, domain, offset=0, limit=None, order=None):
        brand_id = self._get_focus_brand()
        if brand_id and 'brand_id' in self._fields:
            domain = list(domain) + [('brand_id', '=', brand_id)]
        return super()._search(domain, offset=offset, limit=limit, order=order)
