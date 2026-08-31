# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SocialBrandAsset(models.Model):
    """Per-brand media bank for files that belong to no other Odoo record.

    Post images live on the post, underlag files live on the underlag. What
    is left over (raw footage, press kits, stock photography bought for the
    brand) belongs here so the image builder has one place to look.
    """

    _name = 'social.brand.asset'
    _description = 'Social Brand Asset'
    _order = 'sequence, id'

    ASSET_TYPES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('other', 'Other'),
    ]

    brand_id = fields.Many2one(
        'social.brand', string='Brand', required=True, ondelete='cascade',
        index=True)
    name = fields.Char('Name', required=True)
    file = fields.Binary('File', attachment=True, required=True)
    filename = fields.Char('Filename')
    asset_type = fields.Selection(
        ASSET_TYPES, string='Asset Type', required=True, default='image')
    description = fields.Text('Description')
    sequence = fields.Integer('Sequence', default=10)
