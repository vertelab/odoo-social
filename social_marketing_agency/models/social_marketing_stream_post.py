# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SocialMarketingStreamPost(models.Model):
    """Incoming inbox item, scoped to the brand of its stream.

    ``brand_id`` is a *stored* related field, not a plain related one. A
    non-stored related field has no column, so it cannot be used in an
    ir.rule domain and cannot be searched or grouped without the ORM
    walking the relation on every access. Access control here has to hold
    on every path into the ORM, so the value is written to a column and
    indexed, and the record rules below test that column directly.

    The stream owns the brand; the item inherits it. Moving a stream to
    another brand moves its items with it, which the related field's
    dependency handles on its own.
    """

    _name = 'social_marketing.stream.post'
    _inherit = ['social_marketing.stream.post', 'social.brand.focus.mixin']

    brand_id = fields.Many2one(
        'social.brand', string='Brand',
        related='stream_id.brand_id', store=True, index=True, readonly=True,
        help="Brand this incoming item belongs to, taken from its stream. "
             "Stored so record rules, searches and grouping can use it.")
