# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, models
from odoo.exceptions import UserError


class SocialImageRenderWizard(models.TransientModel):
    """Brand-constrained record picker for the render wizard (spec:
    agency-brand-kit, "Template binding to brand customer data").

    The picker's model is already restricted to the template's binding
    model by the base module; here its domain is narrowed to the
    template's brand when the binding model carries a brand_id field
    (``social.image.template.get_binding_domain``). Applied two ways:
    an onchange domain for the UI, and a server-side guard so a stale
    or hand-crafted record_id can never render out of scope.
    """

    _inherit = 'social.image.render.wizard'

    @api.onchange('template_id')
    def _onchange_template_brand_domain(self):
        """Narrow the record picker to the template's brand scope."""
        if not self.template_id:
            return {'domain': {'record_id': []}}
        return {'domain': {
            'record_id': self.template_id.get_binding_domain()}}

    def _get_bound_record(self):
        record = super()._get_bound_record()
        if record and self.template_id.brand_id \
                and 'brand_id' in record._fields:
            if record.brand_id != self.template_id.brand_id:
                raise UserError(_(
                    "Record %(record)s does not belong to brand %(brand)s, "
                    "which template %(template)s is scoped to. Pick a "
                    "record of that brand, or use an unbranded template.") % {
                    'record': record.display_name,
                    'brand': self.template_id.brand_id.name,
                    'template': self.template_id.name,
                })
        return record
