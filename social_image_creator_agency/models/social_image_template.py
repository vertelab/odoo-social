# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SocialImageTemplate(models.Model):
    """Add the agency brand scope to image templates (spec: agency-brand-kit).

    ``brand_id`` is optional: an unbranded template stays company-level data,
    exactly like brand_id = False on the other agency-scoped models. Brand
    visibility is enforced by the record rules in security/security.xml,
    copied from the agency pattern; binding-record selection is limited to
    the brand by :meth:`get_binding_domain`.
    """

    _inherit = 'social.image.template'

    brand_id = fields.Many2one(
        'social.brand', string='Brand', ondelete='set null', index=True,
        help="Optional brand scope. When set, customer users only see this "
             "template if they belong to the brand, and binding record "
             "pickers are limited to the brand's records where the binding "
             "model supports it.")

    def get_binding_domain(self):
        """Return a search domain restricting binding-record selection to
        this template's brand scope, per the agency-brand-kit spec.

        The domain is ``[('brand_id', '=', brand)]`` when the template is
        branded AND the binding model carries a ``brand_id`` field (detected
        via ``_fields``, same idea as ``fields_get``); otherwise an empty
        list, meaning the full (company) scope applies. Used by the render
        wizard record picker (onchange domain + a server-side guard) and by
        the editor preview record search in brand_provider.js.
        """
        self.ensure_one()
        if not self.brand_id or not self.model_id:
            return []
        model = self.model_id.model
        if model not in self.env:
            return []
        if 'brand_id' in self.env[model]._fields:
            return [('brand_id', '=', self.brand_id.id)]
        return []

    def render_for_record(self, record, format='png', variant_index=0):
        """Brand guard on top of the base renderer: refuse records outside
        the template's brand scope (the pickers already filter, this covers
        direct calls and stale selections)."""
        if self.brand_id and 'brand_id' in record._fields:
            if record.brand_id != self.brand_id:
                raise UserError(_(
                    "Record %(record)s does not belong to brand %(brand)s, "
                    "which template %(template)s is scoped to.") % {
                    'record': record.display_name,
                    'brand': self.brand_id.name,
                    'template': self.name,
                })
        return super().render_for_record(
            record, format=format, variant_index=variant_index)

    def get_preview_bindings(self, record_id, scene_json=None):
        """Same brand guard for the editor's live preview path."""
        if self.model_id and self.brand_id:
            model = self.model_id.model
            if model in self.env and 'brand_id' in self.env[model]._fields:
                record = self.env[model].browse(record_id).exists()
                if record and record.brand_id != self.brand_id:
                    raise UserError(_(
                        "Record %(id)s does not belong to brand %(brand)s, "
                        "which this template is scoped to.") % {
                        'id': record_id, 'brand': self.brand_id.name})
        return super().get_preview_bindings(record_id, scene_json=scene_json)
